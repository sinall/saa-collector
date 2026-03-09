import axios from 'axios'
import { ElMessage } from 'element-plus'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  }
})

api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Token ${token}`
    }
    
    if (['post', 'put', 'patch', 'delete'].includes(config.method?.toLowerCase() || '')) {
      const csrfToken = getCsrfToken()
      if (csrfToken) {
        config.headers['X-CSRFToken'] = csrfToken
      }
    }
    
    if (import.meta.env.DEV && import.meta.env.VITE_DEV_TOKEN) {
      config.headers['X-Dev-Token'] = import.meta.env.VITE_DEV_TOKEN
    }
    
    return config
  },
  (error) => Promise.reject(error)
)

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/login'
    }
    const message = error.response?.data?.error || error.response?.data?.message || error.message || '请求失败'
    ElMessage.error(message)
    return Promise.reject(error)
  }
)

function getCsrfToken(): string | null {
  const name = 'csrftoken'
  const value = `; ${document.cookie}`
  const parts = value.split(`; ${name}=`)
  if (parts.length === 2) return parts.pop()?.split(';').shift() || null
  return null
}

export interface ApiResponse<T> {
  success: boolean
  data?: T
  error?: string
  message?: string
}

export interface DataStatus {
  data_type: string
  data_type_display: string
  count: number
  earliest_date: string | null
  latest_date: string | null
  loading?: boolean
  error?: boolean
}

export interface CollectJob {
  id: number
  data_type: string
  data_type_display: string
  symbols: string[]
  params: Record<string, any>
  status: string
  status_display: string
  start_time: string | null
  end_time: string | null
  message: string | null
  created_at: string
}

export interface Stock {
  symbol: string
  name: string
  industry: string | null
  list_date: string | null
}

export const fetchDataStatus = async (): Promise<ApiResponse<DataStatus[]>> => {
  const response = await api.get('/data-status/')
  return response.data
}

export const fetchCollectJobs = async (params?: {
  status?: string
  data_type?: string
  page?: number
  page_size?: number
}): Promise<ApiResponse<{ results: CollectJob[], pagination: any }>> => {
  const response = await api.get('/collect/jobs/', { params })
  return response.data
}

export const fetchCollectJobDetail = async (id: number): Promise<ApiResponse<CollectJob>> => {
  const response = await api.get(`/collect/jobs/${id}/`)
  return response.data
}

export const collectStockInfo = async (symbols?: string[]): Promise<ApiResponse<CollectJob>> => {
  const response = await api.post('/collect/stock-info/', { symbols })
  return response.data
}

export const collectQuotes = async (symbols?: string[]): Promise<ApiResponse<CollectJob>> => {
  const response = await api.post('/collect/quotes/', { symbols })
  return response.data
}

export const collectHistoricalQuotes = async (params: {
  symbols?: string[]
  start_date?: string
  end_date?: string
}): Promise<ApiResponse<CollectJob>> => {
  const response = await api.post('/collect/historical-quotes/', params)
  return response.data
}

export const collectStatements = async (params: {
  symbols?: string[]
  start_date?: string
  report_types?: string[]
}): Promise<ApiResponse<CollectJob>> => {
  const response = await api.post('/collect/statements/', params)
  return response.data
}

export const collectCapital = async (params: {
  symbols?: string[]
  start_date?: string
}): Promise<ApiResponse<CollectJob>> => {
  const response = await api.post('/collect/capital/', params)
  return response.data
}

export const collectValuation = async (symbols?: string[]): Promise<ApiResponse<CollectJob>> => {
  const response = await api.post('/collect/valuation/', { symbols })
  return response.data
}

export const collectMainBusiness = async (params: {
  symbols?: string[]
  start_date?: string
}): Promise<ApiResponse<CollectJob>> => {
  const response = await api.post('/collect/main-business/', params)
  return response.data
}

export const fetchStocks = async (params?: {
  keyword?: string
  page?: number
  page_size?: number
}): Promise<ApiResponse<{ results: Stock[], pagination: any }>> => {
  const response = await api.get('/stocks/', { params })
  return response.data
}

export const fetchStockDetail = async (symbol: string): Promise<ApiResponse<Stock>> => {
  const response = await api.get(`/stocks/${symbol}/`)
  return response.data
}

export default api
