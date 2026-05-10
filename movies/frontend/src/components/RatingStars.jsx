import { useState } from 'react'

export default function RatingStars({ rating = 0, onRate, interactive = false }) {
  const [hovered, setHovered] = useState(0)
  const displayRating = hovered || Math.round(rating)

  // L3: Keyboard accessibility — arrow keys and Enter/Space select a rating.
  const handleKeyDown = (e, star) => {
    if (!interactive || !onRate) return
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      onRate(star)
    } else if (e.key === 'ArrowRight' || e.key === 'ArrowUp') {
      e.preventDefault()
      const next = Math.min(5, star + 1)
      onRate(next)
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') {
      e.preventDefault()
      const prev = Math.max(1, star - 1)
      onRate(prev)
    }
  }

  return (
    <div
      className="stars"
      role={interactive ? 'radiogroup' : 'img'}
      aria-label={
        interactive
          ? `Rate this movie. Current rating: ${rating || 0} out of 5.`
          : `Rating: ${rating || 0} out of 5.`
      }
    >
      {[1, 2, 3, 4, 5].map((star) => (
        <span
          key={star}
          className={`star ${star <= displayRating ? 'active' : ''}`}
          onMouseEnter={() => interactive && setHovered(star)}
          onMouseLeave={() => interactive && setHovered(0)}
          onClick={() => interactive && onRate && onRate(star)}
          onKeyDown={(e) => handleKeyDown(e, star)}
          role={interactive ? 'radio' : undefined}
          aria-checked={interactive ? star === Math.round(rating) : undefined}
          aria-label={interactive ? `${star} star${star > 1 ? 's' : ''}` : undefined}
          tabIndex={interactive ? 0 : -1}
          style={{ cursor: interactive ? 'pointer' : 'default' }}
        >
          ★
        </span>
      ))}
      {rating > 0 && (
        <span style={{ fontSize: '0.85rem', color: '#8b949e', marginLeft: 4 }}>
          {Number(rating).toFixed(1)}
        </span>
      )}
    </div>
  )
}
