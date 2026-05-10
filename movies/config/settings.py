"""
Central configuration for the Movie Recommendation System.
All settings (Spark, Flask, model parameters, paths) in one place.
"""

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ──────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────
DATA_DIR = os.path.join(BASE_DIR, "data")
RAW_DATA_DIR = os.path.join(DATA_DIR, "raw")
PROCESSED_DATA_DIR = os.path.join(DATA_DIR, "processed")
SPLITS_DIR = os.path.join(DATA_DIR, "splits")
DATABASE_PATH = os.path.join(BASE_DIR, "database", "movies.db")
MODEL_DIR = os.path.join(BASE_DIR, "models", "saved")

# Netflix Prize Dataset (~100M ratings, 480K users, 17K movies)
# Download from: https://www.kaggle.com/datasets/netflix-inc/netflix-prize-data
# Place the extracted files in data/raw/netflix-prize/
NETFLIX_DIR = os.path.join(RAW_DATA_DIR, "archive")
NETFLIX_DATA_FILES = [
    "combined_data_1.txt",
    "combined_data_2.txt",
    "combined_data_3.txt",
    "combined_data_4.txt",
]
NETFLIX_MOVIE_TITLES = "movie_titles.csv"

# TMDB API for fetching poster/overview/genre metadata (free key from themoviedb.org)
TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "6547c2f43bd983e608ee4526e4c04b99")
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p"
# Poster size tiers: w92, w154, w185, w342, w500, w780, original
TMDB_POSTER_SIZE = "w342"
TMDB_BACKDROP_SIZE = "w1280"

# ──────────────────────────────────────────────
# Apache Spark
# ──────────────────────────────────────────────
SPARK_CONFIG = {
    "app_name": "MovieRecommender",
    "master": "local[4]",
    "driver_memory": "8g",
    "executor_memory": "4g",
    "shuffle_partitions": 8,
}

# ──────────────────────────────────────────────
# Data Preprocessing
# ──────────────────────────────────────────────
MIN_USER_RATINGS = 20      # Remove users with fewer ratings
MIN_MOVIE_RATINGS = 5      # Remove movies with fewer ratings
OUTLIER_ZSCORE_THRESHOLD = 3.0

# ──────────────────────────────────────────────
# Data Splitting
# ──────────────────────────────────────────────
SPLIT_RATIOS = {
    "train": 0.8,
    "validation": 0.1,
    "test": 0.1,
}
# Netflix data spans 1999-2005
TEMPORAL_SPLIT = {
    "train_end": "2005-01-01",
    "validation_end": "2005-07-01",
}

# ──────────────────────────────────────────────
# Model Parameters
# ──────────────────────────────────────────────

# Collaborative Filtering (ALS)
ALS_PARAMS = {
    "rank": 50,              # Latent factors
    "max_iter": 10,
    "reg_param": 0.1,
    "cold_start_strategy": "drop",
    "user_col": "userId",
    "item_col": "movieId",
    "rating_col": "rating",
}

# Content-Based Filtering
CONTENT_PARAMS = {
    "max_features": 5000,    # TF-IDF max features
    "similarity_metric": "cosine",
}

# Behavior-Based Filtering
BEHAVIOR_PARAMS = {
    "event_weights": {
        "view": 1.0,
        "click": 2.0,
        "search": 3.0,
        "rating": 5.0,
    },
    "temporal_decay_factor": 0.95,  # Per-day decay
    "max_history_days": 90,
}

# Hybrid Weights
HYBRID_WEIGHTS = {
    "collaborative": 0.4,
    "content_based": 0.3,
    "behavior": 0.3,
}

# Grid search ranges for weight optimisation
WEIGHT_GRID = {
    "collaborative": [0.3, 0.4, 0.5],
    "content_based": [0.2, 0.3, 0.4],
    "behavior": [0.2, 0.3, 0.4],
}

# ──────────────────────────────────────────────
# Evaluation
# ──────────────────────────────────────────────
TOP_K = 10                   # For Precision@K, Recall@K, NDCG@K
CROSS_VALIDATION_FOLDS = 5
SPLITTING_STRATEGIES = [
    "random",
    "temporal",
    "user_based",
    "stratified",
    "leave_one_out",
]

# ──────────────────────────────────────────────
# Flask / Backend
# ──────────────────────────────────────────────
FLASK_CONFIG = {
    "SECRET_KEY": os.environ.get("SECRET_KEY", "dev-secret-change-in-production"),
    "DEBUG": os.environ.get("FLASK_DEBUG", "True").lower() == "true",
    "HOST": "0.0.0.0",
    "PORT": 5001,
}
JWT_EXPIRY_HOURS = 24
RECOMMENDATIONS_CACHE_TTL_HOURS = 24
MAX_RECOMMENDATIONS = 20

# ──────────────────────────────────────────────
# Frontend
# ──────────────────────────────────────────────
FRONTEND_URL = "http://localhost:5173"
