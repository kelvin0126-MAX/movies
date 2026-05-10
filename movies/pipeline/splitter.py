"""
Five data splitting strategies for evaluating recommendation models.

1. Random Split (80/10/10)
2. Temporal Split (pre-2005 / H1-2005 / post-Jul-2005)
3. User-Based Split (80/10/10 per user)
4. Stratified Split (preserves rating distribution)
5. Leave-One-Out (all but last rating for test)
"""

import logging
import os

from pyspark.sql import SparkSession, functions as F
from pyspark.sql.window import Window

from config.settings import PROCESSED_DATA_DIR, SPLITS_DIR, SPLIT_RATIOS, TEMPORAL_SPLIT

logger = logging.getLogger(__name__)


def load_processed_ratings(spark):
    """Load the preprocessed ratings parquet."""
    return spark.read.parquet(os.path.join(PROCESSED_DATA_DIR, "ratings"))


def save_split(train, validation, test, strategy_name):
    """Save train/val/test splits for a given strategy."""
    out_dir = os.path.join(SPLITS_DIR, strategy_name)
    os.makedirs(out_dir, exist_ok=True)

    train.write.parquet(os.path.join(out_dir, "train"), mode="overwrite")
    validation.write.parquet(os.path.join(out_dir, "validation"), mode="overwrite")
    test.write.parquet(os.path.join(out_dir, "test"), mode="overwrite")

    logger.info(
        f"[{strategy_name}] Saved — train: {train.count()}, "
        f"val: {validation.count()}, test: {test.count()}"
    )


# ──────────────────────────────────────────────
# Strategy 1: Random Split
# ──────────────────────────────────────────────
def random_split(ratings):
    """Simple random split with 80/10/10 ratio."""
    logger.info("Applying random split...")
    train, val, test = ratings.randomSplit(
        [SPLIT_RATIOS["train"], SPLIT_RATIOS["validation"], SPLIT_RATIOS["test"]],
        seed=42,
    )
    save_split(train, val, test, "random")
    return train, val, test


# ──────────────────────────────────────────────
# Strategy 2: Temporal Split
# ──────────────────────────────────────────────
def temporal_split(ratings):
    """Split by time: train < 2018, val = Jan-Jun 2018, test >= Jul 2018."""
    logger.info("Applying temporal split...")

    # Convert Unix timestamp to date
    ratings_with_date = ratings.withColumn(
        "date", F.from_unixtime(F.col("timestamp")).cast("date")
    )

    train_end = TEMPORAL_SPLIT["train_end"]
    val_end = TEMPORAL_SPLIT["validation_end"]

    train = ratings_with_date.filter(F.col("date") < train_end).drop("date")
    val = ratings_with_date.filter(
        (F.col("date") >= train_end) & (F.col("date") < val_end)
    ).drop("date")
    test = ratings_with_date.filter(F.col("date") >= val_end).drop("date")

    save_split(train, val, test, "temporal")
    return train, val, test


# ──────────────────────────────────────────────
# Strategy 3: User-Based Split
# ──────────────────────────────────────────────
def user_based_split(ratings):
    """Split each user's ratings 80/10/10 chronologically."""
    logger.info("Applying user-based split...")

    # Rank each user's ratings by timestamp
    window = Window.partitionBy("userId").orderBy("timestamp")
    rated = ratings.withColumn("row_num", F.row_number().over(window))
    total = ratings.groupBy("userId").count().withColumnRenamed("count", "total")
    rated = rated.join(total, "userId")

    # Assign splits based on position within each user's timeline
    rated = rated.withColumn("position", F.col("row_num") / F.col("total"))

    train = rated.filter(F.col("position") <= 0.8).drop("row_num", "total", "position")
    val = rated.filter(
        (F.col("position") > 0.8) & (F.col("position") <= 0.9)
    ).drop("row_num", "total", "position")
    test = rated.filter(F.col("position") > 0.9).drop("row_num", "total", "position")

    save_split(train, val, test, "user_based")
    return train, val, test


# ──────────────────────────────────────────────
# Strategy 4: Stratified Split
# ──────────────────────────────────────────────
def stratified_split(ratings):
    """Preserve rating distribution across train/val/test."""
    logger.info("Applying stratified split...")

    # Round ratings to nearest 0.5 for stratification buckets
    ratings_bucketed = ratings.withColumn(
        "rating_bucket", F.round(F.col("rating") * 2) / 2
    )

    train_parts, val_parts, test_parts = [], [], []

    # Split within each rating bucket
    for bucket_row in ratings_bucketed.select("rating_bucket").distinct().collect():
        bucket = bucket_row["rating_bucket"]
        subset = ratings_bucketed.filter(F.col("rating_bucket") == bucket)
        tr, va, te = subset.randomSplit(
            [SPLIT_RATIOS["train"], SPLIT_RATIOS["validation"], SPLIT_RATIOS["test"]],
            seed=42,
        )
        train_parts.append(tr)
        val_parts.append(va)
        test_parts.append(te)

    # Union all buckets
    train = train_parts[0]
    val = val_parts[0]
    test = test_parts[0]
    for i in range(1, len(train_parts)):
        train = train.union(train_parts[i])
        val = val.union(val_parts[i])
        test = test.union(test_parts[i])

    # Drop helper column
    train = train.drop("rating_bucket")
    val = val.drop("rating_bucket")
    test = test.drop("rating_bucket")

    save_split(train, val, test, "stratified")
    return train, val, test


# ──────────────────────────────────────────────
# Strategy 5: Leave-One-Out
# ──────────────────────────────────────────────
def leave_one_out_split(ratings):
    """Use each user's last rating for test, second-to-last for val, rest for train."""
    logger.info("Applying leave-one-out split...")

    window = Window.partitionBy("userId").orderBy(F.col("timestamp").desc())
    ranked = ratings.withColumn("rank", F.row_number().over(window))

    test = ranked.filter(F.col("rank") == 1).drop("rank")
    val = ranked.filter(F.col("rank") == 2).drop("rank")
    train = ranked.filter(F.col("rank") > 2).drop("rank")

    save_split(train, val, test, "leave_one_out")
    return train, val, test


# ──────────────────────────────────────────────
# Run all strategies
# ──────────────────────────────────────────────
def run_all_splits(spark=None):
    """Execute all 5 splitting strategies and save results."""
    from pipeline.preprocess import create_spark_session

    own_spark = spark is None
    if own_spark:
        spark = create_spark_session()

    try:
        ratings = load_processed_ratings(spark)
        logger.info(f"Total ratings for splitting: {ratings.count()}")

        random_split(ratings)
        temporal_split(ratings)
        user_based_split(ratings)
        stratified_split(ratings)
        leave_one_out_split(ratings)

        logger.info("All 5 splitting strategies complete.")
    finally:
        if own_spark:
            spark.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_all_splits()
