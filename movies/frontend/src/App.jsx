import { Routes, Route, Link, useNavigate } from 'react-router-dom'
import { useState, useEffect } from 'react'
import Home from './pages/Home'
import MovieDetail from './pages/MovieDetail'
import Login from './pages/Login'
import Register from './pages/Register'
import Profile from './pages/Profile'
import { useAuth } from './hooks/useAuth'

export default function App() {
  const { user, token, login, logout, register } = useAuth()
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    navigate('/')
  }

  return (
    <div>
      <nav className="navbar">
        <div className="container">
          <Link to="/" className="navbar-brand">
            MovieRec
          </Link>
          <div className="navbar-links">
            <Link to="/">Home</Link>
            {user ? (
              <>
                <Link to="/profile">{user.username}</Link>
                <button className="btn" onClick={handleLogout}>
                  Logout
                </button>
              </>
            ) : (
              <>
                <Link to="/login">Login</Link>
                <Link to="/register">
                  <button className="btn btn-primary">Sign Up</button>
                </Link>
              </>
            )}
          </div>
        </div>
      </nav>

      <div className="container">
        <Routes>
          <Route path="/" element={<Home token={token} />} />
          <Route path="/movie/:id" element={<MovieDetail token={token} user={user} />} />
          <Route path="/login" element={<Login onLogin={login} />} />
          <Route path="/register" element={<Register onRegister={register} />} />
          <Route path="/profile" element={<Profile token={token} user={user} />} />
        </Routes>
      </div>
    </div>
  )
}
