"""
Behavior-Based Filtering with temporal decay and weighted scoring.
Weight: 30% in the hybrid model.

Tracks user interactions (views, clicks, searches, time spent) and uses
temporal decay to weight recent behaviour more heavily.
"""

import logging
import math
from collections import defaultdict
from datetime import datetime, timedelta

from config.settings import BEHAVIOR_PARAMS

logger = logging.getLogger(__name__)


class BehaviorFilter:
    """Behaviour-based recommender using implicit feedback signals."""

    def __init__(self):
        self.event_weights = BEHAVIOR_PARAMS["event_weights"]
        self.decay_factor = BEHAVIOR_PARAMS["temporal_decay_factor"]
        self.max_history_days = BEHAVIOR_PARAMS["max_history_days"]
        # movie_id -> {genre, popularity_score, etc.}
        self.movie_metadata = {}
        # user_id -> list of behaviour events
        self.user_behaviours = defaultdict(list)

    def set_movie_metadata(self, metadata_dict):
        """
        Load movie metadata for enriching recommendations.

        Args:
            metadata_dict: dict of {movie_id: {'genres': str, 'avg_rating': float, ...}}
        """
        self.movie_metadata = metadata_dict

    def add_event(self, user_id, movie_id, event_type, duration=0, timestamp=None):
        """Record a user behaviour event."""
        if timestamp is None:
            timestamp = datetime.now()

        self.user_behaviours[user_id].append({
            "movie_id": movie_id,
            "event_type": event_type,
            "duration": duration,
            "timestamp": timestamp,
        })

    def load_events_bulk(self, events):
        """
        Load behaviour events in bulk.

        Args:
            events: list of dicts with user_id, movie_id, event_type, duration, timestamp
        """
        for event in events:
            user_id = event["user_id"]
            self.user_behaviours[user_id].append({
                "movie_id": event["movie_id"],
                "event_type": event["event_type"],
                "duration": event.get("duration", 0),
                "timestamp": event["timestamp"],
            })

    def _compute_temporal_decay(self, event_timestamp, reference_time=None):
        """Compute exponential temporal decay weight."""
        if reference_time is None:
            reference_time = datetime.now()

        days_ago = (reference_time - event_timestamp).days
        days_ago = min(days_ago, self.max_history_days)

        return self.decay_factor ** days_ago

    def compute_user_scores(self, user_id, reference_time=None):
        """
        Compute behaviour-based scores for all movies a user has interacted with.

        Returns:
            dict of {movie_id: score}
        """
        events = self.user_behaviours.get(user_id, [])
        if not events:
            return {}

        if reference_time is None:
            reference_time = max(e["timestamp"] for e in events)

        # Cut off old events
        cutoff = reference_time - timedelta(days=self.max_history_days)
        recent_events = [e for e in events if e["timestamp"] >= cutoff]

        movie_scores = defaultdict(float)
        for event in recent_events:
            base_weight = self.event_weights.get(event["event_type"], 1.0)
            decay = self._compute_temporal_decay(event["timestamp"], reference_time)

            # Duration bonus (normalised: cap at 120 minutes)
            duration_bonus = 1.0
            if event["duration"] > 0:
                duration_bonus = 1.0 + min(event["duration"] / 120.0, 1.0)

            score = base_weight * decay * duration_bonus
            movie_scores[event["movie_id"]] += score

        return dict(movie_scores)

    def recommend_for_user(self, user_id, all_movie_ids, n=20, exclude_interacted=True):
        """
        Generate recommendations based on user behaviour patterns.

        Uses the user's interaction-weighted genre preferences to score
        un-interacted movies.

        Args:
            user_id: target user
            all_movie_ids: list of all available movie IDs
            n: number of recommendations
            exclude_interacted: skip movies user has already interacted with
        """
        user_scores = self.compute_user_scores(user_id)

        if not user_scores:
            # H4: Cold-start fallback — return popularity-ranked movies by
            # avg_rating (from loaded metadata) so hybrid still receives a
            # meaningful behaviour signal for brand-new users.
            ranked = []
            for movie_id in all_movie_ids:
                meta = self.movie_metadata.get(movie_id, {})
                popularity = float(meta.get("avg_rating", 0) or 0)
                if popularity > 0:
                    ranked.append({"movieId": movie_id, "score": popularity})
            ranked.sort(key=lambda x: x["score"], reverse=True)
            return ranked[:n]

        # Build genre preference profile from interacted movies
        genre_scores = defaultdict(float)
        for movie_id, score in user_scores.items():
            meta = self.movie_metadata.get(movie_id, {})
            genres = meta.get("genres", "")
            for genre in genres.split("|"):
                if genre and genre != "(no genres listed)":
                    genre_scores[genre] += score

        # Normalise genre scores
        max_genre_score = max(genre_scores.values()) if genre_scores else 1.0
        genre_scores = {g: s / max_genre_score for g, s in genre_scores.items()}

        # Score all candidate movies
        interacted = set(user_scores.keys()) if exclude_interacted else set()
        candidates = []

        for movie_id in all_movie_ids:
            if movie_id in interacted:
                continue

            meta = self.movie_metadata.get(movie_id, {})
            movie_genres = meta.get("genres", "").split("|")

            # Score based on genre overlap with user preferences
            score = 0.0
            for genre in movie_genres:
                score += genre_scores.get(genre, 0.0)

            if score > 0:
                candidates.append({"movieId": movie_id, "score": score})

        # Sort by score descending
        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates[:n]

    def generate_synthetic_events(self, ratings_data):
        """
        Generate synthetic behaviour events from rating data.
        Used for offline evaluation since MovieLens lacks behaviour data.

        Logic:
        - Each rating = a 'view' + 'rating' event
        - Higher ratings = longer simulated duration
        - Rating timestamp is used as event timestamp
        """
        logger.info("Generating synthetic behaviour events from ratings...")
        count = 0

        for row in ratings_data:
            user_id = row["userId"]
            movie_id = row["movieId"]
            rating = row["rating"]
            timestamp = datetime.fromtimestamp(row["timestamp"])

            # View event
            self.add_event(
                user_id, movie_id, "view",
                duration=rating * 20,  # Higher rating = more time spent
                timestamp=timestamp,
            )

            # Rating event
            self.add_event(
                user_id, movie_id, "rating",
                duration=0,
                timestamp=timestamp,
            )

            # Simulate click events for highly-rated movies
            if rating >= 4.0:
                self.add_event(
                    user_id, movie_id, "click",
                    duration=0,
                    timestamp=timestamp,
                )

            count += 1

        logger.info(f"Generated synthetic events for {count} ratings.")
