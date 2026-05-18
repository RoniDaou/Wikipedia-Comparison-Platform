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
        'density': [
            'density',
            'population density',
            'pop density',
            'pop. density',
        ],
        'area': [
            'area',
            'total area',
            'land area',
            'surface area',
            # Wikipedia infobox area sub-row — exact "Total" only.
            # "Total (2)", "Total (3)" are intentionally excluded via
            # _canonical_group's numbered-suffix guard (see that method).
            'total',
        ],
        'population': [
            'population',
            'total population',
            'pop',
        ],
        'gdp': [
            'gdp',
            'gdp (nominal)',
            'gdp (ppp)',
            'gross domestic product',
            'gdp per capita',
            'gdp (nominal) per capita',
            'gdp (ppp) per capita',
        ],
        'per_capita': [
            'per capita',
            'gdp per capita',
            'gdp (nominal) per capita',
            'gdp (ppp) per capita',
            'income per capita',
            'gni per capita',
            'gnp per capita',
        ],
        'water': [
            'water',
            'water (%)',
            'water(%)',
            'water percentage',
            'water percent',
            'water area',
            'water area (%)',
            'percent water',
            'percentage water',
        ],
    }

    _FIELD_GROUP_LOOKUP: Dict[str, str] = {
        variant.lower(): canonical
        for canonical, variants in FIELD_GROUPS.items()
        for variant in variants
    }

    # Fields whose base name is shared with a group variant but whose
    # numbered suffix (2), (3), ... must NOT be grouped with it.
    # e.g. "Total (2)" and "Total (3)" are secondary area sub-rows that
    # carry different data and must be ignored for the 'area' group.
    _NUMBERED_SUFFIX_RE = re.compile(r'\s*\(\s*\d+\s*\)\s*$', re.IGNORECASE)

    def _canonical_group(self, field: str) -> Optional[str]:
        """
        Return the canonical group name for a field, or None if ungrouped.

        Special guard: fields with a numbered parenthetical suffix like
        "Total (2)" or "Total (3)" are excluded from all groups even though
        their base name ("total") is a registered variant.  This prevents
        secondary Wikipedia infobox sub-rows from polluting the area group.
        """
        raw = str(field or '').lower().strip()

        # Block "total (2)", "total (3)", etc. before any stripping
        if self._NUMBERED_SUFFIX_RE.search(raw):
            return None

        norm = re.sub(r'\s*\([^)]*\)', '', raw).strip()
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

        Numbered-suffix fields (e.g. "Total (2)", "Total (3)") are
        intentionally excluded: _canonical_group returns None for them,
        so they never contribute to any group's merged value.
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

    # ── Numerical fields (density, area, population, GDP) ──────────────

    # Canonical groups that contain numerical data
    _NUMERICAL_GROUPS = {'density', 'area', 'population', 'gdp', 'per_capita'}

    # Canonical groups that are bounded percentages (0–100).
    # These use a dedicated similarity function instead of the log-ratio
    # one used for huge unbounded numbers like density or GDP.
    _PERCENTAGE_GROUPS = {'water'}

    @staticmethod
    def _extract_numerical_value(value: str) -> Optional[float]:
        """
        Extract the primary numeric value from a Wikipedia infobox field.

        Handles formats like:
          "4.2/km2 (10.9/sq mi) (230th)"   → 4.2
          "45/km2 (116.5/sq mi) (179th)"   → 45.0
          "26,337/km2 (68,200/sq mi) (1st)"→ 26337.0
          "9,596,960 km2 (3,705,407 sq mi)"→ 9596960.0
          "$1.2 trillion"                   → 1.2  (+ unit handling)
          "1,441,719,852"                   → 1441719852.0

        Always extracts the FIRST number (before /km2, /km, or at start).
        Strips commas before parsing.
        """
        text = str(value or '').strip()
        # Priority: number immediately before /km2 or /km (density)
        m = re.search(r'([\d,]+\.?\d*)\s*/\s*km', text)
        if m:
            return float(m.group(1).replace(',', ''))
        # Dollar/currency prefix then number (GDP)
        m = re.search(r'[\$£€¥]\s*([\d,]+\.?\d*)', text)
        if m:
            return float(m.group(1).replace(',', ''))
        # First plain number in string
        m = re.search(r'([\d,]+\.?\d*)', text)
        if m:
            return float(m.group(1).replace(',', ''))
        return None

    @staticmethod
    def _numerical_similarity(val_a: str, val_b: str) -> float:
        """
        Log-ratio similarity between two numerical field values.

        Uses log base-10 difference normalised over a 4-order-of-magnitude
        range so that:
          - identical values → 1.0
          - 10x apart       → 0.75
          - 100x apart      → 0.50
          - 1000x apart     → 0.25
          - 10000x+ apart   → 0.0

        This handles the enormous range of real-world values
        (e.g. density: Monaco 26,337/km² vs Mongolia 2/km²).
        """
        import math
        a = SimilarityMatrixBuilder._extract_numerical_value(val_a)
        b = SimilarityMatrixBuilder._extract_numerical_value(val_b)
        if a is None or b is None or a <= 0 or b <= 0:
            return 0.0
        if a == b:
            return 1.0
        log_diff = abs(math.log10(a) - math.log10(b))
        return max(0.0, 1.0 - log_diff / 4.0)

    # ── Water percentage ────────────────────────────────────────────────

    @staticmethod
    def _parse_water_percent(raw: str) -> Optional[float]:
        """
        Parse a Wikipedia water-percentage infobox value into a float.

        Handles all observed formats:
          "9.71 (2015)"   → 9.71   (year in parentheses — stripped first)
          "3.5%"          → 3.5
          "3%"            → 3.0
          "3"             → 3.0
          "~3.5%"         → 3.5    (tilde prefix)
          "< 1%"          → 1.0    (inequality prefix)
          "> 1%"          → 1.0
          "3,5"           → 3.5    (European decimal comma)
          "2–4%"          → 3.0    (range → midpoint)
          "2-4%"          → 3.0    (hyphen range → midpoint)
          "negligible"    → 0.0    (known-zero word)
          "none"          → 0.0
          "minimal"       → 0.0
          "trace"         → 0.0
          "0"             → 0.0
          "N/A", "", None → None   (unknown — not the same as zero)
        """
        if raw is None:
            return None

        text = str(raw).strip()
        if not text:
            return None

        # Step 1: strip parenthetical content (years, citations, footnotes)
        # e.g. "9.71 (2015)" → "9.71"
        text = re.sub(r'\([^)]*\)', '', text).strip()

        # Step 2: known-zero words → 0.0  (we KNOW the value, it's just tiny)
        lower = text.lower()
        if lower in {'negligible', 'none', 'minimal', 'trace',
                     'insignificant', 'virtually none', '0'}:
            return 0.0

        # Step 3: unknown/missing markers → None  (we do NOT know the value)
        if lower in {'n/a', 'na', 'unknown', '-', '—', 'not available',
                     'not applicable', ''}:
            return None

        # Step 4: strip leading operators and % sign
        text = re.sub(r'^[~<>≤≥≈±\s]+', '', text)
        text = text.replace('%', '').strip()

        # Step 5: European decimal comma → period  (e.g. "3,5" → "3.5")
        # Only when comma is followed by exactly 1–2 digits at end of string
        text = re.sub(r',(\d{1,2})$', r'.\1', text)

        # Step 6: range → midpoint  (e.g. "2–4" or "2-4" → 3.0)
        range_match = re.search(r'([\d.]+)\s*[–\-]\s*([\d.]+)', text)
        if range_match:
            try:
                lo = float(range_match.group(1))
                hi = float(range_match.group(2))
                return (lo + hi) / 2.0
            except ValueError:
                pass

        # Step 7: plain float/int
        plain_match = re.search(r'[\d.]+', text)
        if plain_match:
            try:
                return float(plain_match.group())
            except ValueError:
                pass

        return None  # unparseable → treat as unknown

    @staticmethod
    def _water_percent_similarity(val_a: str, val_b: str,
                                  max_val: float) -> float:
        """
        Similarity for bounded percentage fields (water %).

        Unlike density/GDP which span many orders of magnitude, water %
        is always 0–100 and in practice rarely exceeds ~15–20% for most
        countries. Dividing by the theoretical max (100) would make every
        difference look tiny, so we divide by the actual maximum water %
        observed across the countries in the current dataset.

        Formula:  sim = max(0,  1 − |a − b| / max_val)

        Examples (max_val = 10.0):
          3%  vs 3.5% →  1 − 0.5/10  = 0.95   (very similar)
          3%  vs 10%  →  1 − 7.0/10  = 0.30   (quite different)
          0%  vs 10%  →  1 − 10/10   = 0.00   (maximally different)

        Edge cases:
          Either value is None (unknown)  → 0.0
          max_val is 0 (all countries 0%) → 1.0 (all identical)
        """
        a = SimilarityMatrixBuilder._parse_water_percent(val_a)
        b = SimilarityMatrixBuilder._parse_water_percent(val_b)

        # Unknown value → cannot compare
        if a is None or b is None:
            return 0.0

        # All countries have 0% water → they are all identical
        if max_val <= 0.0:
            return 1.0

        return max(0.0, 1.0 - abs(a - b) / max_val)

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
        Three-level similarity for categorical set-valued features.

        Level 1 — both share at least one widespread value → Jaccard on shared values
        Level 2 — both have only unique values → 0.5 (share the "sovereign" property)
        Level 3 — one has a shared value, other doesn't → 0.0 (maximum separation)
        """
        if not set_a and not set_b:
            return 0.0

        shared_in_a = set_a & shared_values
        shared_in_b = set_b & shared_values

        if shared_in_a and shared_in_b:
            return self._jaccard_similarity(shared_in_a, shared_in_b)

        if not shared_in_a and not shared_in_b:
            return 0.5      # both sovereign/unique — share that property

        return 0.0          # one shared, one unique — maximally different

    def _feature_similarity(self, val_a: str, val_b: str,
                            group: str,
                            shared_by_group: Dict[str, set],
                            water_max_val: float = 0.0) -> float:
        """
        Compute similarity for one feature, routing to the right method.

        Currency         -> three-level on primary ISO code
        Numerical        -> log-ratio similarity (density, area, GDP, ...)
        Water (%)        -> percentage similarity  max(0, 1 - |a-b| / max_val)
                           where max_val is the highest water % in the dataset
        Language / other -> three-level on item sets
        """
        shared = shared_by_group.get(group, set())

        if group == 'currency':
            code_a = self._extract_primary_iso_code(val_a)
            code_b = self._extract_primary_iso_code(val_b)
            if code_a is None or code_b is None:
                return 0.0
            if code_a == code_b:
                return 1.0                          # identical currency
            if code_a not in shared and code_b not in shared:
                return 0.5                          # both sovereign/unique
            return 0.0                              # one shared, one not

        # ── Numerical fields (density, area, population, GDP) ─────────
        if group in self._NUMERICAL_GROUPS:
            return self._numerical_similarity(val_a, val_b)

        # ── Bounded percentage fields (water %) ───────────────────────
        if group in self._PERCENTAGE_GROUPS:
            return self._water_percent_similarity(val_a, val_b, water_max_val)

        set_a = self._extract_item_set(val_a)
        set_b = self._extract_item_set(val_b)
        return self._three_level_similarity(set_a, set_b, shared)

    # ── Dispatcher ──────────────────────────────────────────────────────

    def _selected_feature_similarity(self, country_a: Dict, country_b: Dict,
                                     selected_features: List[str],
                                     shared_by_group: Dict[str, set] = None,
                                     water_max_val: float = 0.0
                                     ) -> Optional[float]:
        """
        Compute feature-level similarity by comparing VALUES, not field titles.

        For each selected feature:
          1. Find its canonical group
          2. Collect ALL field values in that group from each country
          3. Apply the appropriate similarity function for that group type

        Aggregation strategy:
          - Single feature              → return its score directly
          - Multiple NUMERICAL features → return MIN of all scores
            (e.g. density + per capita: a country pair must be close in BOTH
            dimensions to be considered similar; averaging would mask cases
            where one is similar and the other very different, e.g. Monaco
            vs Bangladesh are both dense but have wildly different incomes)
          - Multiple CATEGORICAL features → return MEAN of all scores
            (language + religion: partial overlap in either dimension still
            signals meaningful similarity)
          - Mixed numerical + categorical → return MEAN (default)

        water_max_val: the highest water % in the current dataset, pre-computed
          by the caller so all pairs use the same denominator.

        Returns None only when no features are provided, falling back to TED.
        """
        if not selected_features:
            return None

        fields_a = country_a.get('fields', {}) or {}
        fields_b = country_b.get('fields', {}) or {}
        shared_by_group = shared_by_group or {}

        scores = []
        groups = []
        for field in selected_features:
            val_a = self._collect_group_values(fields_a, field)
            val_b = self._collect_group_values(fields_b, field)
            if val_a is None or val_b is None:
                continue

            norm  = self._normalize_feature_name(field)
            group = self._canonical_group(field) or norm
            groups.append(group)

            scores.append(self._feature_similarity(
                val_a, val_b, group, shared_by_group,
                water_max_val=water_max_val))

        if not scores:
            return None

        # Single feature → return directly
        if len(scores) == 1:
            return scores[0]

        # Multiple features: choose aggregation based on feature types
        # Percentage groups (water) count as numerical for MIN aggregation
        all_numerical = all(
            g in self._NUMERICAL_GROUPS or g in self._PERCENTAGE_GROUPS
            for g in groups
        )
        if all_numerical:
            # MIN: country pair must be close in ALL numerical dimensions
            return min(scores)

        # Default: mean (categorical or mixed)
        return sum(scores) / len(scores)

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

        # Derive shared values using ALL countries in the DB — not just the matrix
        # subset. This ensures currencies/languages used by countries outside the
        # current selection are still counted as "shared" when they should be.
        # e.g. USD must be marked shared even if only 1 USD country is in the matrix.
        all_db_countries = list(self.db.get_country_names())
        shared_by_group = self._derive_shared_codes(
            all_db_countries if all_db_countries else country_names,
            selected_features
        )

        # ── Pre-compute water max value (dynamic denominator) ─────────────────
        # Water % similarity divides by the highest observed value in this
        # dataset so differences are judged against the realistic range,
        # not the theoretical 0-100 range. Computed once here so every pair
        # uses the same denominator (consistent, reproducible scores).
        water_max_val = 0.0
        if selected_features and any(
            self._canonical_group(f) == 'water' for f in selected_features
        ):
            water_vals = []
            for name in country_names:
                doc = self.db.get_country(name)
                if not doc:
                    continue
                fields = doc.get('fields', {}) or {}
                for f in selected_features:
                    if self._canonical_group(f) == 'water':
                        raw = self._collect_group_values(fields, f)
                        if raw:
                            parsed = self._parse_water_percent(raw)
                            if parsed is not None:
                                water_vals.append(parsed)
            water_max_val = max(water_vals) if water_vals else 0.0
            print(f"[Matrix] Water % max value across dataset: {water_max_val:.4f}")

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
                            data_i, data_j, selected_features, shared_by_group,
                            water_max_val=water_max_val
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
                          n_clusters: int = None,
                          linkage: str = 'average',
                          name: str = '',
                          auto_cut: bool = False) -> Dict:
        """Run Agglomerative Hierarchical Clustering on a matrix document.

        Args:
            n_clusters : number of clusters for manual cut, or None for auto.
            auto_cut   : if True, ignore n_clusters and use biggest-gap heuristic.
        """
        countries = matrix_doc['countries']
        sim_m     = matrix_doc['matrix']
        dist_m    = [[similarity_to_distance(sim_m[i][j])
                      for j in range(len(countries))]
                     for i in range(len(countries))]

        # Coordinates are for visualization only; clustering uses dist_m.
        perp   = min(50, max(5, len(countries) // 3))
        tsne   = TSNE2D(perplexity=perp, early_exaggeration=20.0,
                        iterations=1500, seed=42)
        coords = tsne.fit(dist_m)

        # None passed to AgglomerativeClustering triggers auto biggest-gap cut.
        effective_k = None if auto_cut else (n_clusters or 3)
        algo   = AgglomerativeClustering(n_clusters=effective_k, linkage=linkage)
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