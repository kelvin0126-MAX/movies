import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { moviesAPI, ratingsAPI, recommendationsAPI } from '../services/api'
import { useBehaviorTracker } from '../hooks/useBehaviorTracker'
import RatingStars from '../components/RatingStars'
import MovieCard from '../components/MovieCard'

export default function MovieDetail({ token, user }) {
  const { id } = useParams()
  const movieId = parseInt(id)
  const [movie, setMovie] = useState(null)
  const [userRating, setUserRating] = useState(0)
  const [similar, setSimilar] = useState([])
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()
  const tracker = useBehaviorTracker(token)

  useEffect(() => {
    loadMovie()
    loadSimilar()
    tracker.startTimeTracking(movieId)

    return () => {
      tracker.stopTimeTracking(movieId)
      tracker.flushEvents()
    }
    // M7: tracker in deps — its callbacks are memoized so this is safe.
  }, [movieId, tracker])

  useEffect(() => {
    if (token) loadUserRating()
  }, [token, movieId])

  const loadMovie = async () => {
    try {
      const res = await moviesAPI.get(movieId)
      setMovie(res.data)
    } catch (err) {
      console.error('Failed to load movie:', err)
    } finally {
      setLoading(false)
    }
  }

  const loadSimilar = async () => {
    try {
      const res = await recommendationsAPI.similar(movieId, 6)
      setSimilar(res.data.similar_movies)
    } catch (err) {
      console.error('Failed to load similar movies:', err)
    }
  }

  const loadUserRating = async () => {
    try {
      const res = await ratingsAPI.userRatings()
      const found = res.data.ratings.find((r) => r.movie_id === movieId)
      if (found) setUserRating(found.rating)
    } catch (err) {
      // Not logged in or no ratings — ignore
    }
  }

  const handleRate = async (rating) => {
    if (!token) return
    try {
      await ratingsAPI.submit(movieId, rating)
      setUserRating(rating)
    } catch (err) {
      console.error('Failed to submit rating:', err)
    }
  }

  if (loading) return <div className="loading">Loading...</div>
  if (!movie) return <div className="loading">Movie not found.</div>

  const genres = movie.genres ? movie.genres.split('|').filter(Boolean) : []

  return (
    <div className="movie-detail">
      {/* Backdrop hero — full-width blurred image behind poster + title */}
      <div
        className="movie-detail-hero"
        style={
          movie.backdrop_url
            ? {
                backgroundImage: `
                  linear-gradient(to bottom, rgba(13,17,23,0.4) 0%, rgba(13,17,23,0.95) 85%, #0d1117 100%),
                  url(${movie.backdrop_url})
                `,
              }
            : undefined
        }
      >
        <div className="movie-detail-hero-inner">
          <div className="movie-detail-poster-wrap">
            {movie.poster_url ? (
              <img
                src={movie.poster_url}
                alt={`${movie.title} poster`}
                className="movie-detail-poster-img"
              />
            ) : (
              <div className="movie-detail-poster-fallback">
                {movie.title}
              </div>
            )}
          </div>

          <div className="movie-detail-info">
            <h1>{movie.title}</h1>
            <p className="year">
              {movie.year || 'Unknown year'}
              {movie.avg_rating ? (
                <>
                  {' · '}
                  <span className="movie-card-rating">
                    ★ {Number(movie.avg_rating).toFixed(1)}
                  </span>
                  <span style={{ color: '#8b949e', marginLeft: 6 }}>
                    ({movie.rating_count || 0} ratings)
                  </span>
                </>
              ) : null}
            </p>

            {genres.length > 0 && (
              <div style={{ marginBottom: 16 }}>
                {genres.map((g) => (
                  <span key={g} className="genre-tag">{g}</span>
                ))}
              </div>
            )}

            {movie.overview && (
              <p className="movie-detail-overview">{movie.overview}</p>
            )}

            {user && (
              <div style={{ marginTop: 20 }}>
                <p style={{ marginBottom: 8, fontWeight: 500 }}>Your Rating:</p>
                <RatingStars
                  rating={userRating}
                  onRate={handleRate}
                  interactive
                />
              </div>
            )}
          </div>
        </div>
      </div>

      {similar.length > 0 && (
        <div className="section">
          <h2 className="section-title">Similar Movies</h2>
          <div className="movie-grid">
            {similar.map((m) => (
              <MovieCard
                key={m.id}
                movie={m}
                onClick={() => {
                  tracker.trackClick(m.id)
                  navigate(`/movie/${m.id}`)
                }}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
