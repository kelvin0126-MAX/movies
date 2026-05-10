"""
Spark-based data preprocessing pipeline for the Netflix Prize dataset.

Netflix data format (combined_data_*.txt):
  MovieID:
  CustomerID,Rating,Date
  CustomerID,Rating,Date
  ...
  MovieID:
  CustomerID,Rating,Date
  ...

This pipeline parses the custom format, cleans the data,
engineers features, and saves as parquet for downstream use.
"""

import json
import logging
import os

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    FloatType,
    IntegerType,
    StringType,
    StructField,
    StructType,
)
from pyspark.sql.window import Window

from config.settings import (
    MIN_MOVIE_RATINGS,
    MIN_USER_RATINGS,
    NETFLIX_DATA_FILES,
    NETFLIX_DIR,
    OUTLIER_ZSCORE_THRESHOLD,
    PROCESSED_DATA_DIR,
    SPARK_CONFIG,
)

logger = logging.getLogger(__name__)


def create_spark_session():
    """Create and configure a Spark session."""
    return (
        SparkSession.builder
        .appName(SPARK_CONFIG["app_name"])
        .master(SPARK_CONFIG["master"])
        .config("spark.driver.memory", SPARK_CONFIG["driver_memory"])
        .config("spark.executor.memory", SPARK_CONFIG["executor_memory"])
        .config("spark.sql.shuffle.partitions", SPARK_CONFIG["shuffle_partitions"])
        .config("spark.sql.parquet.compression.codec", "snappy")
        .getOrCreate()
    )


