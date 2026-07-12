"""
agglomerative.py — Agglomerative hierarchical clustering for TED matrices.

Pure-Python agglomerative clustering over a precomputed distance matrix.
The algorithm never recomputes TED; it consumes the cached similarity matrix
built by clustering.py and merges countries using pairwise TED distance.
"""

from datetime import datetime, timezone
from typing import Dict, List, Tuple
import time


def _mean(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


class AgglomerativeClustering:
    """
    Bottom-up hierarchical clustering over a precomputed distance matrix.

    Workflow:
      1. Start with each country as its own cluster.
      2. Repeatedly merge the two closest clusters.
      3. Always runs to completion (one root cluster) — cut is applied after.

    Cut modes:
      - auto (n_clusters=None): biggest-gap heuristic automatically selects
        the cut point where the largest jump in merge distances occurs.
        This is the parameter-free approach: the dendrogram decides.
      - manual (n_clusters=int): cut at exactly that many clusters.

    Supported linkage modes:
      - average  : mean pairwise distance between cluster members
      - single   : minimum pairwise distance
      - complete : maximum pairwise distance
    """

    def __init__(self, n_clusters: int = None, linkage: str = "average"):
        self.n_clusters = n_clusters  # None = auto biggest-gap
        self.linkage = (linkage or "average").lower()
        if self.linkage not in {"average", "single", "complete"}:
            raise ValueError('linkage must be "average", "single", or "complete"')

    # ── Biggest-gap auto cut ────────────────────────────────────────────────

    @staticmethod
    def _auto_cut(merge_history: List[Dict], n: int) -> int:
        """
        Adaptive auto-cut based on the distance distribution of the merge history.

        Empirically derived from 6 real similarity matrices covering:
        currency, language, full TED, per-capita GDP, and density.
        Four matrix types are detected and handled with targeted strategies.

        ── TYPE 1: SPARSE / DISCRETE ────────────────────────────────────────
        Signature : <= 6 distinct distance values in the merge history.
        Examples  : Currency  distances in {0.0, 0.5, 1.0}
                    Language  distances in {0.0, 0.5, 0.667, 1.0}
        Strategy  : LAST occurrence of the maximum gap.
                    The merge history has a clear tier structure:
                      • dist=0.0  →  identical (same currency / language family)
                      • dist=0.5  →  both sovereign/unique
                      • dist=1.0  →  incompatible groups (forced merge)
                    Taking the LAST max gap lets all same-tier merges complete
                    before cutting → EUR bloc, Romance languages, etc.

        ── TYPE 2: NARROW CONTINUOUS ────────────────────────────────────────
        Signature : > 6 distinct values  AND  dist_range < 0.20
        Examples  : Full TED on a single region (Middle East TED: 0.16–0.21)
                    All countries are structurally similar; no gap stands out.
        Strategy  : Mean split — cut at the mean merge distance.
                    Splits the dataset into two halves by similarity, separating
                    sub-groups within an otherwise homogeneous set.

        ── TYPE 3: MEDIUM CONTINUOUS ────────────────────────────────────────
        Signature : > 6 distinct values  AND  0.20 <= dist_range < 0.30
        Examples  : Density (Middle East actual merge range: 0.00–0.26)
                    Clear structural break exists (dense vs sparse countries).
        Strategy  : Last gap with z-score > 1.5, no k guard.
                    The z-score threshold finds the dominant structural break.
                    Fallback to mean split if no significant gap found.

        ── TYPE 4: WIDE CONTINUOUS ──────────────────────────────────────────
        Signature : > 6 distinct values  AND  dist_range >= 0.30
        Examples  : Per-capita GDP (Americas: 0.005–0.367)
                    Full TED on globally diverse datasets
        Strategy  : Last gap with z-score > 1.5, with k >= 3 guard.
                    Identifies the last major structural jump (e.g. Haiti as
                    income outlier). If result is too coarse (k < 3), falls
                    back to 65th-percentile split for more granular clusters.

        Special case: all gaps zero → sqrt(n) clusters fallback.
        """
        import math, statistics

        if len(merge_history) < 2:
            return len(merge_history)

        distances = [m["distance"] for m in merge_history]
        gaps      = [distances[i + 1] - distances[i]
                     for i in range(len(distances) - 1)]
        max_gap   = max(gaps)

        # ── All gaps zero → perfectly uniform distances ───────────────────
        if max_gap < 1e-9:
            return max(0, n - max(2, round(math.sqrt(n))))

        n_merges      = len(merge_history)
        distinct_vals = len(set(round(d, 4) for d in distances))
        dist_range    = distances[-1] - distances[0]

        # ── Helper: last z > 1.5 gap ──────────────────────────────────────
        def _last_significant_gap():
            if len(gaps) < 2:
                return None
            mean_g = statistics.mean(gaps)
            std_g  = statistics.stdev(gaps)
            if std_g == 0:
                return None
            sig = [i for i, g in enumerate(gaps)
                   if (g - mean_g) / std_g > 1.5]
            return sig[-1] if sig else None

        # ── Helper: mean split ────────────────────────────────────────────
        def _mean_split():
            mean_d = statistics.mean(distances)
            kept   = sum(1 for d in distances if d <= mean_d)
            return max(1, min(kept, n_merges - 1))

        # ── Helper: percentile split ──────────────────────────────────────
        def _pct_split(pct=0.65):
            idx  = int(pct * len(distances))
            thr  = distances[min(idx, len(distances) - 1)]
            kept = sum(1 for d in distances if d <= thr)
            return max(1, min(kept, n_merges - 1))

        # ── TYPE 1: SPARSE ────────────────────────────────────────────────
        # Use the LAST gap that is >= 50% of the maximum gap.
        # This handles multi-tier sparse matrices (e.g. language with gaps
        # {0.5, 0.333, 0.167}): we want the last MAJOR gap (0.333 at the
        # 0.667→1.0 boundary), not the last gap of any size.
        # For binary/two-tier matrices (currency: gaps {0.5}), only one
        # gap qualifies and it gives the correct last-tier boundary.
        if distinct_vals <= 6:
            threshold = max_gap * 0.5
            sig_sparse = [(g, i) for i, g in enumerate(gaps)
                          if g >= threshold]
            if sig_sparse:
                last_idx = max(sig_sparse, key=lambda x: x[1])[1]
                return last_idx + 1
            # Fallback: absolute last max gap
            rev      = gaps[::-1]
            last_idx = len(gaps) - 1 - rev.index(max_gap)
            return last_idx + 1

        # ── TYPE 2: NARROW CONTINUOUS ─────────────────────────────────────
        if dist_range < 0.20:
            return _mean_split()

        # ── TYPE 3: MEDIUM CONTINUOUS ─────────────────────────────────────
        if dist_range < 0.30:
            sig_idx = _last_significant_gap()
            if sig_idx is not None:
                return sig_idx + 1
            return _mean_split()

        # ── TYPE 4: WIDE CONTINUOUS ───────────────────────────────────────
        sig_idx = _last_significant_gap()
        if sig_idx is not None:
            cut = sig_idx + 1
            if n - cut >= 3:
                return cut
        # k < 3 or no significant gap → 65th-percentile split
        return _pct_split(0.65)

    def fit(self, countries: List[str], distance_matrix: List[List[float]],
            coords: List[List[float]] = None) -> Dict:
        """
        Run agglomerative clustering and return a UI/API-compatible result.

        Args:
            countries: ordered country names matching the matrix.
            distance_matrix: N x N TED distance matrix, where lower is closer.
            coords: optional 2D visualization coordinates.
        """
        n = len(countries)
        if n == 0:
            raise ValueError("Cannot cluster an empty country list.")
        if self.n_clusters is not None:
            if self.n_clusters < 1:
                raise ValueError("n_clusters must be >= 1")
            if self.n_clusters > n:
                raise ValueError(f"n_clusters={self.n_clusters} exceeds number of countries ({n}).")

        started = time.perf_counter()
        clusters = {i: [i] for i in range(n)}
        next_cluster_id = n
        merge_history = []

        # Always run to completion — agglomerative merges everything.
        # The cut is decided after the full hierarchy is built.
        while len(clusters) > 1:
            best_pair = None
            best_distance = float("inf")
            cluster_ids = sorted(clusters.keys())

            for pos_a, cluster_a in enumerate(cluster_ids):
                for cluster_b in cluster_ids[pos_a + 1:]:
                    dist = self._cluster_distance(
                        clusters[cluster_a], clusters[cluster_b], distance_matrix
                    )
                    if dist < best_distance:
                        best_distance = dist
                        best_pair = (cluster_a, cluster_b)

            if best_pair is None:
                break

            a, b = best_pair
            merged_members = clusters[a] + clusters[b]
            merge_history.append({
                "step": len(merge_history) + 1,
                "left": int(a),
                "right": int(b),
                "distance": round(best_distance, 6),
                "similarity": round(1.0 - best_distance, 6),
                "size": len(merged_members),
                "members": [countries[i] for i in merged_members],
            })

            del clusters[a]
            del clusters[b]
            clusters[next_cluster_id] = merged_members
            next_cluster_id += 1

        # ── Determine cut point ────────────────────────────────────────────
        if self.n_clusters is None:
            # Auto mode: biggest gap heuristic
            cut_step = self._auto_cut(merge_history, n)
            auto_cut = True
        else:
            # Manual mode: cut at exactly n_clusters
            cut_step = n - self.n_clusters
            auto_cut = False

        # ── Replay merge history to recover clusters at cut point ──────────
        # Re-simulate the merges up to cut_step to get the actual cluster sets.
        replay_clusters = {i: [i] for i in range(n)}
        replay_next_id = n
        for merge in merge_history[:cut_step]:
            a_id = int(merge["left"])
            b_id = int(merge["right"])
            merged = replay_clusters.pop(a_id, []) + replay_clusters.pop(b_id, [])
            replay_clusters[replay_next_id] = merged
            replay_next_id += 1

        final_clusters = list(replay_clusters.values())
        final_clusters.sort(key=lambda members: (min(members), len(members)))
        n_clusters_actual = len(final_clusters)

        labels = [0] * n
        for cluster_idx, members in enumerate(final_clusters):
            for member_idx in members:
                labels[member_idx] = cluster_idx

        return self._make_result(
            countries=countries,
            labels=labels,
            final_clusters=final_clusters,
            coords=coords,
            distance_matrix=distance_matrix,
            merge_history=merge_history,
            cut_step=cut_step,
            n_clusters_actual=n_clusters_actual,
            auto_cut=auto_cut,
            runtime_ms=round((time.perf_counter() - started) * 1000, 3),
        )

    def _cluster_distance(self, members_a: List[int], members_b: List[int],
                          dist: List[List[float]]) -> float:
        values = [dist[i][j] for i in members_a for j in members_b]
        if self.linkage == "single":
            return min(values)
        if self.linkage == "complete":
            return max(values)
        return _mean(values)

    def _representative(self, members: List[int], dist: List[List[float]]) -> int:
        """Return the medoid-like representative of a cluster."""
        best_member = members[0]
        best_avg = float("inf")
        for candidate in members:
            avg = _mean([dist[candidate][other] for other in members if other != candidate])
            if avg < best_avg:
                best_avg = avg
                best_member = candidate
        return best_member

    def _make_result(self, countries: List[str], labels: List[int],
                     final_clusters: List[List[int]], coords: List[List[float]],
                     distance_matrix: List[List[float]],
                     merge_history: List[Dict],
                     cut_step: int,
                     runtime_ms: float,
                     n_clusters_actual: int = None,
                     auto_cut: bool = False) -> Dict:
        n = len(countries)
        if coords is None:
            coords = [[0.0, 0.0] for _ in range(n)]

        clusters = {}
        for cluster_idx, members in enumerate(final_clusters):
            rep_idx = self._representative(members, distance_matrix)
            centroid = [
                _mean([coords[i][0] for i in members]),
                _mean([coords[i][1] for i in members]),
            ]
            clusters[str(cluster_idx)] = {
                "id": cluster_idx,
                "centroid": centroid,
                "representative": countries[rep_idx],
                "members": [countries[i] for i in members],
                "size": len(members),
            }

        cohesion = self._cohesion(n, labels, distance_matrix)
        silhouette = self._silhouette(n, labels, distance_matrix)

        n_clusters_out = n_clusters_actual if n_clusters_actual is not None else (self.n_clusters or len(final_clusters))
        return {
            "algorithm": "agglomerative",
            "n_clusters": n_clusters_out,
            "n_clusters_requested": self.n_clusters,
            "auto_cut": auto_cut,
            "linkage": self.linkage,
            "clusters": clusters,
            "labels": {countries[i]: labels[i] for i in range(n)},
            "coords": {countries[i]: coords[i] for i in range(n)},
            "cohesion": round(cohesion, 6),
            "silhouette": round(silhouette, 6),
            "merge_history": merge_history,
            "dendrogram": merge_history,
            "cut_step": cut_step,
            "runtime_ms": runtime_ms,
            "n_countries": n,
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }

    def _cohesion(self, n: int, labels: List[int], dist: List[List[float]]) -> float:
        total, count = 0.0, 0
        for cluster_id in sorted(set(labels)):
            members = [i for i in range(n) if labels[i] == cluster_id]
            for i in members:
                for j in members:
                    if i != j:
                        total += dist[i][j]
                        count += 1
        return total / count if count else 0.0

    def _silhouette(self, n: int, labels: List[int], dist: List[List[float]]) -> float:
        unique_labels = sorted(set(labels))
        if len(unique_labels) <= 1:
            return 0.0

        scores = []
        for i in range(n):
            own_label = labels[i]
            own_members = [j for j in range(n) if labels[j] == own_label and j != i]
            a = _mean([dist[i][j] for j in own_members]) if own_members else 0.0

            b = float("inf")
            for other_label in unique_labels:
                if other_label == own_label:
                    continue
                other_members = [j for j in range(n) if labels[j] == other_label]
                if other_members:
                    b = min(b, _mean([dist[i][j] for j in other_members]))

            if b == float("inf"):
                b = 0.0
            denom = max(a, b)
            scores.append((b - a) / denom if denom > 0 else 0.0)

        return _mean(scores)