import MovieCard from './MovieCard'

export default function RecommendationList({ title, movies, onMovieClick }) {
  if (!movies || movies.length === 0) return null

  return (
    <div className="section">
      <h2 className="section-title">{title}</h2>
      <div
        style={{
          display: 'flex',
          gap: 16,
          overflowX: 'auto',
          paddingBottom: 12,
        }}
      >
        {movies.map((movie) => (
          <div
            key={movie.id || movie.movie_id}
            style={{ width: 200, flexShrink: 0 }}
          >
            <MovieCard
              movie={movie}
              onClick={() => onMovieClick(movie.id || movie.movie_id)}
            />
          </div>
        ))}
      </div>
    </div>
  )
}
