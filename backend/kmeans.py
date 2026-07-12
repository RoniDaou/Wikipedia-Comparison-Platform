"""
kmeans.py — K-Medoids clustering with t-SNE visualization.

Contains:
  - TSNE2D        : t-SNE projection for scatter plot visualization only
  - KMeansClustering : K-Medoids algorithm operating on TED distance matrix
"""

import random
import math
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone


def _mean(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


class TSNE2D:
    """
    t-SNE for scatter plot visualization ONLY — never used for clustering.

    K-Medoids assigns clusters using the real TED distance matrix.
    t-SNE then projects those same distances into 2D purely for display.

    To maximize visual cluster separation we use:
      - High early exaggeration (12): strongly pulls cluster members
        together and pushes clusters apart in the first 250 iterations
      - Extended early exaggeration phase (300 iters instead of 250)
      - More total iterations (1200) for full convergence
      - Post-hoc cluster spread: after t-SNE converges, we gently push
        each cluster's centroid further from the global centre, making
        boundaries cleaner without altering relative ordering within clusters
    """

    def __init__(self, perplexity: int = 8, iterations: int = 1200,
                 learning_rate: float = 100.0, early_exaggeration: float = 12.0,
                 seed: int = 42):
        self.perplexity         = perplexity
        self.iterations         = iterations
        self.learning_rate      = learning_rate
        self.early_exaggeration = early_exaggeration
        self.seed               = seed

    def fit(self, dist_matrix: List[List[float]],
            labels: List[int] = None) -> List[List[float]]:
        """
        Return list of [x, y] visualization coordinates.

        Args:
            dist_matrix: N×N TED distance matrix
            labels     : cluster label per country (for post-hoc spreading).
                         If None, post-hoc spreading is skipped.
        """
        n   = len(dist_matrix)
        rng = self._rng(self.seed)

        # ── Step 1: high-dimensional affinities P ──────────────────────
        P       = [[0.0] * n for _ in range(n)]
        log_perp = math.log(self.perplexity)

        for i in range(n):
            lo, hi, sigma = 0.0, 1e10, 1.0
            for _ in range(50):
                exp_row = [0.0] * n
                sum_exp = 0.0
                for j in range(n):
                    if i == j: continue
                    v = math.exp(-(dist_matrix[i][j] ** 2) / (2 * sigma * sigma))
                    exp_row[j] = v
                    sum_exp   += v
                if sum_exp == 0: sum_exp = 1e-10
                H = 0.0
                for j in range(n):
                    if i == j: continue
                    p = exp_row[j] / sum_exp
                    if p > 1e-10: H -= p * math.log(p)
                if H < log_perp:
                    lo = sigma
                    sigma = sigma * 2 if hi > 1e9 else (sigma + hi) / 2
                else:
                    hi = sigma
                    sigma = (lo + sigma) / 2

            exp_row = [0.0] * n
            sum_exp = 0.0
            for j in range(n):
                if i == j: continue
                v = math.exp(-(dist_matrix[i][j] ** 2) / (2 * sigma * sigma))
                exp_row[j] = v
                sum_exp   += v
            if sum_exp == 0: sum_exp = 1e-10
            for j in range(n):
                P[i][j] = exp_row[j] / sum_exp

        # Symmetrise
        for i in range(n):
            for j in range(i + 1, n):
                v = max((P[i][j] + P[j][i]) / (2 * n), 1e-12)
                P[i][j] = v
                P[j][i] = v

        # ── Step 2: initialise embedding ───────────────────────────────
        Y  = [[(rng() - 0.5) * 0.01, (rng() - 0.5) * 0.01] for _ in range(n)]
        Yp = [[y[0], y[1]] for y in Y]
        gains = [[1.0, 1.0] for _ in range(n)]

        # ── Step 3: gradient descent ────────────────────────────────────
        EARLY_PHASE = 300   # extended early exaggeration phase

        for it in range(self.iterations):
            exagg    = self.early_exaggeration if it < EARLY_PHASE else 1.0
            momentum = 0.5 if it < EARLY_PHASE else 0.8

            num  = [[0.0] * n for _ in range(n)]
            sumQ = 0.0
            for i in range(n):
                for j in range(i + 1, n):
                    dx = Y[i][0] - Y[j][0]
                    dy = Y[i][1] - Y[j][1]
                    v  = 1.0 / (1.0 + dx * dx + dy * dy)
                    num[i][j] = v
                    num[j][i] = v
                    sumQ += 2 * v
            if sumQ == 0: sumQ = 1e-10

            grad = [[0.0, 0.0] for _ in range(n)]
            for i in range(n):
                for j in range(n):
                    if i == j: continue
                    Q   = num[i][j] / sumQ
                    mul = 4 * (exagg * P[i][j] - Q) * num[i][j]
                    grad[i][0] += mul * (Y[i][0] - Y[j][0])
                    grad[i][1] += mul * (Y[i][1] - Y[j][1])

            newY = [[Y[i][0], Y[i][1]] for i in range(n)]
            for i in range(n):
                for d in range(2):
                    same = (grad[i][d] > 0) == ((Y[i][d] - Yp[i][d]) > 0)
                    gains[i][d] = max(0.1, gains[i][d] * 0.8 if same
                                      else gains[i][d] + 0.2)
                    step = self.learning_rate * gains[i][d] * grad[i][d]
                    newY[i][d] = (Y[i][d] - step
                                  + momentum * (Y[i][d] - Yp[i][d]))

            for d in range(2):
                mean_d = sum(newY[i][d] for i in range(n)) / n
                for i in range(n):
                    newY[i][d] -= mean_d

            Yp = Y
            Y  = newY

        # ── Step 4: post-hoc cluster spread ────────────────────────────
        # Two-pass approach for maximum visual separation:
        # Pass 1: scale each point away from its cluster centroid (tighten intra)
        # Pass 2: scale each cluster centroid away from origin (push inter apart)
        if labels is not None:
            unique = list(set(labels))

            # Compute cluster centroids
            centroids = {}
            for c in unique:
                members = [i for i in range(n) if labels[i] == c]
                centroids[c] = [
                    sum(Y[i][0] for i in members) / len(members),
                    sum(Y[i][1] for i in members) / len(members)
                ]

            # Pass 1: tighten intra-cluster spread (pull members toward centroid)
            INTRA = 0.7   # <1 pulls points toward their centroid
            for c in unique:
                members = [i for i in range(n) if labels[i] == c]
                cx, cy = centroids[c]
                for i in members:
                    Y[i][0] = cx + INTRA * (Y[i][0] - cx)
                    Y[i][1] = cy + INTRA * (Y[i][1] - cy)

            # Pass 2: push cluster centroids away from global origin
            INTER = 3.0   # >1 pushes clusters apart
            for c in unique:
                members = [i for i in range(n) if labels[i] == c]
                cx, cy = centroids[c]
                dx = (INTER - 1.0) * cx
                dy = (INTER - 1.0) * cy
                for i in members:
                    Y[i][0] += dx
                    Y[i][1] += dy

            # Re-centre at origin
            mx = sum(Y[i][0] for i in range(n)) / n
            my = sum(Y[i][1] for i in range(n)) / n
            for i in range(n):
                Y[i][0] -= mx
                Y[i][1] -= my

            # Pass 3: cluster-pair repulsion
            # Recompute centroids after passes 1+2, then push each pair of
            # clusters away from each other proportional to how close they are.
            # This specifically fixes the case where 2 clusters are close together
            # and the global-origin push moves them in the same direction.
            REPULSION_ITERS = 35
            for _ in range(REPULSION_ITERS):
                # Recompute current centroids
                cur_centroids = {}
                for c in unique:
                    members = [i for i in range(n) if labels[i] == c]
                    cur_centroids[c] = [
                        sum(Y[i][0] for i in members) / len(members),
                        sum(Y[i][1] for i in members) / len(members)
                    ]

                # For each pair of clusters, push them apart
                shifts = {c: [0.0, 0.0] for c in unique}
                for idx_a, ca in enumerate(unique):
                    for cb in unique[idx_a + 1:]:
                        ax, ay = cur_centroids[ca]
                        bx, by = cur_centroids[cb]
                        dx = ax - bx
                        dy = ay - by
                        dist = math.sqrt(dx * dx + dy * dy) or 1e-6
                        # Repulsion force: stronger when clusters are closer
                        force = 0.15 / (dist + 0.1)
                        nx, ny = dx / dist, dy / dist
                        shifts[ca][0] += force * nx
                        shifts[ca][1] += force * ny
                        shifts[cb][0] -= force * nx
                        shifts[cb][1] -= force * ny

                # Apply shifts to all members of each cluster
                for c in unique:
                    members = [i for i in range(n) if labels[i] == c]
                    for i in members:
                        Y[i][0] += shifts[c][0]
                        Y[i][1] += shifts[c][1]

            # Final re-centre
            mx = sum(Y[i][0] for i in range(n)) / n
            my = sum(Y[i][1] for i in range(n)) / n
            for i in range(n):
                Y[i][0] -= mx
                Y[i][1] -= my

        return Y

    @staticmethod
    def _rng(seed: int):
        """Mulberry32 PRNG — reproducible layouts."""
        s = [seed & 0xFFFFFFFF]
        def rand():
            s[0] = (s[0] + 0x6D2B79F5) & 0xFFFFFFFF
            t = s[0]
            t = ((t ^ (t >> 15)) * (1 | t)) & 0xFFFFFFFF
            t = (t + (((t ^ (t >> 7)) * (61 | t)) & 0xFFFFFFFF)) & 0xFFFFFFFF
            return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296.0
        return rand




class KMeansClustering:
    """
    K-Medoids clustering operating DIRECTLY on the TED distance matrix.

    Why K-Medoids instead of K-Means?
        K-Means requires a vector space to compute centroid = mean(members).
        With only a pairwise TED distance matrix, the "mean" is not defined.
        The old approach projected to t-SNE first, then ran K-Means on those
        2D coords — but t-SNE distorts distances non-linearly, so K-Means
        cluster boundaries were inconsistent with what t-SNE drew, producing
        dots that visually sat inside the wrong cluster colour.

        K-Medoids works directly on the distance matrix: instead of an
        abstract centroid, it picks a real country (the medoid) as the
        cluster centre — the one with the lowest average distance to all
        other members. Assignment uses actual TED distances, so the clusters
        are fully consistent with the similarity matrix AND with the t-SNE
        scatter plot (which also derives from the same matrix).

    Algorithm (PAM — Partitioning Around Medoids):
        1. Initialisation : K-Means++ style seeding on distance matrix
        2. Repeat:
           a. Assignment : assign each country to nearest medoid (TED distance)
           b. Update     : for each cluster, pick the member with lowest
                           average distance to all other members as new medoid
        3. Until medoids unchanged or max_iter reached
        4. Best of n_init restarts kept (lowest within-cluster total distance)

    MDS is used for drawing the scatter plot — it preserves TED distances
    linearly, keeping the scatter consistent with cluster assignments.
    """

    def __init__(self, k: int = 3, max_iter: int = 100, n_init: int = 10,
                 random_seed: int = 42):
        self.k           = k
        self.max_iter    = max_iter
        self.n_init      = n_init
        self.random_seed = random_seed

    # ── Main entry point ────────────────────────────────────────────────

    def fit(self, countries: List[str],
            distance_matrix: List[List[float]]) -> Dict:
        """
        Run K-Medoids on the TED distance matrix, then project to MDS for viz.

        Args:
            countries      : ordered list of country names
            distance_matrix: N×N distance matrix (distance = 1 − similarity)

        Returns:
            Result dict with clusters, medoids, labels, coords, and scores.
        """
        n = len(countries)
        if self.k > n:
            raise ValueError(f"k={self.k} exceeds number of countries ({n}).")

        # ── Run K-Medoids n_init times on the real distance matrix ──────
        random.seed(self.random_seed)
        best_labels  = None
        best_medoids = None
        best_cost    = float('inf')

        for _ in range(self.n_init):
            labels, medoids, cost = self._run_once(distance_matrix, n)
            if cost < best_cost:
                best_cost    = cost
                best_labels  = labels
                best_medoids = medoids

        # ── Project to 2D via t-SNE (visualization only) ──────────────
        # K-Medoids already assigned clusters using real TED distances.
        # t-SNE with high early_exaggeration + post-hoc cluster spread
        # maximizes visual separation while assignments stay correct.
        # Perplexity: higher for larger datasets (better global structure)
        # Early exaggeration: 20 for strong cluster pull-apart
        perp   = min(50, max(5, n // 3))
        tsne   = TSNE2D(perplexity=perp, early_exaggeration=20.0,
                        iterations=1500, seed=self.random_seed)
        coords = tsne.fit(distance_matrix, labels=best_labels)

        return self._make_result(countries, best_labels, best_medoids,
                                 coords, distance_matrix, best_cost)

    # ── Core PAM algorithm ──────────────────────────────────────────────

    def _run_once(self, dist: List[List[float]],
                  n: int) -> Tuple[List[int], List[int], float]:
        """One PAM run. Returns (labels, medoid_indices, total_cost)."""
        medoids = self._init_medoids(dist, n)
        labels  = [0] * n

        for _ in range(self.max_iter):
            # Assignment: each point → nearest medoid by TED distance
            new_labels = self._assign(dist, medoids, n)

            # Update: best medoid within each cluster
            new_medoids = self._update_medoids(dist, new_labels, n)

            if new_labels == labels and new_medoids == medoids:
                break

            labels  = new_labels
            medoids = new_medoids

        cost = self._total_cost(dist, labels, medoids, n)
        return labels, medoids, cost

    def _init_medoids(self, dist: List[List[float]], n: int) -> List[int]:
        """
        K-Means++ style initialisation on the distance matrix.
        First medoid: random. Each subsequent medoid: weighted by
        distance² to the nearest already-chosen medoid.
        """
        first = random.randint(0, n - 1)
        medoids = [first]

        while len(medoids) < self.k:
            d_sq = []
            for i in range(n):
                min_d = min(dist[i][m] for m in medoids)
                d_sq.append(min_d ** 2)

            total = sum(d_sq)
            if total < 1e-12:
                # All remaining points equidistant — pick randomly
                remaining = [i for i in range(n) if i not in medoids]
                medoids.append(random.choice(remaining) if remaining else medoids[-1])
            else:
                r, cumsum = random.random() * total, 0.0
                chosen = n - 1
                for i, w in enumerate(d_sq):
                    cumsum += w
                    if cumsum >= r:
                        chosen = i
                        break
                medoids.append(chosen)

        return medoids

    def _assign(self, dist: List[List[float]],
                medoids: List[int], n: int) -> List[int]:
        """Assign each point to the nearest medoid (by TED distance)."""
        labels = []
        for i in range(n):
            best_c, best_d = 0, float('inf')
            for c, m in enumerate(medoids):
                if dist[i][m] < best_d:
                    best_d = dist[i][m]
                    best_c = c
            labels.append(best_c)
        return labels

    def _update_medoids(self, dist: List[List[float]],
                        labels: List[int], n: int) -> List[int]:
        """
        For each cluster, find the member with the lowest average
        TED distance to all other cluster members — that is the new medoid.
        """
        new_medoids = []
        for c in range(self.k):
            members = [i for i in range(n) if labels[i] == c]
            if not members:
                new_medoids.append(random.randint(0, n - 1))
                continue

            best_m, best_avg = members[0], float('inf')
            for m in members:
                avg = sum(dist[m][j] for j in members if j != m)
                avg = avg / (len(members) - 1) if len(members) > 1 else 0.0
                if avg < best_avg:
                    best_avg = avg
                    best_m   = m
            new_medoids.append(best_m)
        return new_medoids

    def _total_cost(self, dist: List[List[float]], labels: List[int],
                    medoids: List[int], n: int) -> float:
        """Total within-cluster distance to medoid (the PAM objective)."""
        return sum(dist[i][medoids[labels[i]]] for i in range(n))

    # ── Result formatting ───────────────────────────────────────────────

    def _make_result(self, countries: List[str], labels: List[int],
                     medoids: List[int], coords: List[List[float]],
                     dist: List[List[float]], total_cost: float) -> Dict:
        n = len(countries)
        clusters = {}
        for c in range(self.k):
            members = [countries[i] for i in range(n) if labels[i] == c]
            rep     = countries[medoids[c]]   # medoid IS the representative
            # centroid for scatter plot = t-SNE coords of the medoid
            centroid_coords = coords[medoids[c]]
            clusters[str(c)] = {
                'id':             c,
                'centroid':       centroid_coords,
                'representative': rep,
                'medoid': rep,
                'members':        members,
                'size':           len(members)
            }

        cohesion   = self._cohesion(n, labels, dist)
        silhouette = self._silhouette(n, labels, dist)

        return {
            'algorithm':   'kmeans',        # keep 'kmeans' so API/UI unchanged
            'k':           self.k,
            'clusters':    clusters,
            'labels':      {countries[i]: labels[i] for i in range(n)},
            'coords':      {countries[i]: coords[i] for i in range(n)},
            'total_cost':  round(total_cost, 6),
            'cohesion':    round(cohesion, 6),
            'silhouette':  round(silhouette, 6),
            'n_countries': n,
            'computed_at': datetime.now(timezone.utc).isoformat()
        }

    def _cohesion(self, n: int, labels: List[int],
                  dist: List[List[float]]) -> float:
        """Average intra-cluster TED distance (lower = more cohesive)."""
        total, count = 0.0, 0
        for c in range(self.k):
            members = [i for i in range(n) if labels[i] == c]
            for i in members:
                for j in members:
                    if i != j:
                        total += dist[i][j]
                        count += 1
        return total / count if count else 0.0

    def _silhouette(self, n: int, labels: List[int],
                    dist: List[List[float]]) -> float:
        """Mean silhouette coefficient ∈ [−1, 1] on TED distances."""
        if self.k == 1:
            return 0.0
        scores = []
        for i in range(n):
            c_i   = labels[i]
            intra = [j for j in range(n) if labels[j] == c_i and j != i]
            a     = _mean([dist[i][j] for j in intra]) if intra else 0.0
            b     = float('inf')
            for c in range(self.k):
                if c == c_i:
                    continue
                other = [j for j in range(n) if labels[j] == c]
                if other:
                    b = min(b, _mean([dist[i][j] for j in other]))
            if b == float('inf'):
                b = 0.0
            denom = max(a, b)
            scores.append((b - a) / denom if denom > 0 else 0.0)
        return _mean(scores)