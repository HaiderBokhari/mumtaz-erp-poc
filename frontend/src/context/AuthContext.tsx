import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import api, { clearTokens, getAccessToken, setTokens } from '../api/client'
import type { Me } from '../types'

interface AuthContextValue {
  me: Me | null
  loading: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => void
  hasRole: (...roles: string[]) => boolean
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null)
  const [loading, setLoading] = useState(true)

  async function fetchMe() {
    try {
      const response = await api.get<Me[] | Me>('me/')
      const data = Array.isArray(response.data) ? response.data[0] : response.data
      setMe(data ?? null)
    } catch {
      setMe(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (getAccessToken()) {
      fetchMe()
    } else {
      setLoading(false)
    }
  }, [])

  async function login(username: string, password: string) {
    const response = await api.post('auth/token/', { username, password })
    setTokens(response.data.access, response.data.refresh)
    await fetchMe()
  }

  function logout() {
    clearTokens()
    setMe(null)
  }

  function hasRole(...roles: string[]) {
    if (!me) return false
    if (me.is_superuser) return true
    return roles.some((r) => me.roles.includes(r))
  }

  return (
    <AuthContext.Provider value={{ me, loading, login, logout, hasRole }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
