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

    # ── Public interface ───────────────────────────────────────────────

    def build(self,
              country_names: List[str],
              progress_callback=None) -> Dict:
        """
        Compute the full N×N similarity matrix and persist it to MongoDB.

        Only the upper triangle is computed (symmetric); diagonal = 1.0.

        Args:
            country_names    : ordered list of country names
            progress_callback: optional callable(done, total, pair_info)

        Returns:
            The stored matrix document (dict).
        """
        n = len(country_names)
        matrix = [[0.0] * n for _ in range(n)]

        # Diagonal
        for i in range(n):
            matrix[i][i] = 1.0

        total_pairs = n * (n - 1) // 2
        done = 0

        for i in range(n):
            data_i = self.db.get_country(country_names[i])
            if data_i:
                data_i.pop('_id', None)

            for j in range(i + 1, n):
                sim = 0.0
                try:
                    data_j = self.db.get_country(country_names[j])
                    if data_j:
                        data_j.pop('_id', None)

                    if data_i and data_j:
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
            'built_at':  datetime.now(timezone.utc).isoformat()
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
            'built_at':  datetime.now(timezone.utc).isoformat()
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
                               progress_callback=None) -> Dict:
        """
        Build a brand-new similarity matrix and save it to the DB.
        Always creates a new document — never overwrites.

        Args:
            country_names    : list to include; None = all in DB
            name             : human-readable label for this matrix
            progress_callback: callable(done, total, pair_info)

        Returns:
            The saved matrix doc (includes '_id' as string).
        """
        names = country_names or sorted(self.db.get_country_names())
        doc   = self.builder.build(names, progress_callback)
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