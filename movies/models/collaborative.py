"""
Collaborative Filtering using Alternating Least Squares (ALS).
Weight: 40% in the hybrid model.

Uses Spark MLlib for distributed matrix factorisation on the MovieLens 25M dataset.
"""

import logging
import os

from pyspark.ml.evaluation import RegressionEvaluator
from pyspark.ml.recommendation import ALS, ALSModel
from pyspark.sql import SparkSession, functions as F

from config.settings import ALS_PARAMS, MODEL_DIR

logger = logging.getLogger(__name__)

COLLABORATIVE_MODEL_PATH = os.path.join(MODEL_DIR, "als_model")


class CollaborativeFilter:
    """ALS-based collaborative filtering recommender."""

    def __init__(self, spark):
        self.spark = spark
        self.model = None
        self.popularity_df = None  # Fallback for cold-start users

    def train(self, train_df):
        """Train ALS model on training data."""
        logger.info("Training ALS collaborative filtering model...")

        als = ALS(
            rank=ALS_PARAMS["rank"],
            maxIter=ALS_PARAMS["max_iter"],
            regParam=ALS_PARAMS["reg_param"],
            coldStartStrategy=ALS_PARAMS["cold_start_strategy"],
            userCol=ALS_PARAMS["user_col"],
            itemCol=ALS_PARAMS["item_col"],
            ratingCol=ALS_PARAMS["rating_col"],
            seed=42,
        )

        self.model = als.fit(train_df)

        # L5: Use configured column names instead of hardcoded strings so
        # changing ALS_PARAMS doesn't silently break popularity fallback.
        item_col = ALS_PARAMS["item_col"]
        rating_col = ALS_PARAMS["rating_col"]

        self.popularity_df = (
            train_df.groupBy(item_col)
            .agg(
                F.mean(rating_col).alias("avg_rating"),
                F.count(rating_col).alias("rating_count"),
            )
            .withColumn(
                "popularity_score",
                F.col("avg_rating") * F.log1p(F.col("rating_count")),
            )
            .orderBy(F.col("popularity_score").desc())
        )

        logger.info("ALS model training complete.")

    def predict(self, user_movie_df):
        """Predict ratings for user-movie pairs."""
        if self.model is None:
            raise RuntimeError("Model not trained. Call train() first.")
        return self.model.transform(user_movie_df)

    def recommend_for_user(self, user_id, n=20):
        """Generate top-N recommendations for a single user."""
        if self.model is None:
            raise RuntimeError("Model not trained. Call train() first.")

        user_df = self.spark.createDataFrame([(user_id,)], ["userId"])
        try:
            recs = self.model.recommendForUserSubset(user_df, n)
            if recs.count() == 0:
                return self._cold_start_recommendations(n)
            # Flatten recommendations
            return (
                recs.select(F.explode("recommendations").alias("rec"))
                .select(
                    F.lit(user_id).alias("userId"),
                    F.col("rec.movieId"),
                    F.col("rec.rating").alias("score"),
                )
            )
        except Exception as e:
            logger.warning(f"ALS prediction failed for user {user_id}: {e}")
            return self._cold_start_recommendations(n)

    def recommend_for_all_users(self, n=20):
        """Generate top-N recommendations for all users."""
        if self.model is None:
            raise RuntimeError("Model not trained. Call train() first.")
        return self.model.recommendForAllUsers(n)

    def _cold_start_recommendations(self, n):
        """Return popular movies as fallback."""
        logger.info("Using popularity-based cold-start fallback.")
        return self.popularity_df.select(
            F.col("movieId"),
            F.col("popularity_score").alias("score"),
        ).limit(n)

    def evaluate(self, test_df):
        """Evaluate model using RMSE on test data."""
        predictions = self.predict(test_df)
        evaluator = RegressionEvaluator(
            metricName="rmse",
            labelCol="rating",
            predictionCol="prediction",
        )
        rmse = evaluator.evaluate(predictions.dropna(subset=["prediction"]))
        logger.info(f"Collaborative Filtering RMSE: {rmse:.4f}")
        return rmse

    def save(self, path=None):
        """Save trained ALS model."""
        path = path or COLLABORATIVE_MODEL_PATH
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.model.save(path)
        logger.info(f"ALS model saved to {path}")

    def load(self, path=None):
        """Load a previously trained ALS model."""
        path = path or COLLABORATIVE_MODEL_PATH
        self.model = ALSModel.load(path)
        logger.info(f"ALS model loaded from {path}")
