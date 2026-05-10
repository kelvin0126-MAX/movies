"""
Content-Based Filtering using TF-IDF and Cosine Similarity.
Weight: 30% in the hybrid model.

Analyses movie genre features to recommend similar items based on user profile.
"""

import logging
import os
import pickle

import numpy as np
from scipy.sparse import save_npz, load_npz
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from config.settings import CONTENT_PARAMS, MODEL_DIR

logger = logging.getLogger(__name__)

CONTENT_MODEL_DIR = os.path.join(MODEL_DIR, "content_based")


class ContentBasedFilter:
    """TF-IDF + cosine similarity content-based recommender."""

    def __init__(self):
        self.vectorizer = TfidfVectorizer(
            max_features=CONTENT_PARAMS["max_features"],
            stop_words="english",
        )
        self.tfidf_matrix = None
        self.movie_ids = None
        self.movie_id_to_idx = {}

    def train(self, movies_df):
        """
        Build TF-IDF matrix from movie genre features.

        Args:
            movies_df: pandas DataFrame with columns ['movieId', 'genres']
        """
        logger.info("Training content-based filtering model...")

        self.movie_ids = movies_df["movieId"].values
        self.movie_id_to_idx = {mid: idx for idx, mid in enumerate(self.movie_ids)}

        # Combine genres into text features (replace '|' with spaces)
        genre_text = movies_df["genres"].fillna("").str.replace("|", " ", regex=False)

        self.tfidf_matrix = self.vectorizer.fit_transform(genre_text)

        logger.info(
            f"TF-IDF matrix shape: {self.tfidf_matrix.shape} "
            f"({len(self.movie_ids)} movies, {self.tfidf_matrix.shape[1]} features)"
        )

    def get_similar_movies(self, movie_id, n=20):
        """Find top-N similar movies to a given movie."""
        if movie_id not in self.movie_id_to_idx:
            logger.warning(f"Movie {movie_id} not found in content model.")
            return []

        idx = self.movie_id_to_idx[movie_id]
        movie_vec = self.tfidf_matrix[idx]

        # Compute similarity with all movies
        similarities = cosine_similarity(movie_vec, self.tfidf_matrix).flatten()

        # Get top-N (excluding the movie itself)
        similar_indices = similarities.argsort()[::-1][1 : n + 1]

        results = []
        for sim_idx in similar_indices:
            results.append({
                "movieId": int(self.movie_ids[sim_idx]),
                "score": float(similarities[sim_idx]),
            })
        return results

    def build_user_profile(self, user_ratings):
        """
        Build a user preference vector from their rated movies.

        Args:
            user_ratings: list of dicts with 'movieId' and 'rating'

        Returns:
            Weighted average TF-IDF vector representing user taste.
        """
        profile_vec = np.zeros(self.tfidf_matrix.shape[1])
        total_weight = 0

        for item in user_ratings:
            movie_id = item["movieId"]
            rating = item["rating"]

            if movie_id in self.movie_id_to_idx:
                idx = self.movie_id_to_idx[movie_id]
                # Weight by rating (higher rating = stronger preference)
                weight = rating - 2.5  # Center around neutral
                profile_vec += weight * self.tfidf_matrix[idx].toarray().flatten()
                total_weight += abs(weight)

        if total_weight > 0:
            profile_vec /= total_weight

        return profile_vec

    def recommend_for_user(self, user_ratings, n=20, exclude_rated=True):
        """
        Generate recommendations based on user's content profile.

        Args:
            user_ratings: list of dicts with 'movieId' and 'rating'
            n: number of recommendations
            exclude_rated: whether to exclude already-rated movies
        """
        profile_vec = self.build_user_profile(user_ratings)

        if np.allclose(profile_vec, 0):
            logger.warning("Empty user profile, returning empty recommendations.")
            return []

        # Compute similarity between user profile and all movies
        similarities = cosine_similarity(
            profile_vec.reshape(1, -1), self.tfidf_matrix
        ).flatten()

        # Exclude already-rated movies
        rated_ids = set()
        if exclude_rated:
            rated_ids = {r["movieId"] for r in user_ratings}

        # Get top-N recommendations
        ranked_indices = similarities.argsort()[::-1]
        results = []
        for idx in ranked_indices:
            movie_id = int(self.movie_ids[idx])
            if movie_id not in rated_ids:
                results.append({
                    "movieId": movie_id,
                    "score": float(similarities[idx]),
                })
                if len(results) >= n:
                    break

        return results

    def save(self, path=None):
        """Save the content-based model artifacts."""
        path = path or CONTENT_MODEL_DIR
        os.makedirs(path, exist_ok=True)

        save_npz(os.path.join(path, "tfidf_matrix.npz"), self.tfidf_matrix)
        with open(os.path.join(path, "vectorizer.pkl"), "wb") as f:
            pickle.dump(self.vectorizer, f)
        np.save(os.path.join(path, "movie_ids.npy"), self.movie_ids)

        logger.info(f"Content-based model saved to {path}")

    def load(self, path=None):
        """Load a previously saved content-based model."""
        path = path or CONTENT_MODEL_DIR

        self.tfidf_matrix = load_npz(os.path.join(path, "tfidf_matrix.npz"))
        with open(os.path.join(path, "vectorizer.pkl"), "rb") as f:
            self.vectorizer = pickle.load(f)
        # L4: Cast to int32 so lookups match pandas int32 columns and avoid
        # hash-mismatch surprises between int64 numpy values and python ints.
        self.movie_ids = np.load(os.path.join(path, "movie_ids.npy")).astype("int32")
        self.movie_id_to_idx = {int(mid): idx for idx, mid in enumerate(self.movie_ids)}

        logger.info(f"Content-based model loaded from {path}")
