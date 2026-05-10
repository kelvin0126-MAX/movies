import { useState, useRef, useEffect, useCallback } from 'react'

export default function SearchBar({ onSearch }) {
  const [query, setQuery] = useState('')
  // H1: Use ref for timer so handleChange doesn't recreate every keystroke
  const timerRef = useRef(null)

  const handleChange = useCallback(
    (e) => {
      const value = e.target.value
      setQuery(value)

      // Debounce search by 400ms
      if (timerRef.current) clearTimeout(timerRef.current)
      timerRef.current = setTimeout(() => {
        onSearch(value)
      }, 400)
    },
    [onSearch]
  )

  const handleSubmit = (e) => {
    e.preventDefault()
    if (timerRef.current) clearTimeout(timerRef.current)
    onSearch(query)
  }

  // Clean up pending timer on unmount
  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [])

  return (
    <form
      onSubmit={handleSubmit}
      style={{ padding: '20px 0' }}
      role="search"
    >
      <label htmlFor="movie-search-input" className="visually-hidden">
        Search movies
      </label>
      <input
        id="movie-search-input"
        type="search"
        className="search-bar"
        placeholder="Search movies..."
        value={query}
        onChange={handleChange}
        aria-label="Search movies"
        autoComplete="off"
      />
    </form>
  )
}
