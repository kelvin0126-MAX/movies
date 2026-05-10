"""
Evaluation orchestrator.
Runs all 4 models across all 5 splitting strategies and collects metrics.
Produces the core dissertation results: 20 evaluation runs.
"""

import json
import logging
import os
import time
from datetime import datetime

import pandas as pd

from config.settings import (
    PROCESSED_DATA_DIR,
    SPLITS_DIR,
    SPLITTING_STRATEGIES,
    TOP_K,
)
from evaluation.metrics import compute_all_metrics

logger = logging.getLogger(__name__)

RESULTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results"
)


class Evaluator:
    """Orchestrates model evaluation across splitting strategies."""

    def __init__(self, spark=None):
        self.spark = spark
        self.results = []

    def load_split(self, strategy_name):
        """Load train/val/test parquet for a splitting strategy."""
        split_dir = os.path.join(SPLITS_DIR, strategy_name)
        train = self.spark.read.parquet(os.path.join(split_dir, "train"))
        val = self.spark.read.parquet(os.path.join(split_dir, "validation"))
        test = self.spark.read.parquet(os.path.join(split_dir, "test"))
        return train, val, test

    def evaluate_model(self, model_name, recommend_fn, test_data, all_movie_ids,
                       genre_map=None, predict_fn=None):
        """
        Evaluate a single model on test data.

        Args:
            model_name: string identifier
            recommend_fn: function(user_id) -> list of recommended movie IDs
            test_data: list of dicts {'userId', 'movieId', 'rating'}
            all_movie_ids: set of all movie IDs
            genre_map: dict for diversity metric
            predict_fn: optional function(user_id, movie_id) -> predicted rating
        """
        # Group test data by user
        user_relevant = {}
        user_test_items = {}
        for row in test_data:
            uid = row["userId"]
            if uid not in user_relevant:
                user_relevant[uid] = set()
                user_test_items[uid] = []
            if row["rating"] >= 3.5:
                user_relevant[uid].add(row["movieId"])
            user_test_items[uid].append(row)

        # Generate recommendations for each user
        recommended_per_user = {}
        response_times = []
        predictions = []
        actuals = []

        sample_users = list(user_relevant.keys())[:500]  # Sample for tractability

        for user_id in sample_users:
            start = time.perf_counter()
            recs = recommend_fn(user_id)
            elapsed_ms = (time.perf_counter() - start) * 1000
            response_times.append(elapsed_ms)

            rec_ids = [r["movieId"] if isinstance(r, dict) else r for r in recs]
            recommended_per_user[user_id] = rec_ids

            # Collect rating predictions if available
            if predict_fn:
                for item in user_test_items.get(user_id, []):
                    try:
                        pred = predict_fn(user_id, item["movieId"])
                        if pred is not None:
                            predictions.append(pred)
                            actuals.append(item["rating"])
                    except Exception:
                        pass

        # Compute metrics
        metrics = compute_all_metrics(
            recommended_per_user=recommended_per_user,
            relevant_per_user=user_relevant,
            predictions=predictions if predictions else None,
            actuals=actuals if actuals else None,
            all_movie_ids=all_movie_ids,
            genre_map=genre_map,
            k=TOP_K,
        )

        # Add response time stats
        if response_times:
            metrics["avg_response_ms"] = sum(response_times) / len(response_times)
            sorted_times = sorted(response_times)
            p95_idx = int(0.95 * len(sorted_times))
            metrics["p95_response_ms"] = sorted_times[min(p95_idx, len(sorted_times) - 1)]

        metrics["model"] = model_name
        metrics["num_users_evaluated"] = len(sample_users)

        return metrics

    def run_full_evaluation(self, model_builders, strategy_names=None):
        """
        Run all models across all splitting strategies.

        Args:
            model_builders: dict of {
                model_name: {
                    'train_fn': function(train_df) -> None,
                    'recommend_fn': function(user_id) -> list,
                    'predict_fn': optional function(user_id, movie_id) -> float,
                }
            }
            strategy_names: list of strategies to evaluate (default: all 5)
        """
        if strategy_names is None:
            strategy_names = SPLITTING_STRATEGIES

        movies_df = self.spark.read.parquet(
            os.path.join(PROCESSED_DATA_DIR, "movies")
        )
        all_movie_ids = set(
            row["movieId"] for row in movies_df.select("movieId").collect()
        )

        # Build genre map for diversity metric
        genre_map = {}
        for row in movies_df.select("movieId", "genres").collect():
            genres = row["genres"] or ""
            genre_map[row["movieId"]] = set(genres.split("|")) - {"(no genres listed)"}

        all_results = []

        for strategy in strategy_names:
            logger.info(f"\n{'='*60}")
            logger.info(f"Evaluating strategy: {strategy}")
            logger.info(f"{'='*60}")

            train, val, test = self.load_split(strategy)

            # Convert test to list of dicts
            test_data = [row.asDict() for row in test.collect()]

            for model_name, builder in model_builders.items():
                logger.info(f"\n--- {model_name} on {strategy} ---")

                # Train model
                start = time.perf_counter()
                builder["train_fn"](train)
                train_time = time.perf_counter() - start

                # Evaluate
                metrics = self.evaluate_model(
                    model_name=model_name,
                    recommend_fn=builder["recommend_fn"],
                    test_data=test_data,
                    all_movie_ids=all_movie_ids,
                    genre_map=genre_map,
                    predict_fn=builder.get("predict_fn"),
                )

                metrics["strategy"] = strategy
                metrics["train_time_seconds"] = train_time

                all_results.append(metrics)
                logger.info(f"Results: {json.dumps(metrics, indent=2, default=str)}")

        self.results = all_results
        self._save_results()
        return all_results

    def _save_results(self):
        """Save evaluation results to CSV and JSON."""
        os.makedirs(RESULTS_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Save as CSV
        df = pd.DataFrame(self.results)
        csv_path = os.path.join(RESULTS_DIR, f"evaluation_{timestamp}.csv")
        df.to_csv(csv_path, index=False)

        # Save as JSON
        json_path = os.path.join(RESULTS_DIR, f"evaluation_{timestamp}.json")
        with open(json_path, "w") as f:
            json.dump(self.results, f, indent=2, default=str)

        logger.info(f"Results saved to {csv_path} and {json_path}")

    def generate_summary_table(self):
        """Create a summary comparison table of all results."""
        if not self.results:
            logger.warning("No results to summarise.")
            return None

        df = pd.DataFrame(self.results)

        # Pivot table: strategies as rows, models as columns
        summary = df.pivot_table(
            index="strategy",
            columns="model",
            values=["RMSE", f"Precision@{TOP_K}", f"NDCG@{TOP_K}", "Coverage"],
            aggfunc="mean",
        )

        return summary
