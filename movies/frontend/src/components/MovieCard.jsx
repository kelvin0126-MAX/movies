import { useRef, useEffect, useState } from 'react'

// Stable hash → gradient hue, so each movie gets a consistent fallback color.
function hashHue(str) {
  let hash = 0
  for (let i = 0; i < str.length; i++) {
    hash = (hash * 31 + str.charCodeAt(i)) | 0
  }
  return Math.abs(hash) % 360
}

export default function MovieCard({ movie, onClick, observeRef, unobserveRef }) {
  const cardRef = useRef(null)
  const [imgError, setImgError] = useState(false)

  useEffect(() => {
    const el = cardRef.current
    if (observeRef && el) {
      observeRef(el)
    }
    // Cleanup: unobserve when this card unmounts (pagination, route change)
    // so the global IntersectionObserver doesn't accumulate dead refs.
    return () => {
      if (unobserveRef && el) {
        unobserveRef(el)
      }
    }
  }, [movie.id, observeRef, unobserveRef])

  const genres = movie.genres ? movie.genres.split('|').filter(Boolean) : []
  const hasPoster = movie.poster_url && !imgError

  // Gradient placeholder hue derived from title (consistent per movie)
  const hue = hashHue(movie.title || '')
  const fallbackStyle = {
    background: `linear-gradient(135deg, hsl(${hue}, 55%, 28%) 0%, hsl(${(hue + 40) % 360}, 60%, 15%) 100%)`,
  }

  return (
    <div className="movie-card" ref={cardRef} onClick={onClick}>
      <div
        className="movie-card-poster"
        style={hasPoster ? {} : fallbackStyle}
      >
        {hasPoster ? (
          <img
            src={movie.poster_url}
            alt={`${movie.title} poster`}
            onError={() => setImgError(true)}
            loading="lazy"
          />
        ) : (
          <div className="movie-card-fallback">
            <div className="movie-card-fallback-title">{movie.title}</div>
            {movie.year ? (
              <div className="movie-card-fallback-year">{movie.year}</div>
            ) : null}
          </div>
        )}
      </div>
      <div className="movie-card-info">
        <div className="movie-card-title">{movie.title}</div>
        <div className="movie-card-meta">
          {movie.year || ''}{' '}
          {movie.avg_rating ? (
            <span className="movie-card-rating">
              ★ {Number(movie.avg_rating).toFixed(1)}
            </span>
          ) : null}
        </div>
        {genres.length > 0 && (
          <div style={{ marginTop: 4 }}>
            {genres.slice(0, 3).map((g) => (
              <span key={g} className="genre-tag">{g}</span>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
