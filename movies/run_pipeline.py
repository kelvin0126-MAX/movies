#!/usr/bin/env python3
"""
Main pipeline runner.
Executes: download -> preprocess -> split -> (optionally) train & evaluate.

Usage:
    python run_pipeline.py                  # Full pipeline
    python run_pipeline.py --step download  # Only download
    python run_pipeline.py --step preprocess
    python run_pipeline.py --step split
    python run_pipeline.py --step evaluate
"""

import argparse
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.logging_config import setup_logging

logger = setup_logging()


def step_download():
    from pipeline.download import prepare_netflix_data, parse_movie_titles, fetch_tmdb_genres
    if prepare_netflix_data():
        movies = parse_movie_titles()
        fetch_tmdb_genres(movies)


def step_preprocess():
    from pipeline.preprocess import run_preprocessing
    run_preprocessing()


def step_split():
    from pipeline.splitter import run_all_splits
    run_all_splits()


def step_evaluate():
    """Run evaluation across all models and splitting strategies."""
    from pipeline.preprocess import create_spark_session
    from evaluation.evaluator import Evaluator
    from models.collaborative import CollaborativeFilter
    from models.content_based import ContentBasedFilter
    from models.behavior import BehaviorFilter
    from models.hybrid import HybridRecommender
    from config.settings import PROCESSED_DATA_DIR

    import pandas as pd

    spark = create_spark_session()

    try:
        # Load movies for content-based model
        movies_pd = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "movies"))

        # Initialise models
        cf = CollaborativeFilter(spark)
        cbf = ContentBasedFilter()
        bf = BehaviorFilter()

        # Set up metadata for behavior model
        movie_meta = {}
        for _, row in movies_pd.iterrows():
            movie_meta[row["movieId"]] = {
                "genres": row.get("genres", ""),
                "avg_rating": 0,
            }
        bf.set_movie_metadata(movie_meta)

        all_movie_ids = list(movies_pd["movieId"].values)

        def make_model_builders():
            return {
                "collaborative": {
                    "train_fn": lambda train_df: cf.train(train_df),
                    "recommend_fn": lambda uid: [
                        {"movieId": r["movieId"]}
                        for r in (cf.recommend_for_user(uid, n=10).collect()
                                  if cf.model else [])
                    ],
                },
                "content_based": {
                    "train_fn": lambda train_df: cbf.train(movies_pd),
                    "recommend_fn": lambda uid: cbf.recommend_for_user(
                        [], n=10  # Would need user ratings in real use
                    ),
                },
                "hybrid": {
                    "train_fn": lambda train_df: (
                        cf.train(train_df),
                        cbf.train(movies_pd),
                    ),
                    "recommend_fn": lambda uid: HybridRecommender(
                        cf, cbf, bf
                    ).recommend(uid, [], all_movie_ids, spark=spark, n=10),
                },
            }

        evaluator = Evaluator(spark)
        results = evaluator.run_full_evaluation(make_model_builders())

        summary = evaluator.generate_summary_table()
        if summary is not None:
            logger.info(f"\n{summary}")

    finally:
        spark.stop()


def main():
    parser = argparse.ArgumentParser(description="Movie Recommender Pipeline")
    parser.add_argument(
        "--step",
        choices=["download", "preprocess", "split", "evaluate", "all"],
        default="all",
        help="Pipeline step to execute",
    )
    args = parser.parse_args()

    steps = {
        "download": step_download,
        "preprocess": step_preprocess,
        "split": step_split,
        "evaluate": step_evaluate,
    }

    if args.step == "all":
        for name, fn in steps.items():
            logger.info(f"\n{'='*60}")
            logger.info(f"Running step: {name}")
            logger.info(f"{'='*60}")
            fn()
    else:
        steps[args.step]()

    logger.info("Pipeline complete.")


if __name__ == "__main__":
    main()
