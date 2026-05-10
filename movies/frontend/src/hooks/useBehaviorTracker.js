import { useEffect, useMemo, useRef, useCallback } from 'react'
import { behaviorAPI } from '../services/api'

/**
 * Behavior tracking hook using IntersectionObserver.
 * Tracks: views (scroll into viewport), clicks, and time spent.
 */
export function useBehaviorTracker(token) {
  const eventsBuffer = useRef([])
  const flushTimer = useRef(null)
  const startTimes = useRef({})

  // Flush buffered events every 10 seconds (only if there's something to flush)
  useEffect(() => {
    if (!token) return

    flushTimer.current = setInterval(() => {
      // Skip interval if buffer empty — avoids wasted API calls (M8)
      if (eventsBuffer.current.length > 0) {
        flushEvents()
      }
    }, 10000)

    return () => {
      flushEvents()
      clearInterval(flushTimer.current)
    }
  }, [token])

  const flushEvents = useCallback(() => {
    if (eventsBuffer.current.length === 0 || !token) return

    const events = [...eventsBuffer.current]
    eventsBuffer.current = []

    behaviorAPI.logBatch(events).catch(() => {
      // Re-add failed events to buffer
      eventsBuffer.current.push(...events)
    })
  }, [token])

  const trackView = useCallback(
    (movieId) => {
      if (!token) return
      eventsBuffer.current.push({
        movie_id: movieId,
        event_type: 'view',
        duration: 0,
      })
    },
    [token]
  )

  const trackClick = useCallback(
    (movieId) => {
      if (!token) return
      eventsBuffer.current.push({
        movie_id: movieId,
        event_type: 'click',
        duration: 0,
      })
    },
    [token]
  )

  const startTimeTracking = useCallback((movieId) => {
    startTimes.current[movieId] = Date.now()
  }, [])

  const stopTimeTracking = useCallback(
    (movieId) => {
      if (!token || !startTimes.current[movieId]) return

      const duration = (Date.now() - startTimes.current[movieId]) / 1000
      delete startTimes.current[movieId]

      if (duration > 2) {
        eventsBuffer.current.push({
          movie_id: movieId,
          event_type: 'view',
          duration,
        })
      }
    },
    [token]
  )

  const trackSearch = useCallback(
    (movieId) => {
      if (!token) return
      eventsBuffer.current.push({
        movie_id: movieId,
        event_type: 'search',
        duration: 0,
      })
    },
    [token]
  )

  // IntersectionObserver for tracking when movie cards enter viewport
  const observerRef = useRef(null)

  const observe = useCallback(
    (element, movieId) => {
      if (!token || !element) return

      if (!observerRef.current) {
        observerRef.current = new IntersectionObserver(
          (entries) => {
            entries.forEach((entry) => {
              if (entry.isIntersecting) {
                const mid = entry.target.dataset.movieId
                if (mid) trackView(parseInt(mid))
              }
            })
          },
          { threshold: 0.5 }
        )
      }

      element.dataset.movieId = movieId
      observerRef.current.observe(element)
    },
    [token, trackView]
  )

  const unobserve = useCallback((element) => {
    if (element && observerRef.current) {
      observerRef.current.unobserve(element)
    }
  }, [])

  // C1: Disconnect observer on unmount to prevent memory leak
  useEffect(() => {
    return () => {
      if (observerRef.current) {
        observerRef.current.disconnect()
        observerRef.current = null
      }
    }
  }, [])

  // Memoize the returned object so consumers can safely include `tracker`
  // in effect deps without causing infinite re-renders (M7 regression fix).
  // Identity only changes when one of the memoized callbacks does.
  return useMemo(
    () => ({
      trackView,
      trackClick,
      trackSearch,
      startTimeTracking,
      stopTimeTracking,
      observe,
      unobserve,
      flushEvents,
    }),
    [
      trackView, trackClick, trackSearch,
      startTimeTracking, stopTimeTracking,
      observe, unobserve, flushEvents,
    ]
  )
}
