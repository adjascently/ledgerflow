import { createContext, useContext, useEffect, useState, ReactNode } from 'react'
import { getCurrentUser, signOut as amplifySignOut } from 'aws-amplify/auth'

interface AuthUser {
  userId: string
  email: string
}

interface AuthContextType {
  user: AuthUser | null
  loading: boolean
  signOut: () => Promise<void>
  setUser: (u: AuthUser | null) => void
}

const AuthContext = createContext<AuthContextType | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getCurrentUser()
      .then((u) => {
        setUser({
          userId: u.userId,
          email: u.signInDetails?.loginId ?? '',
        })
      })
      .catch(() => setUser(null))
      .finally(() => setLoading(false))
  }, [])

  const signOut = async () => {
    await amplifySignOut()
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, loading, signOut, setUser }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
