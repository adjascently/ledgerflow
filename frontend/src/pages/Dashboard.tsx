import { useEffect, useState } from 'react'
import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  ResponsiveContainer,
  Legend,
  LineChart,
  Line,
  CartesianGrid,
  XAxis,
  YAxis,
} from 'recharts'
import {
  getTransactions,
  getCategorySpending,
  getMlPredictions,
  getMonthlySummary,
  CategoryAmount,
  MonthlySummary,
  MlPredictionsResponse,
  Transaction,
} from '../services/api'
import { useAuth } from '../context/AuthContext'
import { formatCategoryLabel } from '../utils/categories'

const COLORS = ['#2D6A4F', '#40916C', '#74C69D', '#B7E4C7', '#95D5B2', '#1B4332', '#52B788']

interface UploadMeta {
  uploadId: string
  fileName?: string
  uploadedAt?: string
}

function currentMonth() {
  return new Date().toISOString().slice(0, 7)
}

export default function Dashboard() {
  const { user } = useAuth()
  const [summary, setSummary] = useState<MonthlySummary | null>(null)
  const [categories, setCategories] = useState<CategoryAmount[]>([])
  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [predictionData, setPredictionData] = useState<MlPredictionsResponse | null>(null)
  const [predictionError, setPredictionError] = useState('')
  const [selectedMonth, setSelectedMonth] = useState(currentMonth())
  const [resolvedMonth, setResolvedMonth] = useState(currentMonth())
  const [activeUploadId, setActiveUploadId] = useState('')
  const [latestUploadMeta, setLatestUploadMeta] = useState<UploadMeta | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!user) return
    let cancelled = false

    const loadInitialMonth = async () => {
      setLoading(true)
      setError('')
      try {
        const rawMeta = localStorage.getItem(`finance:lastUploadMeta:${user.userId}`)
        let parsedMeta: UploadMeta | null = null
        if (rawMeta) {
          try {
            parsedMeta = JSON.parse(rawMeta) as UploadMeta
          } catch {
            parsedMeta = null
          }
        }
        if (cancelled) return
        setLatestUploadMeta(parsedMeta)

        const latestTransactions = await getTransactions(
          user.userId,
          undefined,
          undefined,
          parsedMeta?.uploadId || undefined,
        )
        if (cancelled) return

        const latestTransactionDate =
          latestTransactions.transactions[0]?.date ||
          (await getTransactions(user.userId)).transactions[0]?.date ||
          `${currentMonth()}-01`

        const month = latestTransactionDate.slice(0, 7)
        setSelectedMonth(month)
        setResolvedMonth(month)
        setActiveUploadId(parsedMeta?.uploadId || '')
      } catch {
        if (!cancelled) setError('Could not determine a dashboard month')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    void loadInitialMonth()

    return () => {
      cancelled = true
    }
  }, [user])

  useEffect(() => {
    if (!user || !resolvedMonth) return
    let cancelled = false
    setLoading(true)
    setError('')
    setPredictionError('')
    Promise.allSettled([
      getMonthlySummary(user.userId, resolvedMonth, activeUploadId || undefined),
      getCategorySpending(user.userId, resolvedMonth, activeUploadId || undefined),
      getTransactions(
        user.userId,
        `${resolvedMonth}-01`,
        `${resolvedMonth}-31`,
        activeUploadId || undefined,
      ),
      getMlPredictions(user.userId, resolvedMonth),
    ])
      .then((results) => {
        if (cancelled) return
        const [sumResult, catResult, txnResult, predictionResult] = results

        if (
          sumResult.status !== 'fulfilled' ||
          catResult.status !== 'fulfilled' ||
          txnResult.status !== 'fulfilled'
        ) {
          setError('Could not load dashboard data')
          return
        }

        setSummary(sumResult.value)
        setCategories(catResult.value.categories)
        setTransactions(txnResult.value.transactions)

        if (predictionResult.status === 'fulfilled') {
          setPredictionData(predictionResult.value)
          setPredictionError('')
        } else {
          setPredictionData(null)
          setPredictionError('Predictions are currently unavailable.')
        }
      })
      .catch(() => {
        if (!cancelled) setError('Could not load dashboard data')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [user, resolvedMonth, activeUploadId])

  if (loading) return <div className="page-loading">Loading dashboard…</div>
  if (error) return <div className="alert alert-error">{error}</div>

  const expenses = transactions
    .filter((txn) => Number(txn.amount) < 0)
    .map((txn) => ({ ...txn, spend: Math.abs(Number(txn.amount)) }))

  const income = transactions
    .filter((txn) => Number(txn.amount) > 0)
    .reduce((sum, txn) => sum + Number(txn.amount), 0)

  const averageExpense = expenses.length
    ? expenses.reduce((sum, txn) => sum + txn.spend, 0) / expenses.length
    : 0

  const largestExpense = expenses.reduce<(typeof expenses)[number] | null>(
    (current, txn) => (!current || txn.spend > current.spend ? txn : current),
    null,
  )

  const merchantSpend = new Map<string, { merchant: string; amount: number; count: number }>()
  expenses.forEach((txn) => {
    const merchant = txn.merchant || 'Unknown merchant'
    const existing = merchantSpend.get(merchant)
    if (existing) {
      existing.amount += txn.spend
      existing.count += 1
    } else {
      merchantSpend.set(merchant, { merchant, amount: txn.spend, count: 1 })
    }
  })
  const topMerchants = Array.from(merchantSpend.values())
    .sort((a, b) => b.amount - a.amount)
    .slice(0, 5)

  const dailySpendMap = new Map<string, number>()
  expenses.forEach((txn) => {
    dailySpendMap.set(txn.date, (dailySpendMap.get(txn.date) ?? 0) + txn.spend)
  })
  const dailySpend = Array.from(dailySpendMap.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, amount]) => ({
      date: date.slice(5),
      amount,
    }))

  const largestExpenses = [...expenses]
    .sort((a, b) => b.spend - a.spend)
    .slice(0, 5)

  const pieCategories = categories
    .map((category) => ({
      category: formatCategoryLabel(category.category),
      amount: Number(category.amount),
    }))
    .filter((category) => Number.isFinite(category.amount) && category.amount > 0)

  const prediction = predictionData?.prediction ?? null
  const forecastAmount = prediction ? Number(prediction.forecastAmount) : null
  const anomalyRisk = prediction?.anomalyRisk
  const anomalyLevel = anomalyRisk?.level || 'low'
  const anomalyBadgeClass =
    anomalyLevel === 'high'
      ? 'signal-badge signal-critical'
      : anomalyLevel === 'medium'
        ? 'signal-badge signal-warning'
        : 'signal-badge signal-info'
  const predictedCategories = (prediction?.predictedTopCategories ?? []).slice(0, 3)
  return (
    <div className="page">
      <div className="page-header">
        <h1 className="page-title">Dashboard</h1>
        <span className="page-subtitle">{resolvedMonth}</span>
      </div>

      <div className="filter-bar" style={{ marginBottom: 24 }}>
        <div className="field-inline">
          <label>Month</label>
          <input
            type="month"
            value={selectedMonth}
            onChange={(e) => setSelectedMonth(e.target.value)}
          />
        </div>
        <button className="btn-primary" onClick={() => setResolvedMonth(selectedMonth)}>
          Apply
        </button>
        {latestUploadMeta?.uploadId && (
          <div className="alert" style={{ marginBottom: 0 }}>
            <strong>Scoped to latest upload:</strong> {latestUploadMeta.uploadId}
          </div>
        )}
      </div>

      <div className="alert" style={{ marginBottom: 24 }}>
        <strong>AWS-backed analytics:</strong> these metrics are served from the backend analytics APIs and reporting aggregates stored in RDS.
      </div>

      <div className="metric-grid">
        <div className="metric-card">
          <span className="metric-label">Total spent</span>
          <span className="metric-value">${summary?.totalSpent?.toFixed(2) ?? '—'}</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Transactions</span>
          <span className="metric-value">{summary?.transactionCount ?? '—'}</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Top category</span>
          <span className="metric-value">{summary?.topCategory ? formatCategoryLabel(summary.topCategory) : '—'}</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Average expense</span>
          <span className="metric-value">${averageExpense.toFixed(2)}</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Largest expense</span>
          <span className="metric-value metric-value-sm">
            {largestExpense ? `$${largestExpense.spend.toFixed(2)}` : '—'}
          </span>
          {largestExpense && <span className="metric-note">{largestExpense.merchant}</span>}
        </div>
        <div className="metric-card">
          <span className="metric-label">Money in</span>
          <span className="metric-value">${income.toFixed(2)}</span>
          <span className="metric-note">Positive statement entries</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Forecast next month</span>
          <span className="metric-value">
            {forecastAmount !== null ? `$${forecastAmount.toFixed(2)}` : '—'}
          </span>
          <span className="metric-note">
            {prediction ? `${prediction.forecastConfidence} confidence · ${prediction.source}` : 'ML prediction'}
          </span>
        </div>
      </div>

      {(prediction || predictionError) && (
        <div className="analytics-panel" style={{ marginBottom: 16 }}>
          <h2 className="chart-title">Prediction signals</h2>
          {prediction ? (
            <div className="analytics-stack">
              <div className="signal-card">
                <div className="signal-header">
                  <span className="signal-title">Anomaly risk</span>
                  <span className={anomalyBadgeClass}>{anomalyLevel}</span>
                </div>
                <div className="signal-text">{anomalyRisk?.reason || 'No anomaly explanation available.'}</div>
                <div className="signal-subtext">
                  Score: {anomalyRisk?.score?.toFixed(2) ?? '0.00'} · Model: {prediction.modelName}
                </div>
              </div>

              <div className="signal-card">
                <div className="signal-header">
                  <span className="signal-title">Predicted top categories</span>
                  <span className="signal-badge signal-info">{prediction.source}</span>
                </div>
                {predictedCategories.length > 0 ? (
                  predictedCategories.map((item) => (
                    <div key={item.category} className="signal-subtext">
                      <strong>{formatCategoryLabel(item.category)}</strong> · {(item.confidence * 100).toFixed(0)}% confidence
                      <br />
                      {item.reason}
                    </div>
                  ))
                ) : (
                  <div className="signal-text">No category prediction is available for this month.</div>
                )}
              </div>
            </div>
          ) : (
            <p className="panel-empty">{predictionError}</p>
          )}
        </div>
      )}

      {pieCategories.length > 0 ? (
        <>
          <div className="analytics-grid">
            <div className="chart-card">
              <h2 className="chart-title">Spending by category</h2>
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie
                    data={pieCategories}
                    dataKey="amount"
                    nameKey="category"
                    cx="50%"
                    cy="46%"
                    outerRadius={90}
                    labelLine={false}
                    label={({ category, percent }) =>
                      percent && percent > 0.08 ? `${category}` : ''
                    }
                  >
                    {pieCategories.map((_, i) => (
                      <Cell key={i} fill={COLORS[i % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(v: number) => `$${v.toFixed(2)}`} />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </div>

            <div className="chart-card">
              <h2 className="chart-title">Daily spend trend</h2>
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={dailySpend}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#E2EBE5" />
                  <XAxis dataKey="date" tick={{ fill: '#5A7566', fontSize: 12 }} />
                  <YAxis tick={{ fill: '#5A7566', fontSize: 12 }} />
                  <Tooltip formatter={(v: number) => `$${v.toFixed(2)}`} />
                  <Line type="monotone" dataKey="amount" stroke="#2D6A4F" strokeWidth={3} dot={{ r: 3 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="analytics-detail-grid">
            <div className="analytics-panel">
              <h2 className="chart-title">Top merchants</h2>
              {topMerchants.length > 0 ? (
                <div className="analytics-list">
                  {topMerchants.map((merchant) => (
                    <div className="analytics-list-item" key={merchant.merchant}>
                      <div>
                        <div className="analytics-list-title">{merchant.merchant}</div>
                        <div className="analytics-list-meta">{merchant.count} transactions</div>
                      </div>
                      <div className="analytics-list-stat">${merchant.amount.toFixed(2)}</div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="panel-empty">No merchant data for this month.</p>
              )}
            </div>

            <div className="analytics-panel">
              <h2 className="chart-title">Largest expenses</h2>
              {largestExpenses.length > 0 ? (
                <div className="analytics-list">
                  {largestExpenses.map((txn) => (
                    <div className="analytics-list-item" key={txn.transactionId}>
                      <div>
                        <div className="analytics-list-title">{txn.merchant}</div>
                        <div className="analytics-list-meta">{txn.date} · {formatCategoryLabel(txn.category)}</div>
                      </div>
                      <div className="analytics-list-stat">${txn.spend.toFixed(2)}</div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="panel-empty">No expenses captured for this month.</p>
              )}
            </div>
          </div>
        </>
      ) : (
        <div className="empty-state">
          <p>No spending found for {resolvedMonth}.</p>
          <a href="/upload" className="btn-primary" style={{ display: 'inline-block', marginTop: '12px' }}>Upload a statement</a>
        </div>
      )}
    </div>
  )
}