def parse_netflix_to_csv(output_path=None):
    """
    Parse Netflix combined_data_*.txt files into a single CSV.

    Netflix format:
      MovieID:
      CustomerID,Rating,Date
      ...

    Output CSV: userId,movieId,rating,date
    """
    if output_path is None:
        output_path = os.path.join(NETFLIX_DIR, "ratings_parsed.csv")

    if os.path.exists(output_path):
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        logger.info(f"Parsed ratings CSV already exists ({size_mb:.1f} MB). Skipping parse.")
        return output_path

    logger.info("Parsing Netflix data files (this may take a few minutes)...")

    total_ratings = 0
    current_movie_id = None

    with open(output_path, "w") as out:
        out.write("userId,movieId,rating,date\n")

        for data_file in NETFLIX_DATA_FILES:
            file_path = os.path.join(NETFLIX_DIR, data_file)
            logger.info(f"  Parsing {data_file}...")

            with open(file_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    if line.endswith(":"):
                        # Movie ID line
                        current_movie_id = line[:-1]
                    else:
                        # Rating line: CustomerID,Rating,Date
                        parts = line.split(",")
                        if len(parts) == 3 and current_movie_id:
                            user_id = parts[0]
                            rating = parts[1]
                            date = parts[2]
                            out.write(f"{user_id},{current_movie_id},{rating},{date}\n")
                            total_ratings += 1

    logger.info(f"Parsed {total_ratings:,} ratings into {output_path}")
    return output_path


def load_raw_data(spark):
    """Load parsed Netflix ratings and movie titles into Spark DataFrames."""
    logger.info("Loading Netflix data into Spark...")

    # Parse Netflix files first
    ratings_csv = parse_netflix_to_csv()

    # Ratings schema
    ratings_schema = StructType([
        StructField("userId", IntegerType(), False),
        StructField("movieId", IntegerType(), False),
        StructField("rating", FloatType(), False),
        StructField("date", StringType(), False),
    ])

    ratings = spark.read.csv(ratings_csv, header=True, schema=ratings_schema)

    # Movie titles
    # Parse movie_titles.csv (format: MovieID,YearOfRelease,Title)
    # Some titles have commas, so read as text and parse
    from pipeline.download import parse_movie_titles

    movies_list = parse_movie_titles()

    # Load TMDB genre cache if available
    genre_cache_path = os.path.join(PROCESSED_DATA_DIR, "tmdb_genre_cache.json")
    genre_cache = {}
    if os.path.exists(genre_cache_path):
        with open(genre_cache_path, "r") as f:
            genre_cache = json.load(f)

    # Apply cached genres
    for movie in movies_list:
        mid = str(movie["movieId"])
        if mid in genre_cache:
            movie["genres"] = genre_cache[mid]

    # Create movies DataFrame
    movies_schema = StructType([
        StructField("movieId", IntegerType(), False),
        StructField("title", StringType(), False),
        StructField("year", IntegerType(), True),
        StructField("genres", StringType(), True),
    ])

    movies_rows = [
        (m["movieId"], m["title"], m["year"], m["genres"] or "")
        for m in movies_list
    ]
    movies = spark.createDataFrame(movies_rows, schema=movies_schema)

    logger.info(
        f"Loaded: {ratings.count():,} ratings, {movies.count():,} movies"
    )
    return ratings, movies


def clean_data(ratings, movies):
    """Remove duplicates, nulls, and apply quality filters."""
    logger.info("Cleaning data...")

    # Remove duplicates
    ratings = ratings.dropDuplicates(["userId", "movieId"])
    movies = movies.dropDuplicates(["movieId"])

    # Remove nulls
    ratings = ratings.dropna(subset=["userId", "movieId", "rating"])
    movies = movies.dropna(subset=["movieId", "title"])

    # Filter users with fewer than MIN_USER_RATINGS ratings
    user_counts = ratings.groupBy("userId").count()
    active_users = user_counts.filter(F.col("count") >= MIN_USER_RATINGS).select("userId")
    ratings = ratings.join(active_users, "userId", "inner")

    # Filter movies with fewer than MIN_MOVIE_RATINGS ratings
    movie_counts = ratings.groupBy("movieId").count()
    active_movies = movie_counts.filter(F.col("count") >= MIN_MOVIE_RATINGS).select("movieId")
    ratings = ratings.join(active_movies, "movieId", "inner")

    # Z-score outlier detection on ratings per user
    user_stats = ratings.groupBy("userId").agg(
        F.mean("rating").alias("user_mean"),
        F.stddev("rating").alias("user_std"),
    )
    ratings = ratings.join(user_stats, "userId", "left")
    ratings = ratings.withColumn(
        "zscore",
        F.when(
            F.col("user_std") > 0,
            (F.col("rating") - F.col("user_mean")) / F.col("user_std"),
        ).otherwise(0),
    )
    ratings = ratings.filter(F.abs(F.col("zscore")) <= OUTLIER_ZSCORE_THRESHOLD)
    ratings = ratings.drop("user_mean", "user_std", "zscore")

    logger.info(f"After cleaning: {ratings.count():,} ratings, {movies.count():,} movies")
    return ratings, movies


def engineer_features(ratings, movies):
    """Feature engineering for Netflix data."""
    logger.info("Engineering features...")

    # Convert date string to timestamp (Unix epoch) for splitting
    ratings = ratings.withColumn(
        "timestamp",
        F.unix_timestamp(F.col("date"), "yyyy-MM-dd"),
    )
    ratings = ratings.drop("date")

    # Parse genres into array
    movies = movies.withColumn(
        "genre_list",
        F.when(
            (F.col("genres").isNotNull()) & (F.col("genres") != ""),
            F.split(F.col("genres"), r"\|"),
        ).otherwise(F.array()),
    )

    # Count genres per movie
    movies = movies.withColumn("genre_count", F.size(F.col("genre_list")))

    logger.info("Feature engineering complete.")
    return ratings, movies


def compute_movie_stats(ratings):
    """Compute per-movie statistics."""
    return ratings.groupBy("movieId").agg(
        F.count("rating").alias("rating_count"),
        F.mean("rating").alias("avg_rating"),
        F.stddev("rating").alias("std_rating"),
        F.min("timestamp").alias("first_rating"),
        F.max("timestamp").alias("last_rating"),
    )


def compute_user_stats(ratings):
    """Compute per-user statistics."""
    return ratings.groupBy("userId").agg(
        F.count("rating").alias("rating_count"),
        F.mean("rating").alias("avg_rating"),
        F.stddev("rating").alias("std_rating"),
        F.min("timestamp").alias("first_rating"),
        F.max("timestamp").alias("last_rating"),
    )


def save_processed_data(ratings, movies, movie_stats, user_stats):
    """Save processed data as parquet files."""
    os.makedirs(PROCESSED_DATA_DIR, exist_ok=True)

    logger.info("Saving processed data as parquet...")
    ratings.write.parquet(
        os.path.join(PROCESSED_DATA_DIR, "ratings"), mode="overwrite"
    )
    movies.write.parquet(
        os.path.join(PROCESSED_DATA_DIR, "movies"), mode="overwrite"
    )
    movie_stats.write.parquet(
        os.path.join(PROCESSED_DATA_DIR, "movie_stats"), mode="overwrite"
    )
    user_stats.write.parquet(
        os.path.join(PROCESSED_DATA_DIR, "user_stats"), mode="overwrite"
    )
    logger.info("Processed data saved.")


def run_preprocessing():
    """Execute the full preprocessing pipeline."""
    spark = create_spark_session()
    try:
        ratings, movies = load_raw_data(spark)
        ratings, movies = clean_data(ratings, movies)
        ratings, movies = engineer_features(ratings, movies)
        movie_stats = compute_movie_stats(ratings)
        user_stats = compute_user_stats(ratings)
        save_processed_data(ratings, movies, movie_stats, user_stats)
        logger.info("Preprocessing pipeline complete.")
    finally:
        spark.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_preprocessing()
