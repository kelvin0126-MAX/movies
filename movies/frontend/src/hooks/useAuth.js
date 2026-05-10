import { useState, useEffect } from 'react'
import { authAPI } from '../services/api'

export function useAuth() {
  const [user, setUser] = useState(null)
  const [token, setToken] = useState(localStorage.getItem('token'))

  useEffect(() => {
    if (token) {
      authAPI
        .profile()
        .then((res) => setUser(res.data))
        .catch(() => {
          localStorage.removeItem('token')
          setToken(null)
          setUser(null)
        })
    }
  }, [token])

  // C2: React to 401 events from Axios interceptor
  useEffect(() => {
    const handleUnauthorized = () => {
      setToken(null)
      setUser(null)
    }
    window.addEventListener('auth:unauthorized', handleUnauthorized)
    return () => window.removeEventListener('auth:unauthorized', handleUnauthorized)
  }, [])

  const login = async (username, password) => {
    const res = await authAPI.login({ username, password })
    const { token: newToken, user_id, username: name, email } = res.data
    localStorage.setItem('token', newToken)
    setToken(newToken)
    setUser({ id: user_id, username: name, email })
    return res.data
  }

  const register = async (username, email, password) => {
    const res = await authAPI.register({ username, email, password })
    const { token: newToken, user_id } = res.data
    localStorage.setItem('token', newToken)
    setToken(newToken)
    // H5: Include email in user state so Profile page renders correctly
    setUser({ id: user_id, username, email })
    return res.data
  }

  const logout = async () => {
    try {
      await authAPI.logout()
    } catch (e) {
      // Ignore logout errors
    }
    localStorage.removeItem('token')
    setToken(null)
    setUser(null)
  }

  return { user, token, login, logout, register }
}
