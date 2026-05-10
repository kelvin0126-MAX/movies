import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { moviesAPI, recommendationsAPI } from '../services/api'
import { useBehaviorTracker } from '../hooks/useBehaviorTracker'
import MovieCard from '../components/MovieCard'
import SearchBar from '../components/SearchBar'
import RecommendationList from '../components/RecommendationList'

export default function Home({ token }) {
  const [movies, setMovies] = useState([])
  const [recommendations, setRecommendations] = useState([])
  const [popular, setPopular] = useState([])
  const [genres, setGenres] = useState([])
  const [selectedGenre, setSelectedGenre] = useState('')
  const [searchResults, setSearchResults] = useState(null)
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const navigate = useNavigate()
  const tracker = useBehaviorTracker(token)

  useEffect(() => {
    loadMovies()
    loadGenres()
    loadPopular()
  }, [])

  useEffect(() => {
    if (token) {
      loadRecommendations()
    }
  }, [token])

  useEffect(() => {
    loadMovies()
  }, [page, selectedGenre])

  const loadMovies = async () => {
    try {
      const res = await moviesAPI.list(page, 20, selectedGenre)
      setMovies(res.data.movies)
    } catch (err) {
      console.error('Failed to load movies:', err)
    } finally {
      setLoading(false)
    }
  }

  const loadGenres = async () => {
    try {
      const res = await moviesAPI.genres()
      setGenres(res.data.genres)
    } catch (err) {
      console.error('Failed to load genres:', err)
    }
  }

  const loadRecommendations = async () => {
    try {
      const res = await recommendationsAPI.get(10)
      setRecommendations(res.data.recommendations)
    } catch (err) {
      console.error('Failed to load recommendations:', err)
    }
  }

  const loadPopular = async () => {
    try {
      const res = await recommendationsAPI.popular(10)
      setPopular(res.data.movies)
    } catch (err) {
      console.error('Failed to load popular:', err)
    }
  }

  const handleSearch = async (query) => {
    if (!query.trim()) {
      setSearchResults(null)
      return
    }
    try {
      const res = await moviesAPI.search(query)
      setSearchResults(res.data.movies)
    } catch (err) {
      console.error('Search failed:', err)
    }
  }

  const handleMovieClick = (movieId) => {
    tracker.trackClick(movieId)
    navigate(`/movie/${movieId}`)
  }

  if (loading) {
    return <div className="loading">Loading movies...</div>
  }

  return (
    <div>
      <div className="section">
        <SearchBar onSearch={handleSearch} />
      </div>

      {searchResults && (
        <div className="section">
          <h2 className="section-title">Search Results</h2>
          <div className="movie-grid">
            {searchResults.map((movie) => (
              <MovieCard
                key={movie.id}
                movie={movie}
                onClick={() => handleMovieClick(movie.id)}
                observeRef={(el) => tracker.observe(el, movie.id)}
                unobserveRef={(el) => tracker.unobserve(el)}
              />
            ))}
          </div>
          {searchResults.length === 0 && <p>No movies found.</p>}
        </div>
      )}

      {!searchResults && token && recommendations.length > 0 && (
        <RecommendationList
          title="Recommended For You"
          movies={recommendations}
          onMovieClick={handleMovieClick}
        />
      )}

      {!searchResults && popular.length > 0 && (
        <RecommendationList
          title="Popular Movies"
          movies={popular}
          onMovieClick={handleMovieClick}
        />
      )}

      {!searchResults && (
        <div className="section">
          <h2 className="section-title">
            {selectedGenre ? `${selectedGenre} Movies` : 'All Movies'}
          </h2>

          <div style={{ marginBottom: 16, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button
              className={`genre-tag ${!selectedGenre ? 'active' : ''}`}
              onClick={() => { setSelectedGenre(''); setPage(1) }}
              style={!selectedGenre ? { background: '#238636', color: '#fff' } : {}}
            >
              All
            </button>
            {genres.map((g) => (
              <button
                key={g}
                className="genre-tag"
                onClick={() => { setSelectedGenre(g); setPage(1) }}
                style={selectedGenre === g ? { background: '#238636', color: '#fff' } : {}}
              >
                {g}
              </button>
            ))}
          </div>

          <div className="movie-grid">
            {movies.map((movie) => (
              <MovieCard
                key={movie.id}
                movie={movie}
                onClick={() => handleMovieClick(movie.id)}
                observeRef={(el) => tracker.observe(el, movie.id)}
                unobserveRef={(el) => tracker.unobserve(el)}
              />
            ))}
          </div>

          <div style={{ display: 'flex', gap: 12, justifyContent: 'center', padding: 20 }}>
            <button
              className="btn"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
            >
              Previous
            </button>
            <span style={{ padding: '8px 0', color: '#8b949e' }}>Page {page}</span>
            <button
              className="btn"
              onClick={() => setPage((p) => p + 1)}
              // Disable when current page is short (last page) — server returns
              // up to 20 items per page so anything < 20 means we've hit the end.
              disabled={movies.length < 20}
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
