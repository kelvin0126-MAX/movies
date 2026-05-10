import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { ratingsAPI } from '../services/api'
import RatingStars from '../components/RatingStars'

export default function Profile({ token, user }) {
  const [ratings, setRatings] = useState([])
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  useEffect(() => {
    if (!token) {
      navigate('/login')
      return
    }
    loadRatings()
  }, [token])

  const loadRatings = async () => {
    try {
      const res = await ratingsAPI.userRatings()
      setRatings(res.data.ratings)
    } catch (err) {
      console.error('Failed to load ratings:', err)
    } finally {
      setLoading(false)
    }
  }

  if (!user) return null

  return (
    <div className="section">
      <h2 className="section-title">Profile</h2>

      <div style={{
        background: '#161b22',
        border: '1px solid #30363d',
        borderRadius: 8,
        padding: 24,
        marginBottom: 24,
      }}>
        <p><strong>Username:</strong> {user.username}</p>
        <p><strong>Email:</strong> {user.email || 'N/A'}</p>
        <p><strong>Total Ratings:</strong> {ratings.length}</p>
      </div>

      <h3 className="section-title">Your Ratings</h3>

      {loading ? (
        <div className="loading">Loading...</div>
      ) : ratings.length === 0 ? (
        <p style={{ color: '#8b949e' }}>You haven't rated any movies yet.</p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {ratings.map((r) => (
            <div
              key={r.movie_id}
              style={{
                background: '#161b22',
                border: '1px solid #30363d',
                borderRadius: 8,
                padding: 16,
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                cursor: 'pointer',
              }}
              onClick={() => navigate(`/movie/${r.movie_id}`)}
            >
              <div>
                <p style={{ fontWeight: 600 }}>{r.title}</p>
                <p style={{ fontSize: '0.8rem', color: '#8b949e' }}>
                  {r.genres} {r.year ? `(${r.year})` : ''}
                </p>
              </div>
              <RatingStars rating={r.rating} />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
