import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { auth, errorMessage, tokenStore } from '../api/client'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  // On first load, a token in localStorage is only a claim. We verify it
  // against /profile before treating the user as logged in - otherwise an
  // expired token would render the whole app, then fail on every request.
  useEffect(() => {
    const token = tokenStore.get()
    if (!token) {
      setLoading(false)
      return
    }
    auth
      .profile()
      .then((res) => setUser(res.data))
      .catch(() => tokenStore.clear())
      .finally(() => setLoading(false))
  }, [])

  const login = useCallback(async (email, password) => {
    try {
      const { data } = await auth.login({ email, password })
      tokenStore.set(data.access_token)
      setUser(data.user)
      return { ok: true }
    } catch (error) {
      return { ok: false, error: errorMessage(error, 'Could not sign in') }
    }
  }, [])

  const register = useCallback(async (name, email, password) => {
    try {
      const { data } = await auth.register({ name, email, password })
      tokenStore.set(data.access_token)
      setUser(data.user)
      return { ok: true }
    } catch (error) {
      return { ok: false, error: errorMessage(error, 'Could not create account') }
    }
  }, [])

  const logout = useCallback(() => {
    tokenStore.clear()
    setUser(null)
  }, [])

  return (
    <AuthContext.Provider
      value={{ user, loading, login, register, logout, isAdmin: user?.role === 'admin' }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside AuthProvider')
  return context
}
