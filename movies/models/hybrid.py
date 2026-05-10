"""
Hybrid Recommendation Model.
Combines collaborative, content-based, and behaviour-based filtering.

Default weights: 0.4 * collaborative + 0.3 * content + 0.3 * behaviour
Supports grid search weight optimisation on validation set.
"""

import logging
from itertools import product

import numpy as np

from config.settings import HYBRID_WEIGHTS, WEIGHT_GRID, TOP_K

logger = logging.getLogger(__name__)


class HybridRecommender:
    """Weighted hybrid ensemble of three recommendation approaches."""

    def __init__(self, collaborative, content_based, behavior):
        """
        Args:
            collaborative: CollaborativeFilter instance
            content_based: ContentBasedFilter instance
            behavior: BehaviorFilter instance
        """
        self.collaborative = collaborative
        self.content_based = content_based
        self.behavior = behavior
        self.weights = HYBRID_WEIGHTS.copy()

    def _normalise_scores(self, recommendations):
        """Min-max normalise scores to [0, 1] range.

        H3: If all input scores are identical (common for cold-start models
        returning all zeros), treat this model as contributing no useful signal
        — emit 0.0 instead of 0.5 so it doesn't falsely boost items.
        If scores are identical but non-zero (rare), preserve a constant 1.0
        so ranking within this model's candidates is unchanged.
        """
        if not recommendations:
            return []

        scores = [r["score"] for r in recommendations]
        min_s = min(scores)
        max_s = max(scores)
        score_range = max_s - min_s

        if score_range == 0:
            constant = 0.0 if max_s == 0 else 1.0
            return [
                {"movieId": r["movieId"], "score": constant}
                for r in recommendations
            ]

        return [
            {
                "movieId": r["movieId"],
                "score": (r["score"] - min_s) / score_range,
            }
            for r in recommendations
        ]

    def recommend(self, user_id, user_ratings, all_movie_ids, spark=None, n=20):
        """
        Generate hybrid recommendations for a user.

        Args:
            user_id: target user ID
            user_ratings: list of dicts {'movieId': int, 'rating': float}
            all_movie_ids: list of all candidate movie IDs
            spark: SparkSession (needed for collaborative filtering)
            n: number of recommendations to return
        """
        # Get recommendations from each model
        collab_recs = []
        content_recs = []
        behavior_recs = []

        # Collaborative filtering
        try:
            if spark is not None and self.collaborative.model is not None:
                collab_spark_df = self.collaborative.recommend_for_user(user_id, n=n * 2)
                if collab_spark_df is not None:
                    collab_recs = [
                        {"movieId": row["movieId"], "score": float(row["score"])}
                        for row in collab_spark_df.collect()
                    ]
        except Exception as e:
            logger.warning(f"Collaborative filtering failed for user {user_id}: {e}")

        # Content-based filtering
        try:
            content_recs = self.content_based.recommend_for_user(
                user_ratings, n=n * 2, exclude_rated=True
            )
        except Exception as e:
            logger.warning(f"Content-based filtering failed for user {user_id}: {e}")

        # Behavior-based filtering
        try:
            behavior_recs = self.behavior.recommend_for_user(
                user_id, all_movie_ids, n=n * 2
            )
        except Exception as e:
            logger.warning(f"Behaviour filtering failed for user {user_id}: {e}")

        # Normalise scores
        collab_recs = self._normalise_scores(collab_recs)
        content_recs = self._normalise_scores(content_recs)
        behavior_recs = self._normalise_scores(behavior_recs)

        # Build score maps
        collab_map = {r["movieId"]: r["score"] for r in collab_recs}
        content_map = {r["movieId"]: r["score"] for r in content_recs}
        behavior_map = {r["movieId"]: r["score"] for r in behavior_recs}

        # Combine all candidate movie IDs
        all_candidates = set(collab_map.keys()) | set(content_map.keys()) | set(behavior_map.keys())

        # Compute hybrid score
        hybrid_scores = []
        for movie_id in all_candidates:
            score = (
                self.weights["collaborative"] * collab_map.get(movie_id, 0.0)
                + self.weights["content_based"] * content_map.get(movie_id, 0.0)
                + self.weights["behavior"] * behavior_map.get(movie_id, 0.0)
            )
            hybrid_scores.append({"movieId": movie_id, "score": score})

        # Sort and return top-N
        hybrid_scores.sort(key=lambda x: x["score"], reverse=True)
        return hybrid_scores[:n]

    def optimise_weights(self, validation_data, user_ratings_map, all_movie_ids,
                         spark=None, metric_fn=None):
        """
        Grid search over weight combinations to find optimal hybrid weights.

        Args:
            validation_data: list of dicts {'userId', 'movieId', 'rating'}
            user_ratings_map: dict of {user_id: [{'movieId', 'rating'}, ...]}
            all_movie_ids: list of all movie IDs
            spark: SparkSession
            metric_fn: function(predictions, actuals) -> float (lower is better)
        """
        logger.info("Starting hybrid weight optimisation via grid search...")

        best_weights = self.weights.copy()
        best_score = float("inf")

        collab_range = WEIGHT_GRID["collaborative"]
        content_range = WEIGHT_GRID["content_based"]
        behavior_range = WEIGHT_GRID["behavior"]

        for w_c, w_cb, w_b in product(collab_range, content_range, behavior_range):
            # Weights must sum to 1.0
            if abs(w_c + w_cb + w_b - 1.0) > 0.01:
                continue

            self.weights = {
                "collaborative": w_c,
                "content_based": w_cb,
                "behavior": w_b,
            }

            # Evaluate on validation set (sample for speed)
            sample_users = list(set(d["userId"] for d in validation_data))[:100]
            predictions = []
            actuals = []

            for user_id in sample_users:
                user_val = [d for d in validation_data if d["userId"] == user_id]
                user_train = user_ratings_map.get(user_id, [])

                if not user_train:
                    continue

                recs = self.recommend(
                    user_id, user_train, all_movie_ids, spark=spark, n=TOP_K
                )
                rec_ids = {r["movieId"] for r in recs}

                for item in user_val:
                    predictions.append(1 if item["movieId"] in rec_ids else 0)
                    actuals.append(1 if item["rating"] >= 3.5 else 0)

            if metric_fn and predictions:
                score = metric_fn(predictions, actuals)
            elif predictions:
                # Default: use hit rate (higher is better, so negate)
                hits = sum(1 for p, a in zip(predictions, actuals) if p == 1 and a == 1)
                score = -hits / max(len(actuals), 1)
            else:
                score = float("inf")

            logger.info(f"Weights ({w_c}, {w_cb}, {w_b}) -> score: {score:.4f}")

            if score < best_score:
                best_score = score
                best_weights = self.weights.copy()

        self.weights = best_weights
        logger.info(f"Optimal weights: {best_weights} (score: {best_score:.4f})")
        return best_weights
