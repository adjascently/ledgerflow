import axios from 'axios'
import { fetchAuthSession } from 'aws-amplify/auth'

const BASE = import.meta.env.VITE_API_BASE_URL

// Attach Cognito JWT to every request automatically
const api = axios.create({ baseURL: BASE })

api.interceptors.request.use(async (config) => {
  try {
    const session = await fetchAuthSession()
    const token = session.tokens?.idToken?.toString()
    if (token) config.headers.Authorization = `Bearer ${token}`
  } catch {
    // unauthenticated — let the request go through (public endpoints)
  }
  return config
})

// ── User ──────────────────────────────────────────────────────────────────────

export async function createUser(userId: string, email: string, currencyPreference = 'USD') {
  const { data } = await api.post('/user', { userId, email, currencyPreference })
  return data
}

export async function getUserProfile(userId: string) {
  const { data } = await api.get(`/user/${userId}`)
  return data as {
    user: {
      userId: string
      email: string
      currencyPreference: string
      spendingThreshold?: number
    }
  }
}

export async function updateSpendingThreshold(userId: string, spendingThreshold: number) {
  const { data } = await api.put(`/user/${userId}`, { spendingThreshold })
  return data as {
    message: string
    user: {
      userId: string
      email: string
      currencyPreference: string
      spendingThreshold?: number
    }
  }
}

// ── Upload ────────────────────────────────────────────────────────────────────

export async function getUploadUrl(userId: string, fileName: string, contentType: string) {
  const { data } = await api.post('/statement/upload', { userId, fileName, contentType })
  return data as { uploadId: string; s3Key: string; uploadUrl: string; expiresIn: number }
}

export async function uploadFileToS3(uploadUrl: string, file: File) {
  // PUT directly to S3 — no auth header, just content-type
  await axios.put(uploadUrl, file, {
    headers: { 'Content-Type': file.type },
  })
}

// ── Transactions ──────────────────────────────────────────────────────────────

export async function getTransactions(userId: string, startDate?: string, endDate?: string, uploadId?: string) {
  const params: Record<string, string> = {}
  if (startDate) params.startDate = startDate
  if (endDate) params.endDate = endDate
  if (uploadId) params.uploadId = uploadId
  const { data } = await api.get(`/transactions/${userId}`, { params })
  return data as { transactions: Transaction[]; count: number }
}

export async function saveTransactions(userId: string, transactions: Transaction[]) {
  const { data } = await api.post('/transactions', { userId, transactions })
  return data
}

// ── Analytics ─────────────────────────────────────────────────────────────────

export async function getMonthlySummary(userId: string, month: string, uploadId?: string) {
  const params: Record<string, string> = { month }
  if (uploadId) params.uploadId = uploadId
  const { data } = await api.get(`/summary/monthly/${userId}`, { params })
  return data as MonthlySummary
}

export async function getCategorySpending(userId: string, month: string, uploadId?: string) {
  const params: Record<string, string> = { month }
  if (uploadId) params.uploadId = uploadId
  const { data } = await api.get(`/analytics/category/${userId}`, { params })
  return data as { userId: string; month: string; categories: CategoryAmount[] }
}

export async function getMlPredictions(userId: string, month: string, months = 6) {
  const { data } = await api.get(`/ml/predictions/${userId}`, {
    params: { month, months: String(months) },
  })
  return data as MlPredictionsResponse
}

// ── Types ─────────────────────────────────────────────────────────────────────

export interface Transaction {
  transactionId: string
  date: string
  merchant: string
  amount: number
  category: string
  paymentMethod: string
  uploadId?: string
}

export interface MonthlySummary {
  userId: string
  month: string
  transactionCount: number
  totalSpent: number
  topCategory: string | null
  categories: Record<string, number>
}

export interface CategoryAmount {
  category: string
  amount: number
}

export interface PredictedCategory {
  category: string
  confidence: number
  reason: string
}

export interface AnomalyRisk {
  level: 'low' | 'medium' | 'high' | string
  score: number
  reason: string
}

export interface PredictionResult {
  source: string
  modelName: string
  forecastAmount: number
  forecastConfidence: string
  predictedTopCategories: PredictedCategory[]
  anomalyRisk: AnomalyRisk
}

export interface MlPredictionsResponse {
  userId: string
  focusMonth: string
  prediction: PredictionResult | null
  recommendedActions: string[]
  predictionStore: {
    status: string
    database?: string
    message?: string
  }
}
