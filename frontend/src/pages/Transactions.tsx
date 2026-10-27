import { useEffect, useState } from 'react'
import { getTransactions, Transaction } from '../services/api'
import { useAuth } from '../context/AuthContext'
import { useSearchParams } from 'react-router-dom'
import { formatCategoryLabel } from '../utils/categories'

interface UploadMeta {
  uploadId: string
  fileName?: string
  uploadedAt?: string
}

function currentMonthRange() {
  const now = new Date()
  const y = now.getFullYear()
  const m = String(now.getMonth() + 1).padStart(2, '0')
  return { start: `${y}-${m}-01`, end: `${y}-${m}-31` }
}

export default function Transactions() {
  const { user } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()
  const range = currentMonthRange()
  const [startDate, setStartDate] = useState(range.start)
  const [endDate, setEndDate] = useState(range.end)
  const [uploadId, setUploadId] = useState('')
  const [latestUploadMeta, setLatestUploadMeta] = useState<UploadMeta | null>(null)
  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = () => {
    if (!user) return
    setLoading(true)
    getTransactions(user.userId, startDate, endDate, uploadId || undefined)
      .then((d) => setTransactions(d.transactions))
      .catch(() => setError('Could not load transactions'))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    if (!user) return
    const uploadIdFromQuery = searchParams.get('uploadId')
    const rawMeta = localStorage.getItem(`finance:lastUploadMeta:${user.userId}`)
    let parsedMeta: UploadMeta | null = null
    if (rawMeta) {
      try {
        parsedMeta = JSON.parse(rawMeta) as UploadMeta
      } catch {
        parsedMeta = null
      }
    }
    setLatestUploadMeta(parsedMeta)
    setUploadId(uploadIdFromQuery || parsedMeta?.uploadId || '')
  }, [user, searchParams])

  useEffect(() => { load() }, [user, uploadId])

  const applyFilters = () => {
    const nextParams = new URLSearchParams(searchParams)
    if (uploadId) nextParams.set('uploadId', uploadId)
    else nextParams.delete('uploadId')
    setSearchParams(nextParams)
    load()
  }

  const clearUploadFilter = () => {
    setUploadId('')
    const nextParams = new URLSearchParams(searchParams)
    nextParams.delete('uploadId')
    setSearchParams(nextParams)
  }

  const useLatestUpload = () => {
    if (!latestUploadMeta?.uploadId) return
    setUploadId(latestUploadMeta.uploadId)
    const nextParams = new URLSearchParams(searchParams)
    nextParams.set('uploadId', latestUploadMeta.uploadId)
    setSearchParams(nextParams)
  }

  return (
    <div className="page">
      <div className="page-header">
        <h1 className="page-title">Transactions</h1>
      </div>

      <div className="filter-bar">
        <div className="field-inline">
          <label>From</label>
          <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
        </div>
        <div className="field-inline">
          <label>To</label>
          <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
        </div>
        <div className="field-inline">
          <label>Upload ID</label>
          <input
            type="text"
            value={uploadId}
            onChange={(e) => setUploadId(e.target.value)}
            placeholder="Latest upload by default"
          />
        </div>
        <button className="btn-primary" onClick={applyFilters}>Apply</button>
        {uploadId && <button className="btn-ghost" onClick={clearUploadFilter}>Show all uploads</button>}
      </div>

      {uploadId && (
        <div className="alert" style={{ marginBottom: 16 }}>
          <strong>Viewing upload:</strong> {uploadId}
        </div>
      )}

      {latestUploadMeta?.uploadId && latestUploadMeta.uploadId !== uploadId && (
        <div className="alert" style={{ marginBottom: 16 }}>
          <strong>Latest upload available:</strong> {latestUploadMeta.uploadId}
          {latestUploadMeta.fileName && ` (${latestUploadMeta.fileName})`}
          <button className="btn-ghost" style={{ marginLeft: 12 }} onClick={useLatestUpload}>
            Use latest upload
          </button>
        </div>
      )}

      {error && <div className="alert alert-error">{error}</div>}

      {loading ? (
        <div className="page-loading">Loading transactions…</div>
      ) : transactions.length === 0 ? (
        <div className="empty-state">
          <p>No transactions found for this date range.</p>
        </div>
      ) : (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Merchant</th>
                <th>Category</th>
                <th>Payment</th>
                <th style={{ textAlign: 'right' }}>Amount</th>
              </tr>
            </thead>
            <tbody>
              {transactions.map((t) => (
                <tr key={t.transactionId}>
                  <td>{t.date}</td>
                  <td>{t.merchant}</td>
                  <td><span className="category-badge">{formatCategoryLabel(t.category)}</span></td>
                  <td>{t.paymentMethod}</td>
                  <td style={{ textAlign: 'right', fontWeight: 500 }}>${Number(t.amount).toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="table-footer">{transactions.length} transactions</div>
        </div>
      )}
    </div>
  )
}
