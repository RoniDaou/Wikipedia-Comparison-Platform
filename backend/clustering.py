"""
clustering.py — Project 2: Wikipedia Infobox Document Clustering
COE 543/743 — Intelligent Data Processing and Applications
Spring 2026 — Instructor: Joe Tekli

Entry point for all clustering operations.
Imports and dispatches to:
  - kmean.py          : KMeansClustering (K-Medoids) + TSNE2D
  - agglomerative.py  : AgglomerativeClustering

Also contains:
  - SimilarityMatrixBuilder : pairwise TED-based similarity (cached in MongoDB)
  - ClusteringPipeline      : high-level interface called by api.py
"""

import random
import math
import re
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone

# ── Import algorithms from dedicated modules ───────────────────────────────
from kmeans import KMeansClustering, TSNE2D
from agglomerative import AgglomerativeClustering


# ══════════════════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════════════════

def similarity_to_distance(sim: float) -> float:
    """Convert similarity ∈ [0,1] → distance ∈ [0,1].  d = 1 − sim."""
    return round(max(0.0, min(1.0, 1.0 - sim)), 6)


def _mean(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _pairwise_distance(idx_a: int, idx_b: int,
                       distance_matrix: List[List[float]]) -> float:
    """Look up pre-computed distance between two country indices."""
    return distance_matrix[idx_a][idx_b]


# ══════════════════════════════════════════════════════════════════════════════
#  Similarity Matrix Builder
# ══════════════════════════════════════════════════════════════════════════════

class SimilarityMatrixBuilder:
    """
    Computes and caches pairwise TED similarity scores for all countries.

    The matrix is stored in MongoDB as a single document so that clustering
    never needs to rerun expensive TED computations.

    Storage schema (similarity_matrix collection):
    {
        "countries": ["Lebanon", "France", ...],          # ordered list
        "matrix":    [[1.0, 0.72, ...], ...],             # N×N similarity
        "built_at":  "2026-05-11T...",
        "count":     N
    }
    """

    def __init__(self, comparator, db):
        """
        Args:
            comparator : TEDComparator instance
            db         : WikipediaDatabase instance
        """
        self.comparator = comparator
        self.db = db

    def _normalize_selected_features(self, selected_features: Optional[List[str]]) -> List[str]:
        """Return a clean, de-duplicated list of requested infobox fields."""
        if not selected_features:
            return []
        seen = set()
        cleaned = []
        for field in selected_features:
            if field is None:
                continue
            key = str(field).strip()
            if key and key not in seen:
                seen.add(key)
                cleaned.append(key)
        return cleaned


    def _normalize_feature_name(self, field: str) -> str:
        """Normalize a field name the same way tree_builder normalizes XML tags."""
        name = str(field or '').lower().strip()
        name = re.sub(r'[^a-z0-9]', '_', name)
        name = re.sub(r'_+', '_', name).strip('_')
        return name

    def _is_currency_only_matrix(self, selected_features: List[str]) -> bool:
        """True when the user selected only the Currency infobox field."""
        return (
            len(selected_features) == 1
            and self._normalize_feature_name(selected_features[0]) == 'currency'
        )

    # ══════════════════════════════════════════════════════════════════
    #  Semantic field groups
    #
    #  Maps a concept name to all Wikipedia infobox field name variants.
    #  When computing similarity, ALL fields in the same group are
    #  collected and their values merged — field title is irrelevant,
    #  only the VALUE inside matters.
    #  e.g. Cuba ("Official language: Spanish") and Argentina
    #       ("National language: Spanish") both produce {'spanish'} -> 1.0
    # ══════════════════════════════════════════════════════════════════

    FIELD_GROUPS: Dict[str, List[str]] = {
        'language': [
            'official language',
            'official languages',
            'official languages and national language',
            'official languages and regional languages',
            'national language',
            'national languages',
            'national language (official)',
            'co-official languages',
            'common language',
            'common languages',
            'language',
            'languages',
            'languages in official use',
            'language spoken at home',
            'recognised language',
            'recognised languages',
            'recognised national languages',
            'recognised regional languages',
            'recognized language',
            'recognized languages',
            'recognized national languages',
            'recognized regional languages',
            'regional languages',
            'regional and minority languages',
            'minority language',
            'minority languages',
            'indigenous languages',
            'native languages',
            'working language',
            'working languages',
            'official language (federal level)',
            'official language and national language',
            'government-sponsored languages',
            'national sign language',
            'spoken languages',
            'vernacular language',
            'vernacular languages',
            'other languages',
            'other common language',
            'foreign languages',
            'second language',
            'significant language',
        ],
        'religion': [
            'religion',
            'religions',
            'official religion',
            'state religion',
            'religious groups',
            'religious group',
        ],
        'ethnic groups': [
            'ethnic groups',
            'ethnic group',
            'ethnicity',
            'ethnicities',
            'nationality',
            'nationalities',
            'demographics',
        ],
        'currency': [
            'currency',
            'currencies',
        ],
        'government': [
            'government',
            'government type',
            'type of government',
            'governing body',
            'political system',
        ],
    }

    _FIELD_GROUP_LOOKUP: Dict[str, str] = {
        variant.lower(): canonical
        for canonical, variants in FIELD_GROUPS.items()
        for variant in variants
    }

    def _canonical_group(self, field: str) -> Optional[str]:
        """Return the canonical group name for a field, or None if ungrouped."""
        norm = re.sub(r'\s*\([^)]*\)', '',
                      str(field or '').lower()).strip()
        if norm in self._FIELD_GROUP_LOOKUP:
            return self._FIELD_GROUP_LOOKUP[norm]
        for variant, canonical in self._FIELD_GROUP_LOOKUP.items():
            if norm.startswith(variant) or variant.startswith(norm):
                return canonical
        return None

    def _collect_group_values(self, fields: Dict,
                              selected_field: str) -> Optional[str]:
        """
        Collect and merge values from ALL fields that belong to the same
        semantic group as selected_field. Field title is ignored — only
        the value inside matters.
        Falls back to exact field lookup for ungrouped fields.
        """
        group = self._canonical_group(selected_field)
        if group is not None:
            merged = [str(v) for f, v in fields.items()
                      if self._canonical_group(f) == group]
            return '\n'.join(merged) if merged else None
        return fields.get(selected_field)

    # ── Item set extraction ─────────────────────────────────────────────

    @staticmethod
    def _extract_item_set(value: str) -> set:
        """
        Extract a normalized set of items from any multi-value infobox field.
        Strips tree connectors, parenthetical qualifiers, lowercases everything.
        """
        items = set()
        for line in str(value or '').splitlines():
            clean = re.sub(r'^[├└│─\s]+', '', line).strip()
            clean = re.sub(r'\s*\([^)]*\)', '', clean).strip()
            clean = re.sub(r'[,;:\-]+$', '', clean).strip().lower()
            if len(clean) >= 2:
                items.add(clean)
        return items

    @staticmethod
    def _jaccard_similarity(set_a: set, set_b: set) -> float:
        """Jaccard: |A ∩ B| / |A ∪ B|. Returns 0.0 if both empty."""
        union = set_a | set_b
        return len(set_a & set_b) / len(union) if union else 0.0

    # ── Currency ────────────────────────────────────────────────────────

    @staticmethod
    def _extract_primary_iso_code(value) -> Optional[str]:
        """Extract the primary ISO code from the first line of a currency field."""
        first_line = ''
        for line in str(value or '').splitlines():
            s = line.strip()
            if s:
                first_line = s
                break
        codes = re.findall(r'\b[A-Z]{3}\b', first_line)
        return codes[0] if codes else None

    def _derive_shared_codes(self, country_names: List[str],
                             selected_features: List[str]) -> Dict[str, set]:
        """
        Scan every country in the dataset and derive, for each selected
        feature group, the set of VALUES that appear in 2+ countries.

        These are the 'shared' values — used to implement the three-level
        similarity gradient for both currency and language:

          Both share a shared value  -> full Jaccard (or 1.0 if identical)
          Both have only unique vals -> 0.5  (share the 'unique' property)
          One shared, one unique     -> 0.0  (maximum separation)

        Returns a dict: { canonical_group_name -> set_of_shared_values }
        e.g. { 'language': {'english','arabic','french',...},
               'currency': {'EUR','USD',...} }

        Fully automatic — no hardcoded lists, works for any dataset.
        """
        if not selected_features:
            return {}

        # Group selected features by canonical group
        groups_to_scan: set = set()
        for field in selected_features:
            g = self._canonical_group(field)
            if g:
                groups_to_scan.add(g)
            elif self._normalize_feature_name(field) == 'currency':
                groups_to_scan.add('currency')

        if not groups_to_scan:
            return {}

        # Count value occurrences across all countries
        value_counts: Dict[str, Dict[str, int]] = {g: {} for g in groups_to_scan}

        for name in country_names:
            doc = self.db.get_country(name)
            if not doc:
                continue
            fields = doc.get('fields') or {}

            for group in groups_to_scan:
                # Find the selected field for this group
                sel_field = next(
                    (f for f in selected_features
                     if self._canonical_group(f) == group or
                     (group == 'currency' and
                      self._normalize_feature_name(f) == 'currency')),
                    None
                )
                if sel_field is None:
                    continue

                raw_value = self._collect_group_values(fields, sel_field)
                if not raw_value:
                    continue

                if group == 'currency':
                    code = self._extract_primary_iso_code(raw_value)
                    if code:
                        value_counts[group][code] = \
                            value_counts[group].get(code, 0) + 1
                else:
                    for item in self._extract_item_set(raw_value):
                        value_counts[group][item] = \
                            value_counts[group].get(item, 0) + 1

        # Keep only values that appear in 2+ countries
        shared: Dict[str, set] = {}
        for group, counts in value_counts.items():
            shared[group] = {v for v, c in counts.items() if c >= 2}
            print(f"[Matrix] Shared '{group}' values "
                  f"(>=2 countries): {sorted(shared[group])[:10]}"
                  f"{'...' if len(shared[group]) > 10 else ''}")

        return shared

    def _three_level_similarity(self, set_a: set, set_b: set,
                                shared_values: set) -> float:
        """
        Three-level similarity for any categorical set-valued feature.

        Level 1 — Both sets share at least one shared value:
            Jaccard restricted to shared values, so unique minority values
            don't dilute the similarity signal.
            e.g. {'arabic','kurdish'} vs {'arabic'}: shared={'arabic'}
                 -> Jaccard({'arabic'},{'arabic'}) = 1.0

        Level 2 — No shared value overlap, but both have ONLY unique values:
            Return 0.5. They share the 'unique language country' property —
            more similar to each other than to shared-language countries.
            e.g. {'japanese'} vs {'korean'}: both unique -> 0.5

        Level 3 — One has a shared value the other lacks:
            Return 0.0. Maximum separation.
            e.g. {'arabic'} vs {'japanese'}: arabic is shared, japanese unique -> 0.0

        This matches the same logic used for currency and solves the giant
        Cluster 0 problem: unique-language countries now get 0.5 signal
        against each other instead of 0.0.
        """
        if not set_a and not set_b:
            return 0.0

        shared_in_a = set_a & shared_values
        shared_in_b = set_b & shared_values

        # Level 1: both have shared values — compare on shared values only
        if shared_in_a and shared_in_b:
            return self._jaccard_similarity(shared_in_a, shared_in_b)

        # Level 2: neither has any shared value — both are unique-language
        if not shared_in_a and not shared_in_b:
            return 0.5

        # Level 3: one has a shared value, the other doesn't
        return 0.0

    def _feature_similarity(self, val_a: str, val_b: str,
                            group: str,
                            shared_by_group: Dict[str, set]) -> float:
        """
        Compute similarity for one feature, routing to the right method.

        Currency  -> three-level on primary ISO code
        Language / other -> three-level on item sets
        """
        shared = shared_by_group.get(group, set())

        if group == 'currency':
            code_a = self._extract_primary_iso_code(val_a)
            code_b = self._extract_primary_iso_code(val_b)
            if code_a is None or code_b is None:
                return 0.0
            if code_a == code_b:
                return 1.0
            if code_a not in shared and code_b not in shared:
                return 0.5
            return 0.0

        set_a = self._extract_item_set(val_a)
        set_b = self._extract_item_set(val_b)
        return self._three_level_similarity(set_a, set_b, shared)

    # ── Dispatcher ──────────────────────────────────────────────────────

    def _selected_feature_similarity(self, country_a: Dict, country_b: Dict,
                                     selected_features: List[str],
                                     shared_by_group: Dict[str, set] = None
                                     ) -> Optional[float]:
        """
        Compute feature-level similarity by comparing VALUES, not field titles.

        For each selected feature:
          1. Find its canonical group
          2. Collect ALL field values in that group from each country
          3. Apply three-level similarity (shared/unique/cross)

        Returns None only when no features are provided, falling back to TED.
        """
        if not selected_features:
            return None

        fields_a = country_a.get('fields', {}) or {}
        fields_b = country_b.get('fields', {}) or {}
        shared_by_group = shared_by_group or {}

        scores = []
        for field in selected_features:
            val_a = self._collect_group_values(fields_a, field)
            val_b = self._collect_group_values(fields_b, field)
            if val_a is None or val_b is None:
                continue

            norm = self._normalize_feature_name(field)
            group = self._canonical_group(field) or norm

            scores.append(self._feature_similarity(
                val_a, val_b, group, shared_by_group))

        return sum(scores) / len(scores) if scores else None

    def _filter_country_fields(self, country_doc: Dict, selected_features: List[str]) -> Dict:
        """
        Build a reduced country document containing only selected infobox fields.

        This keeps the project aligned with TED-based document similarity: the
        user controls which fields enter the semi-structured tree, but the
        pairwise similarity is still computed by TED on that reduced tree.
        """
        if not selected_features:
            return country_doc

        reduced = dict(country_doc)
        # Avoid comparing identity metadata when the user explicitly asks to
        # cluster by selected fields. The real country names are still kept in
        # the matrix country list; this reduced document is only used for TED.
        reduced['country_name'] = 'country'
        reduced.pop('source_url', None)

        fields = country_doc.get('fields', {}) or {}
        reduced['fields'] = {
            field: fields[field]
            for field in selected_features
            if field in fields
        }
        if '_field_order' in country_doc:
            reduced['_field_order'] = [
                field for field in country_doc.get('_field_order', [])
                if field in reduced['fields']
            ]
        return reduced

    # ── Public interface ───────────────────────────────────────────────

    def build(self,
              country_names: List[str],
              progress_callback=None,
              selected_features: Optional[List[str]] = None) -> Dict:
        """
        Compute the full N×N similarity matrix.

        Only the upper triangle is computed (symmetric); diagonal = 1.0.
        When selected_features is provided, each country document is reduced to
        those fields before the TED comparator runs.

        Args:
            country_names     : ordered list of country names
            progress_callback : optional callable(done, total, pair_info)
            selected_features : optional list of infobox fields to keep before TED

        Returns:
            The stored matrix document (dict).
        """
        selected_features = self._normalize_selected_features(selected_features)
        n = len(country_names)
        matrix = [[0.0] * n for _ in range(n)]

        for i in range(n):
            matrix[i][i] = 1.0

        # Derive shared values for all selected feature groups from the dataset.
        # Empty dict when no features selected (full TED path).
        shared_by_group = self._derive_shared_codes(country_names, selected_features)

        total_pairs = n * (n - 1) // 2
        done = 0

        for i in range(n):
            data_i = self.db.get_country(country_names[i])
            if data_i:
                data_i.pop('_id', None)
                data_i = self._filter_country_fields(data_i, selected_features)

            for j in range(i + 1, n):
                sim = 0.0
                try:
                    data_j = self.db.get_country(country_names[j])
                    if data_j:
                        data_j.pop('_id', None)
                        data_j = self._filter_country_fields(data_j, selected_features)

                    if data_i and data_j:
                        special_sim = self._selected_feature_similarity(
                            data_i, data_j, selected_features, shared_by_group
                        )
                        if special_sim is not None:
                            sim = special_sim
                        else:
                            result = self.comparator.compare_countries(data_i, data_j)
                            sim = result['similarity_score']
                except Exception as exc:
                    print(f"[Matrix] Error ({country_names[i]} vs {country_names[j]}): {exc}")

                matrix[i][j] = sim
                matrix[j][i] = sim
                done += 1

                if progress_callback:
                    progress_callback(done, total_pairs,
                                      f"{country_names[i]} ↔ {country_names[j]}")

        doc = {
            'countries': country_names,
            'matrix':    matrix,
            'count':     n,
            'built_at':  datetime.now(timezone.utc).isoformat(),
            'matrix_mode': 'feature_ted' if selected_features else 'full_ted',
            'selected_features': selected_features
        }
        # NOTE: do NOT save here — the ClusteringPipeline.build_and_save_matrix()
        # handles saving so we never double-insert.
        print(f"[Matrix] Built {n}×{n} matrix ({total_pairs} pairs).")
        return doc

    def build_incremental(self, progress_callback=None) -> Dict:
        """
        Extend an existing cached matrix with any newly added countries.
        If no cached matrix exists, builds from scratch.
        (Legacy method kept for compatibility.)
        """
        existing = self.db.get_latest_similarity_matrix()
        all_names = self.db.get_country_names()

        if not existing:
            return self.build(sorted(all_names), progress_callback)

        old_names = existing['countries']
        new_names = [n for n in all_names if n not in old_names]

        if not new_names:
            print("[Matrix] Already up-to-date.")
            return existing

        merged_names = old_names + sorted(new_names)
        return self.build_incremental_extended(
            existing, new_names, merged_names, progress_callback)

    def build_incremental_extended(self,
                                    existing: Dict,
                                    new_names: List[str],
                                    merged_names: List[str],
                                    progress_callback=None) -> Dict:
        """
        Core incremental build: given an existing matrix and new country names,
        computes only the new pairs and returns a merged matrix dict.
        Does NOT save — the caller (ClusteringPipeline) handles saving.
        """
        n_old = len(existing['countries'])
        n_new = len(merged_names)

        # Expand old matrix
        old_matrix = existing['matrix']
        matrix = [[0.0] * n_new for _ in range(n_new)]

        for i in range(n_old):
            for j in range(n_old):
                matrix[i][j] = old_matrix[i][j]

        for i in range(n_new):
            matrix[i][i] = 1.0

        total_pairs = n_new * (n_new - 1) // 2 - n_old * (n_old - 1) // 2
        done = 0

        for i in range(n_new):
            data_i = self.db.get_country(merged_names[i])
            if data_i:
                data_i.pop('_id', None)

            for j in range(i + 1, n_new):
                if i < n_old and j < n_old:
                    continue  # already computed

                sim = 0.0
                try:
                    data_j = self.db.get_country(merged_names[j])
                    if data_j:
                        data_j.pop('_id', None)

                    if data_i and data_j:
                        result = self.comparator.compare_countries(data_i, data_j)
                        sim = result['similarity_score']
                except Exception as exc:
                    print(f"[Matrix] Error ({merged_names[i]} vs {merged_names[j]}): {exc}")

                matrix[i][j] = sim
                matrix[j][i] = sim
                done += 1

                if progress_callback:
                    progress_callback(done, total_pairs,
                                      f"{merged_names[i]} ↔ {merged_names[j]}")

        doc = {
            'countries': merged_names,
            'matrix':    matrix,
            'count':     n_new,
            'built_at':  datetime.now(timezone.utc).isoformat(),
            'matrix_mode': 'full_ted',
            'selected_features': []
        }
        # NOTE: do NOT save here — ClusteringPipeline handles saving.
        print(f"[Matrix] Extended to {n_new}×{n_new}.")
        return doc


# ══════════════════════════════════════════════════════════════════════════════
#  K-Means Clustering
# ══════════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════════
#  t-SNE  (pure Python — mirrors the JS implementation)
#  Projects the N×N similarity matrix into 2D coordinate vectors so that
#  true K-Means (mean centroid) can be computed.
# ══════════════════════════════════════════════════════════════════════════════



class ClusteringPipeline:
    """
    High-level interface called by api.py.
    Handles loading the matrix from DB and dispatching to the right algorithm.
    """

    def __init__(self, db, comparator):
        self.db         = db
        self.comparator = comparator
        self.builder    = SimilarityMatrixBuilder(comparator, db)

    # ── Matrix management ──────────────────────────────────────────────

    def get_matrix_by_id(self, matrix_id: str) -> Optional[Dict]:
        """Load a specific matrix from DB by its _id string."""
        return self.db.get_similarity_matrix(matrix_id)

    def build_and_save_matrix(self, country_names: Optional[List[str]] = None,
                               name: str = '',
                               progress_callback=None,
                               selected_features: Optional[List[str]] = None) -> Dict:
        """
        Build a brand-new similarity matrix and save it to the DB.
        Always creates a new document — never overwrites.

        Args:
            country_names    : list to include; None = all in DB
            name             : human-readable label for this matrix
            progress_callback: callable(done, total, pair_info)
            selected_features: optional infobox fields to keep before TED

        Returns:
            The saved matrix doc (includes '_id' as string).
        """
        names = country_names or sorted(self.db.get_country_names())
        doc   = self.builder.build(names, progress_callback, selected_features=selected_features)
        inserted_id = self.db.save_similarity_matrix(doc, name=name)
        doc['_id']  = inserted_id
        return doc

    def build_incremental(self, base_matrix_id: str,
                           name: str = '',
                           progress_callback=None) -> Dict:
        """
        Extend an existing matrix with new countries from the DB.
        Creates a new saved document (does not modify the old one).
        """
        existing = self.db.get_similarity_matrix(base_matrix_id)
        if not existing:
            return self.build_and_save_matrix(
                progress_callback=progress_callback, name=name)

        all_names = sorted(self.db.get_country_names())
        old_names = existing['countries']
        new_names = [n for n in all_names if n not in old_names]

        if not new_names:
            return existing   # nothing new to add

        # Build only the new pairs on top of the existing matrix
        merged = old_names + new_names
        doc = self.builder.build_incremental_extended(
            existing, new_names, merged, progress_callback)
        inserted_id = self.db.save_similarity_matrix(doc, name=name)
        doc['_id']  = inserted_id
        return doc

    # ── Run clustering ─────────────────────────────────────────────────

    def run_kmeans(self, matrix_doc: Dict,
                   k: int = 3,
                   max_iter: int = 100,
                   n_init: int = 10,
                   name: str = '') -> Dict:
        """Run K-Means on a matrix document. Saves a new result doc."""
        countries = matrix_doc['countries']
        sim_m     = matrix_doc['matrix']
        dist_m    = [[similarity_to_distance(sim_m[i][j])
                      for j in range(len(countries))]
                     for i in range(len(countries))]

        algo   = KMeansClustering(k=k, max_iter=max_iter, n_init=n_init)
        result = algo.fit(countries, dist_m)
        matrix_id = str(matrix_doc.get('_id', ''))
        inserted_id = self.db.save_cluster_result(result, name=name, matrix_id=matrix_id)
        result['_id']       = inserted_id
        result['matrix_id'] = matrix_id
        return result

    def run_agglomerative(self, matrix_doc: Dict,
                          n_clusters: int = 3,
                          linkage: str = 'average',
                          name: str = '') -> Dict:
        """Run Agglomerative Hierarchical Clustering on a matrix document."""
        countries = matrix_doc['countries']
        sim_m     = matrix_doc['matrix']
        dist_m    = [[similarity_to_distance(sim_m[i][j])
                      for j in range(len(countries))]
                     for i in range(len(countries))]

        # Coordinates are for visualization only; clustering uses dist_m.
        perp   = min(50, max(5, len(countries) // 3))
        tsne   = TSNE2D(perplexity=perp, early_exaggeration=20.0,
                        iterations=1500, seed=42)
        # Use temporary zero labels for layout; final cluster labels are assigned
        # by AgglomerativeClustering after the hierarchical merges.
        coords = tsne.fit(dist_m)

        algo   = AgglomerativeClustering(n_clusters=n_clusters, linkage=linkage)
        result = algo.fit(countries, dist_m, coords=coords)
        matrix_id = str(matrix_doc.get('_id', ''))
        inserted_id = self.db.save_cluster_result(result, name=name, matrix_id=matrix_id)
        result['_id']       = inserted_id
        result['matrix_id'] = matrix_id
        return result

    # ── Evaluation helpers (used by the API for cluster stats) ─────────

    def get_top_similar_pairs(self, matrix_doc: Dict,
                               top_n: int = 10) -> List[Dict]:
        """Return top-N most similar country pairs (excluding self)."""
        countries = matrix_doc['countries']
        sim_m     = matrix_doc['matrix']
        n         = len(countries)
        pairs     = []

        for i in range(n):
            for j in range(i + 1, n):
                pairs.append({
                    'country1':   countries[i],
                    'country2':   countries[j],
                    'similarity': round(sim_m[i][j], 4)
                })

        pairs.sort(key=lambda x: -x['similarity'])
        return pairs[:top_n]

    def get_country_neighbors(self, matrix_doc: Dict,
                               country: str,
                               top_n: int = 5) -> List[Dict]:
        """Return top-N nearest neighbours of a given country."""
        countries = matrix_doc['countries']
        if country not in countries:
            return []

        i     = countries.index(country)
        sim_m = matrix_doc['matrix']
        n     = len(countries)

        neighbors = [
            {'country': countries[j], 'similarity': round(sim_m[i][j], 4)}
            for j in range(n) if j != i
        ]
        neighbors.sort(key=lambda x: -x['similarity'])
        return neighbors[:top_n]