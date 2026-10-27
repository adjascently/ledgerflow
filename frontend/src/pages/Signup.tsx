import { useState, FormEvent } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { signUp, confirmSignUp, signIn, getCurrentUser } from 'aws-amplify/auth'
import { createUser } from '../services/api'
import { useAuth } from '../context/AuthContext'

type Step = 'register' | 'confirm'

export default function Signup() {
  const [step, setStep] = useState<Step>('register')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()
  const { setUser } = useAuth()

  const handleRegister = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    if (password !== confirm) { setError('Passwords do not match'); return }
    setLoading(true)
    try {
      await signUp({ username: email, password, options: { userAttributes: { email } } })
      setStep('confirm')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Sign up failed')
    } finally {
      setLoading(false)
    }
  }

  const handleConfirm = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await confirmSignUp({ username: email, confirmationCode: code })
      // Sign in to get the userId from Cognito
      await signIn({ username: email, password })
      const u = await getCurrentUser()
      // Create the user profile in Swathi's DynamoDB
      await createUser(u.userId, email)
      setUser({ userId: u.userId, email })
      navigate('/dashboard')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Confirmation failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        {step === 'register' ? (
          <>
            <h1 className="auth-title">Create account</h1>
            <p className="auth-sub">Start tracking your finances</p>
            {error && <div className="alert alert-error">{error}</div>}
            <form onSubmit={handleRegister} className="auth-form">
              <div className="field">
                <label>Email</label>
                <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" required />
              </div>
              <div className="field">
                <label>Password</label>
                <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="8+ characters" required />
              </div>
              <div className="field">
                <label>Confirm password</label>
                <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} placeholder="••••••••" required />
              </div>
              <button type="submit" className="btn-primary" disabled={loading}>
                {loading ? 'Creating account…' : 'Create account'}
              </button>
            </form>
            <p className="auth-switch">Already have an account? <Link to="/login">Sign in</Link></p>
          </>
        ) : (
          <>
            <h1 className="auth-title">Check your email</h1>
            <p className="auth-sub">We sent a 6-digit code to <strong>{email}</strong></p>
            {error && <div className="alert alert-error">{error}</div>}
            <form onSubmit={handleConfirm} className="auth-form">
              <div className="field">
                <label>Confirmation code</label>
                <input type="text" value={code} onChange={(e) => setCode(e.target.value)} placeholder="123456" maxLength={6} required />
              </div>
              <button type="submit" className="btn-primary" disabled={loading}>
                {loading ? 'Confirming…' : 'Confirm & continue'}
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  )
}
