import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
})

// Attach auth token to requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// C2: Handle expired/invalid tokens — clear local state and signal auth layer.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      const hadToken = !!localStorage.getItem('token')
      if (hadToken) {
        localStorage.removeItem('token')
        // useAuth listens for this to reset user state and redirect to login
        window.dispatchEvent(new Event('auth:unauthorized'))
      }
    }
    return Promise.reject(error)
  }
)

// Auth
export const authAPI = {
  register: (data) => api.post('/auth/register', data),
  login: (data) => api.post('/auth/login', data),
  logout: () => api.post('/auth/logout'),
  profile: () => api.get('/auth/profile'),
}

// Movies
export const moviesAPI = {
  list: (page = 1, perPage = 20, genre = '') =>
    api.get('/movies/', { params: { page, per_page: perPage, genre } }),
  get: (id) => api.get(`/movies/${id}`),
  search: (q) => api.get('/movies/search', { params: { q } }),
  genres: () => api.get('/movies/genres'),
}

// Ratings
export const ratingsAPI = {
  submit: (movieId, rating) => api.post('/ratings/', { movie_id: movieId, rating }),
  userRatings: () => api.get('/ratings/user'),
  movieRatings: (movieId) => api.get(`/ratings/movie/${movieId}`),
}

// Recommendations
export const recommendationsAPI = {
  get: (n = 20) => api.get('/recommendations/', { params: { n } }),
  similar: (movieId, n = 10) => api.get(`/recommendations/similar/${movieId}`, { params: { n } }),
  popular: (n = 20) => api.get('/recommendations/popular', { params: { n } }),
}

// Behavior tracking
export const behaviorAPI = {
  log: (movieId, eventType, duration = 0) =>
    api.post('/behavior/', { movie_id: movieId, event_type: eventType, duration }),
  logBatch: (events) => api.post('/behavior/batch', { events }),
}

export default api
