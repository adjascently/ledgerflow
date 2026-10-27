import { FormEvent, useEffect, useMemo, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { getUserProfile, updateSpendingThreshold } from '../services/api'

export default function Alerts() {
  const { user } = useAuth()
  const [threshold, setThreshold] = useState(1000)
  const [draftThreshold, setDraftThreshold] = useState('1000')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const alertTypes = useMemo(() => ([
    {
      title: 'Spending threshold exceeded',
      description: `Triggered when your total monthly spending goes above $${threshold.toLocaleString()}. You receive an email with a full category breakdown.`,
      status: 'active',
    },
    {
      title: 'Statement processed',
      description: 'Sent after each bank statement upload is successfully analysed by the automated workflow.',
      status: 'active',
    },
    {
      title: 'Processing failed',
      description: 'Sent if the workflow encounters an error while processing your statement.',
      status: 'active',
    },
    {
      title: 'Unusual transaction detected',
      description: 'Flags transactions significantly above your average spend in a category.',
      status: 'coming-soon',
    },
  ]), [threshold])

  useEffect(() => {
    if (!user) return
    setLoading(true)
    setError('')
    getUserProfile(user.userId)
      .then((data) => {
        const nextThreshold = Number(data.user.spendingThreshold ?? 1000)
        setThreshold(nextThreshold)
        setDraftThreshold(String(nextThreshold))
      })
      .catch(() => setError('Could not load alert settings'))
      .finally(() => setLoading(false))
  }, [user])

  const onSave = async (e: FormEvent) => {
    e.preventDefault()
    if (!user) return
    setSaving(true)
    setError('')
    setMessage('')

    const numericThreshold = Number(draftThreshold)
    if (!Number.isFinite(numericThreshold) || numericThreshold <= 0) {
      setSaving(false)
      setError('Threshold must be a positive number.')
      return
    }

    try {
      const data = await updateSpendingThreshold(user.userId, numericThreshold)
      const nextThreshold = Number(data.user.spendingThreshold ?? numericThreshold)
      setThreshold(nextThreshold)
      setDraftThreshold(String(nextThreshold))
      setMessage('Spending threshold updated.')
    } catch {
      setError('Could not update spending threshold')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="page">
      <div className="page-header">
        <h1 className="page-title">Alerts</h1>
        <span className="page-subtitle">Notifications sent to {user?.email}</span>
      </div>

      <div className="alert-info-card">
        <h3>How alerts work</h3>
        <p>
          Alerts are delivered by email via Amazon SNS. When you upload a bank statement,
          an automated workflow analyses your transactions and sends a summary to your inbox —
          usually within a minute.
        </p>
      </div>

      {error && <div className="alert alert-error">{error}</div>}
      {message && <div className="alert">{message}</div>}

      <h2 className="section-heading">Alert types</h2>
      <div className="alert-list">
        {alertTypes.map((a) => (
          <div key={a.title} className="alert-item">
            <div className="alert-item-header">
              <span className="alert-item-title">{a.title}</span>
              <span className={`alert-status ${a.status === 'active' ? 'status-active' : 'status-soon'}`}>
                {a.status === 'active' ? 'Active' : 'Coming soon'}
              </span>
            </div>
            <p className="alert-item-desc">{a.description}</p>
          </div>
        ))}
      </div>

      <div className="alert-info-card" style={{ marginTop: '24px' }}>
        <h3>Spending threshold</h3>
        {loading ? (
          <p>Loading alert settings…</p>
        ) : (
          <>
            <p>Current threshold: <strong>${threshold.toLocaleString()} / month</strong></p>
            <form onSubmit={onSave} style={{ marginTop: '16px', display: 'flex', gap: '12px', alignItems: 'end', flexWrap: 'wrap' }}>
              <div className="field-inline">
                <label>Monthly threshold</label>
                <input
                  type="number"
                  min="1"
                  step="1"
                  value={draftThreshold}
                  onChange={(e) => setDraftThreshold(e.target.value)}
                />
              </div>
              <button className="btn-primary" type="submit" disabled={saving}>
                {saving ? 'Saving…' : 'Save threshold'}
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  )
}
