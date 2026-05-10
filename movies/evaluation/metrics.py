"""
Evaluation metrics for recommendation systems.

Primary: RMSE, MAE, response time, coverage
Secondary: Precision@K, Recall@K, NDCG@K, F1-Score, diversity
"""

import math
import time
from collections import defaultdict

import numpy as np


def rmse(predictions, actuals):
    """Root Mean Squared Error."""
    predictions = np.array(predictions, dtype=float)
    actuals = np.array(actuals, dtype=float)
    return float(np.sqrt(np.mean((predictions - actuals) ** 2)))


def mae(predictions, actuals):
    """Mean Absolute Error."""
    predictions = np.array(predictions, dtype=float)
    actuals = np.array(actuals, dtype=float)
    return float(np.mean(np.abs(predictions - actuals)))


def precision_at_k(recommended, relevant, k=10):
    """
    Precision@K: fraction of top-K recommendations that are relevant.

    Args:
        recommended: list of recommended movie IDs (ordered by score)
        relevant: set of relevant movie IDs (e.g. movies rated >= 3.5)
        k: cutoff
    """
    top_k = recommended[:k]
    if not top_k:
        return 0.0
    hits = len(set(top_k) & set(relevant))
    return hits / k


def recall_at_k(recommended, relevant, k=10):
    """
    Recall@K: fraction of relevant items that appear in top-K.

    Args:
        recommended: list of recommended movie IDs
        relevant: set of relevant movie IDs
        k: cutoff
    """
    if not relevant:
        return 0.0
    top_k = recommended[:k]
    hits = len(set(top_k) & set(relevant))
    return hits / len(relevant)


def f1_at_k(recommended, relevant, k=10):
    """F1-Score@K: harmonic mean of Precision@K and Recall@K."""
    p = precision_at_k(recommended, relevant, k)
    r = recall_at_k(recommended, relevant, k)
    if p + r == 0:
        return 0.0
    return 2 * p * r / (p + r)


def ndcg_at_k(recommended, relevant, k=10):
    """
    Normalised Discounted Cumulative Gain at K.

    Args:
        recommended: list of recommended movie IDs (ordered)
        relevant: set of relevant movie IDs
        k: cutoff
    """
    top_k = recommended[:k]

    # DCG
    dcg = 0.0
    for i, item in enumerate(top_k):
        if item in relevant:
            dcg += 1.0 / math.log2(i + 2)  # i+2 because log2(1)=0

    # Ideal DCG
    ideal_hits = min(len(relevant), k)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_hits))

    if idcg == 0:
        return 0.0
    return dcg / idcg


def catalogue_coverage(all_recommended, total_movies):
    """
    Fraction of the entire catalogue that appears in recommendations.

    Args:
        all_recommended: set of all movie IDs recommended across all users
        total_movies: total number of movies in the catalogue
    """
    if total_movies == 0:
        return 0.0
    return len(all_recommended) / total_movies


def diversity(recommendations, genre_map):
    """
    Intra-list diversity: average pairwise genre dissimilarity within a recommendation list.

    Args:
        recommendations: list of movie IDs
        genre_map: dict of {movie_id: set of genres}
    """
    if len(recommendations) < 2:
        return 0.0

    total_dissimilarity = 0.0
    pairs = 0

    for i in range(len(recommendations)):
        for j in range(i + 1, len(recommendations)):
            genres_i = genre_map.get(recommendations[i], set())
            genres_j = genre_map.get(recommendations[j], set())

            if not genres_i and not genres_j:
                dissimilarity = 0.0
            else:
                union = genres_i | genres_j
                intersection = genres_i & genres_j
                dissimilarity = 1.0 - (len(intersection) / len(union)) if union else 0.0

            total_dissimilarity += dissimilarity
            pairs += 1

    return total_dissimilarity / pairs if pairs > 0 else 0.0


def measure_response_time(recommend_fn, *args, **kwargs):
    """Measure recommendation generation time in milliseconds."""
    start = time.perf_counter()
    result = recommend_fn(*args, **kwargs)
    elapsed_ms = (time.perf_counter() - start) * 1000
    return result, elapsed_ms


def compute_all_metrics(recommended_per_user, relevant_per_user, predictions=None,
                        actuals=None, all_movie_ids=None, genre_map=None, k=10):
    """
    Compute all evaluation metrics.

    Args:
        recommended_per_user: dict of {user_id: [movie_ids ordered by score]}
        relevant_per_user: dict of {user_id: set of relevant movie_ids}
        predictions: list of predicted ratings (for RMSE/MAE)
        actuals: list of actual ratings (for RMSE/MAE)
        all_movie_ids: set of all movie IDs (for coverage)
        genre_map: dict of {movie_id: set of genres} (for diversity)
        k: cutoff for ranking metrics

    Returns:
        dict of metric_name -> value
    """
    results = {}

    # Rating prediction metrics
    if predictions is not None and actuals is not None:
        results["RMSE"] = rmse(predictions, actuals)
        results["MAE"] = mae(predictions, actuals)

    # Ranking metrics (averaged over users)
    precisions, recalls, f1s, ndcgs, diversities = [], [], [], [], []

    all_recommended_items = set()

    for user_id in recommended_per_user:
        recs = recommended_per_user[user_id]
        rels = relevant_per_user.get(user_id, set())

        precisions.append(precision_at_k(recs, rels, k))
        recalls.append(recall_at_k(recs, rels, k))
        f1s.append(f1_at_k(recs, rels, k))
        ndcgs.append(ndcg_at_k(recs, rels, k))

        all_recommended_items.update(recs[:k])

        if genre_map:
            diversities.append(diversity(recs[:k], genre_map))

    results[f"Precision@{k}"] = float(np.mean(precisions)) if precisions else 0.0
    results[f"Recall@{k}"] = float(np.mean(recalls)) if recalls else 0.0
    results[f"F1@{k}"] = float(np.mean(f1s)) if f1s else 0.0
    results[f"NDCG@{k}"] = float(np.mean(ndcgs)) if ndcgs else 0.0

    if all_movie_ids:
        results["Coverage"] = catalogue_coverage(all_recommended_items, len(all_movie_ids))

    if diversities:
        results["Diversity"] = float(np.mean(diversities))

    return results
