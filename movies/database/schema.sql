-- Movie Recommendation System Database Schema
-- 6 tables as specified in the research proposal

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Movies table
-- poster_path / backdrop_path are TMDB-relative paths (e.g. /abc.jpg) —
-- full URL built in API layer with config.TMDB_IMAGE_BASE + size.
CREATE TABLE IF NOT EXISTS movies (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    genres TEXT,
    year INTEGER,
    tmdb_id INTEGER,
    poster_path TEXT,
    backdrop_path TEXT,
    overview TEXT
);

-- Ratings table
CREATE TABLE IF NOT EXISTS ratings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    movie_id INTEGER NOT NULL,
    rating REAL NOT NULL CHECK(rating >= 1.0 AND rating <= 5.0),
    timestamp INTEGER NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (movie_id) REFERENCES movies(id),
    UNIQUE(user_id, movie_id)
);

-- Behaviour tracking table
-- M6: timestamp is stored as INTEGER (Unix epoch seconds) for consistency
-- with ratings.timestamp. Existing databases with TEXT timestamps will
-- continue to work because SQLite is dynamically typed.
CREATE TABLE IF NOT EXISTS behaviour (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    movie_id INTEGER NOT NULL,
    event_type TEXT NOT NULL CHECK(event_type IN ('view', 'click', 'search', 'rating')),
    duration REAL DEFAULT 0,
    timestamp INTEGER NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (movie_id) REFERENCES movies(id)
);

-- Recommendations cache table
CREATE TABLE IF NOT EXISTS recommendations_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    movie_id INTEGER NOT NULL,
    score REAL NOT NULL,
    algorithm TEXT NOT NULL,
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (movie_id) REFERENCES movies(id)
);

-- Sessions table
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    token TEXT UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Movie stats (pre-computed from Netflix dataset)
CREATE TABLE IF NOT EXISTS movie_stats (
    movie_id INTEGER PRIMARY KEY,
    avg_rating REAL,
    rating_count INTEGER,
    FOREIGN KEY (movie_id) REFERENCES movies(id)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_movie_stats_rating_count ON movie_stats(rating_count DESC);
CREATE INDEX IF NOT EXISTS idx_movie_stats_avg_rating ON movie_stats(avg_rating DESC);
CREATE INDEX IF NOT EXISTS idx_movies_tmdb ON movies(tmdb_id);
CREATE INDEX IF NOT EXISTS idx_ratings_user ON ratings(user_id);
CREATE INDEX IF NOT EXISTS idx_ratings_movie ON ratings(movie_id);
CREATE INDEX IF NOT EXISTS idx_ratings_timestamp ON ratings(timestamp);
CREATE INDEX IF NOT EXISTS idx_behaviour_user ON behaviour(user_id);
CREATE INDEX IF NOT EXISTS idx_behaviour_movie ON behaviour(movie_id);
CREATE INDEX IF NOT EXISTS idx_cache_user ON recommendations_cache(user_id);
CREATE INDEX IF NOT EXISTS idx_cache_generated ON recommendations_cache(generated_at);
CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);
