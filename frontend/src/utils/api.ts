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
  frequency: string | null
  completeness: number | null
  show_completeness?: boolean
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
}): Promise<ApiResponse<{ results: CollectJob[], pagination: { total: number } }>> => {
  const response = await api.get('/collect/jobs/', { params })
  return {
    success: true,
    data: {
      results: response.data.results || [],
      pagination: { total: response.data.count || 0 }
    }
  }
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

export interface MissingDataRecord {
  symbol: string
  name: string
  date: string
  data_type: string
  frequency: string
}

export interface SummaryItem {
  period: string
  expected: number
  missing: number
}

export const checkDataCompleteness = async (params: {
  data_type: string
  symbols?: string[]
  start_date?: string
  end_date?: string
  frequency?: string
  page?: number
  page_size?: number
}): Promise<ApiResponse<{
  total_missing: number
  missing_records: MissingDataRecord[]
  summary: SummaryItem[]
  pagination: {
    page: number
    page_size: number
    total: number
    total_pages: number
  }
}>> => {
  const response = await api.post('/data-completeness/check/', params)
  return response.data
}

export interface HeatmapDataType {
  key: string
  label: string
  frequency?: 'daily' | 'quarterly' | 'yearly' | null
}

export interface HeatmapResponse {
  date_range: {
    start: string
    end: string
  }
  frequency: string
  periods: string[]
  data_types: HeatmapDataType[]
  matrix: Record<string, number[]>
}

function generateMockHeatmapData(frequency: string): HeatmapResponse {
  const dataTypes: HeatmapDataType[] = [
    { key: 'trade_days', label: '交易日', frequency: 'daily' },
    { key: 'stock_info', label: '股票基本信息', frequency: null },
    { key: 'quote', label: '最新行情', frequency: null },
    { key: 'historical_quote', label: '历史行情', frequency: 'daily' },
    { key: 'balance_sheet', label: '资产负债表', frequency: 'quarterly' },
    { key: 'income', label: '利润表', frequency: 'quarterly' },
    { key: 'cash_flow', label: '现金流量表', frequency: 'quarterly' },
    { key: 'main_business', label: '主营业务', frequency: 'quarterly' },
    { key: 'capital', label: '股本变动', frequency: 'yearly' },
    { key: 'dividend', label: '分红数据', frequency: 'yearly' },
    { key: 'valuation_board', label: '板块估值', frequency: 'daily' },
    { key: 'valuation_industry', label: '行业估值', frequency: 'daily' },
  ]

  let periods: string[] = []
  const now = new Date()
  const startDate = new Date('2009-01-01')

  if (frequency === 'daily') {
    for (let d = new Date(startDate); d <= now; d.setDate(d.getDate() + 1)) {
      const dateStr = d.toISOString().split('T')[0]
      if (dateStr) periods.push(dateStr)
    }
  } else if (frequency === 'monthly') {
    for (let y = 2009; y <= now.getFullYear(); y++) {
      for (let m = 1; m <= 12; m++) {
        if (y === now.getFullYear() && m > now.getMonth() + 1) break
        periods.push(`${y}-${String(m).padStart(2, '0')}`)
      }
    }
  } else if (frequency === 'quarterly') {
    for (let y = 2009; y <= now.getFullYear(); y++) {
      for (let q = 1; q <= 4; q++) {
        if (y === now.getFullYear() && q > Math.ceil((now.getMonth() + 1) / 3)) break
        periods.push(`${y}-Q${q}`)
      }
    }
  } else {
    for (let y = 2009; y <= now.getFullYear(); y++) {
      periods.push(`${y}`)
    }
  }

  const matrix: Record<string, number[]> = {}
  dataTypes.forEach(dt => {
    const dtFreq = dt.frequency
    if (dtFreq === null) {
      const value = dt.key === 'stock_info' ? 1.0 : Math.round((0.6 + Math.random() * 0.4) * 100) / 100
      matrix[dt.key] = Array(periods.length).fill(value)
    } else if (frequency === 'monthly' && dtFreq === 'quarterly') {
      const values: number[] = []
      for (let i = 0; i < periods.length; i += 3) {
        const value = Math.round((0.6 + Math.random() * 0.4) * 100) / 100
        values.push(value, value, value)
      }
      matrix[dt.key] = values.slice(0, periods.length)
    } else if (frequency === 'monthly' && dtFreq === 'yearly') {
      const values: number[] = []
      for (let i = 0; i < periods.length; i += 12) {
        const value = Math.round((0.6 + Math.random() * 0.4) * 100) / 100
        for (let j = 0; j < 12 && values.length < periods.length; j++) {
          values.push(value)
        }
      }
      matrix[dt.key] = values
    } else if (frequency === 'quarterly' && dtFreq === 'yearly') {
      const values: number[] = []
      for (let i = 0; i < periods.length; i += 4) {
        const value = Math.round((0.6 + Math.random() * 0.4) * 100) / 100
        for (let j = 0; j < 4 && values.length < periods.length; j++) {
          values.push(value)
        }
      }
      matrix[dt.key] = values
    } else {
      matrix[dt.key] = periods.map(() => {
        const base = 0.6 + Math.random() * 0.4
        return Math.round(base * 100) / 100
      })
    }
  })

  const endDateStr = now.toISOString().split('T')[0] ?? ''
  return {
    date_range: { start: '2009-01-01', end: endDateStr },
    frequency,
    periods,
    data_types: dataTypes,
    matrix,
  }
}

export const fetchCompletenessHeatmap = async (frequency: string = 'monthly'): Promise<ApiResponse<HeatmapResponse>> => {
  const response = await api.get('/data-completeness/heatmap/', { params: { frequency } })
  return response.data
}

export interface StockDetail {
  symbol: string
  name: string
  industry: string | null
  list_date: string | null
}

export interface StockHistoricalQuote {
  trade_date: string
  open: number | null
  high: number | null
  low: number | null
  close: number | null
  volume: number | null
  amount: number | null
}

export interface StockBalanceSheet {
  report_period: string
  report_date: string
  total_assets: number | null
  total_liabilities: number | null
  total_equity: number | null
}

function generateMockStockDetail(symbol: string): StockDetail {
  const industries = ['银行', '房地产', '科技', '医药', '消费']
  return {
    symbol,
    name: `${symbol}公司`,
    industry: industries[Math.floor(Math.random() * industries.length)] ?? null,
    list_date: '2020-01-01',
  }
}

function generateMockHistoricalQuotes(_symbol: string): StockHistoricalQuote[] {
  const quotes: StockHistoricalQuote[] = []
  const basePrice = 10 + Math.random() * 90
  for (let i = 0; i < 100; i++) {
    const date = new Date()
    date.setDate(date.getDate() - i)
    const change = (Math.random() - 0.5) * 0.1
    const price = basePrice * (1 + change)
    quotes.push({
      trade_date: date.toISOString().split('T')[0] ?? '',
      open: Math.round(price * 100) / 100,
      high: Math.round(price * 1.02 * 100) / 100,
      low: Math.round(price * 0.98 * 100) / 100,
      close: Math.round(price * 100) / 100,
      volume: Math.floor(Math.random() * 10000000),
      amount: Math.floor(Math.random() * 100000000),
    })
  }
  return quotes
}

function generateMockBalanceSheets(_symbol: string): StockBalanceSheet[] {
  const sheets: StockBalanceSheet[] = []
  for (let y = 2020; y <= 2025; y++) {
    for (let q = 1; q <= 4; q++) {
      if (y === 2025 && q > 1) break
      sheets.push({
        report_period: `${y}-Q${q}`,
        report_date: `${y}-${String(q * 3).padStart(2, '0')}-31`,
        total_assets: Math.floor(1000000000 + Math.random() * 10000000000),
        total_liabilities: Math.floor(500000000 + Math.random() * 5000000000),
        total_equity: Math.floor(500000000 + Math.random() * 5000000000),
      })
    }
  }
  return sheets
}

export const fetchStockDetailMock = async (symbol: string): Promise<ApiResponse<StockDetail>> => {
  return { success: true, data: generateMockStockDetail(symbol) }
}

export const fetchStockHistoricalQuotesMock = async (symbol: string): Promise<ApiResponse<StockHistoricalQuote[]>> => {
  return { success: true, data: generateMockHistoricalQuotes(symbol) }
}

export const fetchStockBalanceSheetsMock = async (symbol: string): Promise<ApiResponse<StockBalanceSheet[]>> => {
  return { success: true, data: generateMockBalanceSheets(symbol) }
}

export interface TypeBrowseRow {
  [key: string]: string | number | null
}

function generateMockTypeBrowseData(dataType: string): TypeBrowseRow[] {
  const rows: TypeBrowseRow[] = []
  const count = 100
  const stocks = [
    { code: '000001', name: '平安银行' },
    { code: '000002', name: '万科A' },
    { code: '000003', name: '国农科技' },
    { code: '600000', name: '浦发银行' },
    { code: '600001', name: '邯郸钢铁' },
  ]

  if (dataType === 'info') {
    for (let i = 0; i < count; i++) {
      const stock = stocks[Math.floor(Math.random() * stocks.length)]!
      rows.push({
        symbol: stock.code,
        name: stock.name,
        exchange: stock.code.startsWith('6') ? 'SH' : 'SZ',
        industry_classification_id: ['银行', '房地产', '科技', '医药', '消费'][Math.floor(Math.random() * 5)] ?? '',
        listing_time: new Date(Date.now() - Math.random() * 10 * 365 * 24 * 3600000).toISOString().split('T')[0] ?? '',
        company_name: `${stock.name}股份有限公司`,
        legal_representative: '张三',
        registered_capital: 1000000000,
        website: 'https://example.com',
      })
    }
  } else if (dataType === 'quote') {
    for (let i = 0; i < count; i++) {
      const stock = stocks[Math.floor(Math.random() * stocks.length)]!
      const price = 10 + Math.random() * 90
      rows.push({
        symbol: stock.code,
        stock_name: stock.name,
        date: new Date(Date.now() - Math.random() * 7 * 24 * 3600000).toISOString().split('T')[0] ?? '',
        price: Math.round(price * 100) / 100,
      })
    }
  } else if (dataType === 'historical_quote') {
    for (let i = 0; i < count; i++) {
      const stock = stocks[Math.floor(Math.random() * stocks.length)]!
      const basePrice = 10 + Math.random() * 90
      rows.push({
        symbol: stock.code,
        stock_name: stock.name,
        date: new Date(Date.now() - Math.random() * 365 * 24 * 3600000).toISOString().split('T')[0] ?? '',
        price: Math.round(basePrice * 100) / 100,
      })
    }
  } else if (dataType === 'balance_sheet') {
    for (let i = 0; i < count; i++) {
      const stock = stocks[Math.floor(Math.random() * stocks.length)]!
      rows.push({
        symbol: stock.code,
        stock_name: stock.name,
        date: '2024-12-31',
        total_assets: Math.floor(1000000000 + Math.random() * 10000000000),
        total_current_assets: Math.floor(500000000 + Math.random() * 5000000000),
        total_liabilities: Math.floor(500000000 + Math.random() * 5000000000),
        total_current_liabilities: Math.floor(300000000 + Math.random() * 3000000000),
        total_shareholders_equity: Math.floor(500000000 + Math.random() * 5000000000),
        monetary_funds: Math.floor(100000000 + Math.random() * 1000000000),
        accounts_receivable: Math.floor(50000000 + Math.random() * 500000000),
        inventories: Math.floor(30000000 + Math.random() * 300000000),
        fixed_assets: Math.floor(200000000 + Math.random() * 2000000000),
        short_term_borrowings: Math.floor(100000000 + Math.random() * 1000000000),
        long_term_borrowings: Math.floor(50000000 + Math.random() * 500000000),
      })
    }
  } else if (dataType === 'income') {
    for (let i = 0; i < count; i++) {
      const stock = stocks[Math.floor(Math.random() * stocks.length)]!
      rows.push({
        symbol: stock.code,
        stock_name: stock.name,
        date: '2024-12-31',
        operating_revenue: Math.floor(1000000000 + Math.random() * 10000000000),
        operating_cost: Math.floor(500000000 + Math.random() * 5000000000),
        business_profit: Math.floor(100000000 + Math.random() * 1000000000),
        net_profit: Math.floor(100000000 + Math.random() * 2000000000),
        controlling_net_profit: Math.floor(80000000 + Math.random() * 1800000000),
        basic_earnings_per_share: Math.round((Math.random() * 2 + 0.1) * 100) / 100,
        selling_expenses: Math.floor(10000000 + Math.random() * 100000000),
        administrative_expenses: Math.floor(5000000 + Math.random() * 50000000),
        financial_expenses: Math.floor(3000000 + Math.random() * 30000000),
      })
    }
  } else if (dataType === 'cash_flow') {
    for (let i = 0; i < count; i++) {
      const stock = stocks[Math.floor(Math.random() * stocks.length)]!
      rows.push({
        symbol: stock.code,
        stock_name: stock.name,
        date: '2024-12-31',
        net_cash_flows_from_operating_activities: Math.floor(500000000 + Math.random() * 5000000000),
        net_cash_flows_from_investing_activities: Math.floor(-Math.random() * 3000000000),
        net_cash_flows_from_financing_activities: Math.floor(-Math.random() * 2000000000),
      })
    }
  } else if (dataType === 'main_business') {
    for (let i = 0; i < count; i++) {
      const stock = stocks[Math.floor(Math.random() * stocks.length)]!
      rows.push({
        symbol: stock.code,
        stock_name: stock.name,
        date: '2024-12-31',
        category: ['PRODUCT', 'REGION'][Math.floor(Math.random() * 2)] ?? '',
        item_name: ['银行业务', '房地产开发', '技术服务', '医药制造', '消费品'][Math.floor(Math.random() * 5)] ?? '',
        main_business_income: Math.floor(100000000 + Math.random() * 5000000000),
        main_business_cost: Math.floor(50000000 + Math.random() * 3000000000),
        main_business_profit: Math.floor(30000000 + Math.random() * 2000000000),
        gross_profit_margin: Math.round((Math.random() * 0.3 + 0.1) * 100) / 100,
      })
    }
  } else if (dataType === 'capital') {
    for (let i = 0; i < count; i++) {
      const stock = stocks[Math.floor(Math.random() * stocks.length)]!
      rows.push({
        symbol: stock.code,
        stock_name: stock.name,
        date: new Date(Date.now() - Math.random() * 365 * 24 * 3600000).toISOString().split('T')[0] ?? '',
        capital: Math.floor(1000000000 + Math.random() * 10000000000),
      })
    }
  } else if (dataType === 'dividend') {
    for (let i = 0; i < count; i++) {
      const stock = stocks[Math.floor(Math.random() * stocks.length)]!
      rows.push({
        symbol: stock.code,
        stock_name: stock.name,
        date: new Date(Date.now() - Math.random() * 365 * 24 * 3600000).toISOString().split('T')[0] ?? '',
        dps: Math.round((Math.random() * 2) * 100) / 100,
        dividend: Math.floor(100000000 + Math.random() * 1000000000),
      })
    }
  } else if (dataType === 'trade_days') {
    for (let i = 0; i < count; i++) {
      rows.push({
        date: new Date(Date.now() - i * 24 * 3600000).toISOString().split('T')[0] ?? '',
        is_open: Math.random() > 0.3 ? 1 : 0,
      })
    }
  }

  return rows
}

export const fetchTypeBrowseDataMock = async (
  dataType: string,
  page: number = 1,
  pageSize: number = 50
): Promise<ApiResponse<{ results: TypeBrowseRow[], total: number }>> => {
  const allData = generateMockTypeBrowseData(dataType)
  const start = (page - 1) * pageSize
  const results = allData.slice(start, start + pageSize)
  return {
    success: true,
    data: {
      results,
      total: allData.length,
    },
  }
}

export const fetchTypeBrowseData = async (
  tableName: string,
  page: number = 1,
  pageSize: number = 50,
  startDate?: string,
  endDate?: string
): Promise<ApiResponse<{ results: Record<string, unknown>[], total: number }>> => {
  const params: Record<string, unknown> = { page, page_size: pageSize }
  if (startDate) params.start_date = startDate
  if (endDate) params.end_date = endDate
  const response = await api.get(`/type-browse-data/${tableName}/`, { params })
  return response.data
}

function generateMockStocks(keyword?: string): { results: Stock[], pagination: { total: number } } {
  const allStocks: Stock[] = []
  const prefixes = ['000', '001', '002', '600', '601', '603']
  const names = ['平安银行', '万科A', '国农科技', '浦发银行', '邯郸钢铁', 'ST嘉陵']

  for (let i = 0; i < 500; i++) {
    const prefix = prefixes[i % prefixes.length] ?? '000'
    const suffix = String(i).padStart(3, '0')
    allStocks.push({
      symbol: `${prefix}${suffix}`,
      name: `${names[i % names.length]}${i}`,
      industry: ['银行', '房地产', '科技', '医药', '消费'][i % 5] ?? null,
      list_date: '2020-01-01',
    })
  }

  let filtered = allStocks
  if (keyword) {
    const lowerKeyword = keyword.toLowerCase()
    filtered = allStocks.filter(s => 
      s.symbol.toLowerCase().includes(lowerKeyword) || 
      s.name.toLowerCase().includes(lowerKeyword)
    )
  }

  return {
    results: filtered,
    pagination: { total: filtered.length },
  }
}

export const fetchStocksMock = async (params?: {
  keyword?: string
  page?: number
  page_size?: number
}): Promise<ApiResponse<{ results: Stock[], pagination: { total: number } }>> => {
  const { results, pagination } = generateMockStocks(params?.keyword)
  const page = params?.page ?? 1
  const pageSize = params?.page_size ?? 20
  const start = (page - 1) * pageSize
  const pagedResults = results.slice(start, start + pageSize)

  return {
    success: true,
    data: {
      results: pagedResults,
      pagination,
    },
  }
}

export interface CollectPlan {
  id: number
  name: string
  status: 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED'
  status_display: string
  execution_mode_display: string
  source_report_name?: string
  created_at: string
  started_at?: string
  completed_at?: string
  jobs: {
    data_type_display: string
    symbols: string[]
    params: {
      start_date?: string
      end_date?: string
    }
    status: string
    status_display: string
    start_time?: string
    end_time?: string
    message?: string
  }[]
}

export interface CollectSchedule {
  id: number
  name: string
  data_type: string
  data_type_display: string
  cron_expression: string
  symbols: string[]
  params: {
    date_start: string
    date_end: string
  }
  enabled: boolean
  created_at: string
  updated_at: string
  plans: {
    id: number
    name: string
    status: 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED'
    status_display: string
    total_jobs: number
    success_jobs: number
    created_at: string
  }[]
}

function generateMockCollectSchedules(): CollectSchedule[] {
  const schedules: CollectSchedule[] = []
  const dataTypes = ['quote', 'historical_quote', 'balance_sheet', 'income', 'cash_flow']
  const dataTypeDisplays = ['行情数据', '历史行情', '资产负债表', '利润表', '现金流量表']
  const frequencies = ['daily', 'weekly', 'monthly', 'quarterly', 'yearly']
  const stockCodes = ['000001', '000002', '600000', '600001', '600036']
  const statuses: Array<'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED'> = ['PENDING', 'RUNNING', 'COMPLETED', 'FAILED']
  const statusDisplays = ['待执行', '执行中', '已完成', '执行失败']

  for (let i = 1; i <= 8; i++) {
    const date = new Date()
    date.setDate(date.getDate() - (i - 1) * 3)

    const frequencyIndex = Math.floor(Math.random() * frequencies.length)
    const dataTypeIndex = Math.floor(Math.random() * dataTypes.length)
    const frequency = frequencies[frequencyIndex] ?? 'daily'

    const plans = []
    for (let j = 0; j < 3; j++) {
      const planDate = new Date(date)
      planDate.setDate(planDate.getDate() - j * 7)
      const statusIdx = Math.floor(Math.random() * 4)
      plans.push({
        id: i * 100 + j,
        name: `定时触发-${dataTypes[dataTypeIndex] ?? 'quote'}-${planDate.toISOString().split('T')[0] ?? ''}`,
        status: statuses[statusIdx] ?? 'PENDING',
        status_display: statusDisplays[statusIdx] ?? '待执行',
        total_jobs: Math.floor(Math.random() * 5) + 1,
        success_jobs: statusIdx === 2 ? Math.floor(Math.random() * 5) + 1 : Math.floor(Math.random() * 3),
        created_at: planDate.toISOString(),
      })
    }

    schedules.push({
      id: i,
      name: `${dataTypeDisplays[dataTypeIndex] ?? '行情数据'} 采集日程 - ${frequency}度`,
      data_type: dataTypes[dataTypeIndex] ?? 'quote',
      data_type_display: dataTypeDisplays[dataTypeIndex] ?? '行情数据',
      symbols: i % 2 === 0 ? [] : stockCodes.slice(0, 3 + Math.floor(Math.random() * 3)),
      cron_expression: frequency === 'daily' ? '0 0 * * *' : frequency === 'weekly' ? '0 0 * * 1' : frequency === 'monthly' ? '0 0 1 * *' : frequency === 'quarterly' ? '0 0 1 1 */3' : '0 0 1 1 *',
      params: {
        date_start: '2009-01-01',
        date_end: date.toISOString().split('T')[0] ?? '',
      },
      enabled: Math.random() > 0.5,
      created_at: date.toISOString(),
      updated_at: new Date().toISOString(),
      plans,
    })
  }

  return schedules
}

function generateMockCollectPlans(): CollectPlan[] {
  const plans: CollectPlan[] = []
  const dataTypes = ['quote', 'historical_quote', 'balance_sheet', 'income', 'cash_flow']
  const dataTypeDisplays = ['行情数据', '历史行情', '资产负债表', '利润表', '现金流量表']
  const stockCodes = ['000001', '000002', '600000', '600001', '600036']
  const statuses: Array<'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED'> = ['PENDING', 'RUNNING', 'COMPLETED', 'FAILED']
  const statusDisplays = ['待执行', '执行中', '已完成', '执行失败']

  for (let i = 1; i <= 8; i++) {
    const date = new Date()
    date.setDate(date.getDate() - (i - 1) * 5)
    const statusIndex = Math.min(i - 1, 3)
    const status = statuses[statusIndex] ?? 'PENDING'

    plans.push({
      id: i,
      name: `采集计划 ${i}`,
      status,
      status_display: statusDisplays[statusIndex] ?? '待执行',
      execution_mode_display: '手动执行',
      source_report_name: i > 2 ? `完整性检查报告 #${i - 2}` : undefined,
      created_at: date.toISOString(),
      started_at: status !== 'PENDING' ? new Date(date.getTime() + 60000).toISOString() : undefined,
      completed_at: status === 'COMPLETED' || status === 'FAILED' ? new Date(date.getTime() + 3600000).toISOString() : undefined,
      jobs: [
        {
          data_type_display: dataTypeDisplays[i % dataTypeDisplays.length] ?? '行情数据',
          symbols: stockCodes.slice(0, 3 + Math.floor(Math.random() * 3)),
          params: {
            start_date: '2009-01-01',
            end_date: date.toISOString().split('T')[0] ?? '',
          },
          status: status === 'PENDING' ? 'PENDING' : status === 'RUNNING' ? 'RUNNING' : 'SUCCESS',
          status_display: status === 'PENDING' ? '待执行' : status === 'RUNNING' ? '执行中' : '执行成功',
          start_time: status !== 'PENDING' ? new Date(date.getTime() + 60000).toISOString() : undefined,
          end_time: status === 'COMPLETED' ? new Date(date.getTime() + 1800000).toISOString() : undefined,
          message: status === 'COMPLETED' ? '成功采集 100 条数据' : status === 'FAILED' ? '网络错误' : undefined,
        },
      ],
    })
  }

  return plans
}

export const fetchCollectScheduleMock = async (id: number): Promise<ApiResponse<CollectSchedule>> => {
  await new Promise(resolve => setTimeout(resolve, 300))

  const schedule = generateMockCollectSchedules().find(s => s.id === id)
  if (!schedule) {
    return {
      success: false,
      error: '采集日程不存在',
    }
  }

  return {
    success: true,
    data: schedule,
  }
}

export const fetchCollectPlanMock = async (id: number): Promise<ApiResponse<CollectPlan>> => {
  await new Promise(resolve => setTimeout(resolve, 300))

  let plan = generateMockCollectPlans().find(p => p.id === id)

  if (!plan) {
    const statuses: Array<'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED'> = ['PENDING', 'RUNNING', 'COMPLETED', 'FAILED']
    const statusDisplays = ['待执行', '执行中', '已完成', '执行失败']
    const dataTypeDisplays = ['行情数据', '历史行情', '资产负债表', '利润表', '现金流量表']
    const stockCodes = ['000001', '000002', '600000', '600001', '600036']
    const statusIdx = id % 4
    const status = statuses[statusIdx] ?? 'PENDING'
    const date = new Date()
    date.setDate(date.getDate() - Math.floor(id / 100) * 7)

    plan = {
      id,
      name: `定时触发-计划 #${id}`,
      status,
      status_display: statusDisplays[statusIdx] ?? '待执行',
      execution_mode_display: '并行执行',
      created_at: date.toISOString(),
      started_at: status !== 'PENDING' ? new Date(date.getTime() + 60000).toISOString() : undefined,
      completed_at: status === 'COMPLETED' || status === 'FAILED' ? new Date(date.getTime() + 3600000).toISOString() : undefined,
      jobs: [
        {
          data_type_display: dataTypeDisplays[id % dataTypeDisplays.length] ?? '行情数据',
          symbols: stockCodes.slice(0, 3 + (id % 3)),
          params: {
            start_date: '2009-01-01',
            end_date: date.toISOString().split('T')[0] ?? '',
          },
          status: status === 'PENDING' ? 'PENDING' : status === 'RUNNING' ? 'RUNNING' : 'SUCCESS',
          status_display: status === 'PENDING' ? '待执行' : status === 'RUNNING' ? '执行中' : '执行成功',
          start_time: status !== 'PENDING' ? new Date(date.getTime() + 60000).toISOString() : undefined,
          end_time: status === 'COMPLETED' ? new Date(date.getTime() + 1800000).toISOString() : undefined,
          message: status === 'COMPLETED' ? '成功采集 100 条数据' : status === 'FAILED' ? '网络错误' : undefined,
        },
      ],
    }
  }

  return {
    success: true,
    data: plan,
  }
}

export interface IntegrityReport {
  id: number
  name: string
  status: 'GENERATING' | 'COMPLETED' | 'FAILED'
  status_display: string
  frequency: string
  frequency_display: string
  stock_scope: string
  data_types: string[]
  date_start: string
  date_end: string
  items_count: number
  selected_count: number
  created_at: string
  created_at_display: string
  completed_at?: string
}

export interface IntegrityReportItem {
  id: number
  report_id: number
  data_type: string
  stock_code: string
  period: string
  status: 'PENDING' | 'FIXED'
  status_display: string
  selected: boolean
}

export interface IntegrityReportCreateParams {
  name: string
  stock_scope: string
  stock_codes?: string[]
  data_types: string[]
  frequency: string
  date_start?: string
  date_end?: string
}

function generateMockIntegrityReports(): IntegrityReport[] {
  const reports: IntegrityReport[] = []
  const statuses: Array<'GENERATING' | 'COMPLETED' | 'FAILED'> = ['COMPLETED', 'COMPLETED', 'FAILED']
  const frequencies = ['daily', 'weekly', 'monthly', 'quarterly', 'yearly']
  const frequencyDisplays = ['日度', '周度', '月度', '季度', '年度']
  const dataTypeOptions = ['trade_days', 'stock_info', 'quote', 'historical_quote', 'balance_sheet', 'income', 'cash_flow', 'main_business', 'capital', 'dividend', 'valuation_board', 'valuation_industry']

  for (let i = 1; i <= 8; i++) {
    const statusIndex = Math.min(i - 1, 2)
    const status = statuses[statusIndex] ?? 'COMPLETED'
    const freqIndex = Math.floor(Math.random() * frequencies.length)
    const date = new Date()
    date.setDate(date.getDate() - (i - 1) * 2)

    const selectedTypes = dataTypeOptions.slice(0, 3 + Math.floor(Math.random() * 5))

    reports.push({
      id: i,
      name: `完整性检查报告 #${i}`,
      status,
      status_display: status === 'GENERATING' ? '生成中' : status === 'COMPLETED' ? '已完成' : '失败',
      frequency: frequencies[freqIndex] ?? 'monthly',
      frequency_display: frequencyDisplays[freqIndex] ?? '月度',
      stock_scope: 'ALL',
      data_types: selectedTypes,
      date_start: '2009-01-01',
      date_end: date.toISOString().split('T')[0] ?? '',
      items_count: status === 'COMPLETED' ? Math.floor(Math.random() * 500) + 50 : 0,
      selected_count: status === 'COMPLETED' ? Math.floor(Math.random() * 100) : 0,
      created_at: date.toISOString(),
      created_at_display: date.toLocaleString('zh-CN'),
      completed_at: status !== 'GENERATING' ? new Date(date.getTime() + 3600000).toISOString() : undefined,
    })
  }

  return reports
}

function generateMockIntegrityReportItems(
  reportId: number,
  page: number = 1,
  pageSize: number = 100,
  filters?: {
    status?: string
    data_type?: string
    stock_code?: string
    period?: string
  }
): { items: IntegrityReportItem[], total: number, selected_count: number } {
  const allItems: IntegrityReportItem[] = []
  const dataTypes = ['trade_days', 'stock_info', 'quote', 'historical_quote', 'balance_sheet', 'income', 'cash_flow', 'main_business', 'capital', 'dividend', 'valuation_board', 'valuation_industry']
  const stockCodes = ['000001', '000002', '000003', '000004', '000005', '600000', '600001', '600002', '600003', '600004', '600005']

  let itemId = 1
  const periods = ['2024-Q1', '2024-Q2', '2024-Q3', '2024-Q4', '2024-01', '2024-02', '2024-03', '2024-04', '2024-05', '2024-06']

  for (let i = 0; i < 250; i++) {
    const dataType = dataTypes[Math.floor(Math.random() * dataTypes.length)] ?? 'quote'
    const stockCode = stockCodes[Math.floor(Math.random() * stockCodes.length)] ?? '000001'
    const period = periods[Math.floor(Math.random() * periods.length)] ?? '2024-Q1'
    const status = Math.random() > 0.3 ? 'PENDING' : 'FIXED'

    allItems.push({
      id: itemId++,
      report_id: reportId,
      data_type: dataType,
      stock_code: stockCode,
      period,
      status,
      status_display: status === 'FIXED' ? '已修复' : '待修复',
      selected: status === 'PENDING' && Math.random() > 0.5,
    })
  }

  let filteredItems = allItems

  if (filters?.status) {
    filteredItems = filteredItems.filter(item => item.status === filters.status)
  }
  if (filters?.data_type) {
    filteredItems = filteredItems.filter(item => item.data_type === filters.data_type)
  }
  if (filters?.stock_code) {
    filteredItems = filteredItems.filter(item => item.stock_code.includes(filters.stock_code ?? ''))
  }
  if (filters?.period) {
    filteredItems = filteredItems.filter(item => item.period.includes(filters.period ?? ''))
  }

  const total = filteredItems.length
  const selectedCount = filteredItems.filter(item => item.selected).length

  const start = (page - 1) * pageSize
  const items = filteredItems.slice(start, start + pageSize)

  return { items, total, selected_count: selectedCount }
}

export const fetchIntegrityReports = async (): Promise<ApiResponse<IntegrityReport[]>> => {
  const response = await api.get('/integrity-reports/')
  return {
    success: true,
    data: response.data.results || [],
  }
}

export const createIntegrityReport = async (params: IntegrityReportCreateParams): Promise<ApiResponse<IntegrityReport>> => {
  const response = await api.post('/integrity-reports/', params)
  return response.data
}

export const fetchIntegrityReportDetail = async (
  id: number,
  params?: {
    page?: number
    page_size?: number
    status?: string
    data_type?: string
    stock_code?: string
    period?: string
  }
): Promise<ApiResponse<IntegrityReport & {
  items: IntegrityReportItem[]
  items_count: number
  selected_count: number
  pagination?: { page: number; page_size: number; total: number; total_pages: number }
}>> => {
  const response = await api.get(`/integrity-reports/${id}/`, { params })
  return response.data
}

export const selectItems = async (
  reportId: number,
  params: {
    data_types?: string[]
    stock_code?: string
    period?: string
    status?: string
    selected: boolean
  }
): Promise<ApiResponse<{ updated_count: number }>> => {
  const response = await api.post(`/integrity-reports/${reportId}/items/select-all/`, params)
  return response.data
}

export const generatePlan = async (reportId: number): Promise<ApiResponse<{ id: number }>> => {
  const response = await api.post(`/integrity-reports/${reportId}/generate-plan/`)
  return {
    success: true,
    data: { id: response.data.data.id },
  }
}

export const refreshReport = async (reportId: number): Promise<ApiResponse<any>> => {
  const response = await api.post(`/integrity-reports/${reportId}/refresh/`)
  return response.data
}

export const fetchIntegrityReportHeatmap = async (reportId: number): Promise<ApiResponse<IntegrityReportHeatmapData>> => {
  const response = await api.get(`/integrity-reports/${reportId}/heatmap/`)
  return response.data
}

export const fetchIntegrityReportsMock = async (): Promise<ApiResponse<IntegrityReport[]>> => {
  await new Promise(resolve => setTimeout(resolve, 300))
  const reports = generateMockIntegrityReports()
  return {
    success: true,
    data: reports,
  }
}

export const createIntegrityReportMock = async (params: IntegrityReportCreateParams): Promise<ApiResponse<IntegrityReport>> => {
  await new Promise(resolve => setTimeout(resolve, 500))

  const report: IntegrityReport = {
    id: Math.floor(Math.random() * 1000) + 100,
    name: params.name,
    status: 'GENERATING',
    status_display: '生成中',
    frequency: params.frequency,
    frequency_display: params.frequency === 'daily' ? '日度' : params.frequency === 'weekly' ? '周度' : params.frequency === 'monthly' ? '月度' : params.frequency === 'quarterly' ? '季度' : '年度',
    stock_scope: params.stock_scope,
    data_types: params.data_types,
    date_start: params.date_start ?? '2009-01-01',
    date_end: params.date_end ?? new Date().toISOString().split('T')[0] ?? '',
    items_count: 0,
    selected_count: 0,
    created_at: new Date().toISOString(),
    created_at_display: new Date().toLocaleString('zh-CN'),
  }

  return {
    success: true,
    data: report,
  }
}

export const fetchIntegrityReportDetailMock = async (
  id: number,
  params?: {
    page?: number
    page_size?: number
    status?: string
    data_type?: string
    stock_code?: string
    period?: string
  }
): Promise<ApiResponse<{
  report: IntegrityReport
  items: IntegrityReportItem[]
  items_count: number
  selected_count: number
}>> => {
  await new Promise(resolve => setTimeout(resolve, 200))

  const reports = generateMockIntegrityReports()
  const report = reports.find(r => r.id === id) ?? reports[0]

  if (!report) {
    return {
      success: false,
      error: '报告不存在',
    }
  }

  if (report.status === 'GENERATING') {
    return {
      success: true,
      data: {
        report,
        items: [],
        items_count: 0,
        selected_count: 0,
      },
    }
  }

  const page = params?.page ?? 1
  const pageSize = params?.page_size ?? 100
  const result = generateMockIntegrityReportItems(id, page, pageSize, {
    status: params?.status,
    data_type: params?.data_type,
    stock_code: params?.stock_code,
    period: params?.period,
  })

  return {
    success: true,
    data: {
      report: {
        ...report,
        items_count: result.total,
        selected_count: result.selected_count,
      },
      items: result.items,
      items_count: result.total,
      selected_count: result.selected_count,
    },
  }
}

export const selectItemsMock = async (
  reportId: number,
  params: {
    data_types?: string[]
    stock_code?: string
    period?: string
    status?: string
    selected: boolean
  }
): Promise<ApiResponse<{ updated_count: number }>> => {
  await new Promise(resolve => setTimeout(resolve, 300))

  const count = Math.floor(Math.random() * 50) + 10

  return {
    success: true,
    data: {
      updated_count: count,
    },
  }
}

export const generatePlanMock = async (reportId: number): Promise<ApiResponse<{ id: number }>> => {
  await new Promise(resolve => setTimeout(resolve, 500))

  return {
    success: true,
    data: {
      id: Math.floor(Math.random() * 100) + 1,
    },
  }
}

export const refreshReportMock = async (reportId: number): Promise<ApiResponse<any>> => {
  await new Promise(resolve => setTimeout(resolve, 300))

  return {
    success: true,
    data: {},
  }
}

export interface IntegrityReportHeatmapData {
  data_types: { key: string; label: string; frequency?: string | null }[]
  periods: string[]
  matrix: Record<string, number[]>
}

export const fetchIntegrityReportHeatmapMock = async (reportId: number): Promise<ApiResponse<IntegrityReportHeatmapData>> => {
  await new Promise(resolve => setTimeout(resolve, 200))

  const dataTypes = [
    { key: 'quote', label: '行情数据' },
    { key: 'historical_quote', label: '历史行情' },
    { key: 'balance_sheet', label: '资产负债表' },
    { key: 'income', label: '利润表' },
    { key: 'cash_flow', label: '现金流量表' },
    { key: 'dividend', label: '分红数据' },
  ]

  const periods = ['2024-Q1', '2024-Q2', '2024-Q3', '2024-Q4', '2023-Q1', '2023-Q2', '2023-Q3', '2023-Q4']

  const matrix: Record<string, number[]> = {}
  dataTypes.forEach(dt => {
    matrix[dt.key] = periods.map(() => Math.floor(Math.random() * 50) + 5)
  })

  return {
    success: true,
    data: {
      data_types: dataTypes,
      periods,
      matrix,
    },
  }
}

export interface DisplayFieldConfig {
  name: string
  label: string
  visible: boolean
  fixed?: boolean
  order: number
  width: number
  format?: 'price' | 'volume' | 'money' | 'percent' | 'date'
}

export interface DisplayTableConfig {
  table_name: string
  table_label: string
  config: {
    fields: DisplayFieldConfig[]
  }
}

export interface DataTypeGroup {
  key: string
  label: string
  items: {
    key: string
    label: string
    table: string
  }[]
}

export interface DisplayConfigResponse {
  groups: DataTypeGroup[]
  configs: Record<string, {
    table_label: string
    config: { fields: DisplayFieldConfig[] }
  }>
}

const DEFAULT_DISPLAY_CONFIGS: Record<string, {
  table_label: string
  config: { fields: DisplayFieldConfig[] }
}> = {
  'saa_stocks': {
    table_label: '基本信息',
    config: {
      fields: [
        { name: 'symbol', label: '股票代码', visible: true, fixed: true, order: 1, width: 100 },
        { name: 'name', label: '股票名称', visible: true, order: 2, width: 120 },
        { name: 'exchange', label: '交易所', visible: true, order: 3, width: 80 },
        { name: 'industry_classification_id', label: '所属行业', visible: true, order: 4, width: 100 },
        { name: 'listing_time', label: '上市日期', visible: true, order: 5, width: 110, format: 'date' },
        { name: 'company_name', label: '公司名称', visible: false, order: 10, width: 200 },
        { name: 'legal_representative', label: '法人代表', visible: false, order: 11, width: 100 },
        { name: 'registered_capital', label: '注册资金', visible: false, order: 12, width: 120, format: 'money' },
        { name: 'website', label: '机构网址', visible: false, order: 13, width: 200 },
      ]
    }
  },
  'saa_latest_prices': {
    table_label: '最新行情',
    config: {
      fields: [
        { name: 'symbol', label: '股票代码', visible: true, fixed: true, order: 1, width: 100 },
        { name: 'date', label: '日期', visible: true, fixed: true, order: 2, width: 110, format: 'date' },
        { name: 'price', label: '最新价', visible: true, order: 3, width: 100, format: 'price' },
      ]
    }
  },
  'saa_prices_ex': {
    table_label: '历史行情',
    config: {
      fields: [
        { name: 'code', label: '股票代码', visible: true, fixed: true, order: 1, width: 100 },
        { name: 'date', label: '日期', visible: true, fixed: true, order: 2, width: 110, format: 'date' },
        { name: 'open', label: '开盘价', visible: true, order: 3, width: 100, format: 'price' },
        { name: 'close', label: '收盘价', visible: true, order: 4, width: 100, format: 'price' },
        { name: 'high', label: '最高价', visible: true, order: 5, width: 100, format: 'price' },
        { name: 'low', label: '最低价', visible: true, order: 6, width: 100, format: 'price' },
        { name: 'volume', label: '成交量', visible: true, order: 7, width: 120, format: 'number' },
        { name: 'money', label: '成交额', visible: true, order: 8, width: 140, format: 'money' },
      ]
    }
  },
  'saa_raw_balance_sheet': {
    table_label: '资产负债表',
    config: {
      fields: [
        { name: 'symbol', label: '股票代码', visible: true, fixed: true, order: 1, width: 100 },
        { name: 'date', label: '报告日期', visible: true, fixed: true, order: 2, width: 110, format: 'date' },
        { name: 'total_assets', label: '资产总计', visible: true, order: 3, width: 140, format: 'money' },
        { name: 'total_current_assets', label: '流动资产合计', visible: true, order: 4, width: 140, format: 'money' },
        { name: 'total_liabilities', label: '负债合计', visible: true, order: 5, width: 140, format: 'money' },
        { name: 'total_current_liabilities', label: '流动负债合计', visible: true, order: 6, width: 140, format: 'money' },
        { name: 'total_shareholders_equity', label: '所有者权益合计', visible: true, order: 7, width: 150, format: 'money' },
        { name: 'monetary_funds', label: '货币资金', visible: false, order: 10, width: 130, format: 'money' },
        { name: 'accounts_receivable', label: '应收账款', visible: false, order: 11, width: 130, format: 'money' },
        { name: 'inventories', label: '存货', visible: false, order: 12, width: 130, format: 'money' },
        { name: 'fixed_assets', label: '固定资产', visible: false, order: 13, width: 130, format: 'money' },
        { name: 'short_term_borrowings', label: '短期借款', visible: false, order: 14, width: 130, format: 'money' },
        { name: 'long_term_borrowings', label: '长期借款', visible: false, order: 15, width: 130, format: 'money' },
      ]
    }
  },
  'saa_raw_income_statement': {
    table_label: '利润表',
    config: {
      fields: [
        { name: 'symbol', label: '股票代码', visible: true, fixed: true, order: 1, width: 100 },
        { name: 'date', label: '报告日期', visible: true, fixed: true, order: 2, width: 110, format: 'date' },
        { name: 'operating_revenue', label: '营业收入', visible: true, order: 3, width: 140, format: 'money' },
        { name: 'operating_cost', label: '营业成本', visible: true, order: 4, width: 140, format: 'money' },
        { name: 'business_profit', label: '营业利润', visible: true, order: 5, width: 140, format: 'money' },
        { name: 'net_profit', label: '净利润', visible: true, order: 6, width: 140, format: 'money' },
        { name: 'controlling_net_profit', label: '归母净利润', visible: true, order: 7, width: 140, format: 'money' },
        { name: 'basic_earnings_per_share', label: '基本每股收益', visible: true, order: 8, width: 120, format: 'price' },
        { name: 'selling_expenses', label: '销售费用', visible: false, order: 10, width: 130, format: 'money' },
        { name: 'administrative_expenses', label: '管理费用', visible: false, order: 11, width: 130, format: 'money' },
        { name: 'financial_expenses', label: '财务费用', visible: false, order: 12, width: 130, format: 'money' },
      ]
    }
  },
  'saa_raw_cash_flow_statement': {
    table_label: '现金流量表',
    config: {
      fields: [
        { name: 'symbol', label: '股票代码', visible: true, fixed: true, order: 1, width: 100 },
        { name: 'date', label: '报告日期', visible: true, fixed: true, order: 2, width: 110, format: 'date' },
        { name: 'net_cash_flows_from_operating_activities', label: '经营活动现金流量净额', visible: true, order: 3, width: 180, format: 'money' },
        { name: 'net_cash_flows_from_investing_activities', label: '投资活动现金流量净额', visible: true, order: 4, width: 180, format: 'money' },
        { name: 'net_cash_flows_from_financing_activities', label: '筹资活动现金流量净额', visible: true, order: 5, width: 180, format: 'money' },
      ]
    }
  },
  'saa_raw_main_business': {
    table_label: '主营业务',
    config: {
      fields: [
        { name: 'symbol', label: '股票代码', visible: true, fixed: true, order: 1, width: 100 },
        { name: 'date', label: '报告日期', visible: true, fixed: true, order: 2, width: 110, format: 'date' },
        { name: 'category', label: '分类类型', visible: true, order: 3, width: 100 },
        { name: 'item_name', label: '主营构成', visible: true, order: 4, width: 150 },
        { name: 'main_business_income', label: '主营收入', visible: true, order: 5, width: 140, format: 'money' },
        { name: 'main_business_cost', label: '主营成本', visible: true, order: 6, width: 140, format: 'money' },
        { name: 'main_business_profit', label: '主营利润', visible: true, order: 7, width: 140, format: 'money' },
        { name: 'gross_profit_margin', label: '毛利率', visible: true, order: 8, width: 100, format: 'percent' },
      ]
    }
  },
  'saa_capitals': {
    table_label: '股本变动',
    config: {
      fields: [
        { name: 'symbol', label: '股票代码', visible: true, fixed: true, order: 1, width: 100 },
        { name: 'date', label: '变更日期', visible: true, fixed: true, order: 2, width: 110, format: 'date' },
        { name: 'capital', label: '总股本', visible: true, order: 3, width: 140, format: 'volume' },
      ]
    }
  },
  'saa_dividends': {
    table_label: '分红数据',
    config: {
      fields: [
        { name: 'symbol', label: '股票代码', visible: true, fixed: true, order: 1, width: 100 },
        { name: 'date', label: '除权除息日', visible: true, fixed: true, order: 2, width: 120, format: 'date' },
        { name: 'dps', label: '每股分红', visible: true, order: 3, width: 100, format: 'price' },
        { name: 'dividend', label: '分红总额', visible: true, order: 4, width: 140, format: 'money' },
      ]
    }
  },
}

const DATA_TYPE_GROUPS: DataTypeGroup[] = [
  {
    key: 'basic',
    label: '基本信息',
    items: [
      { key: 'info', label: '基本信息', table: 'saa_stocks' },
    ]
  },
  {
    key: 'quote',
    label: '行情数据',
    items: [
      { key: 'quote', label: '最新行情', table: 'saa_latest_prices' },
      { key: 'historical_quote', label: '历史行情', table: 'saa_prices_ex' },
    ]
  },
  {
    key: 'statement',
    label: '财务报表',
    items: [
      { key: 'balance_sheet', label: '资产负债表', table: 'saa_raw_balance_sheet' },
      { key: 'income', label: '利润表', table: 'saa_raw_income_statement' },
      { key: 'cash_flow', label: '现金流量表', table: 'saa_raw_cash_flow_statement' },
    ]
  },
  {
    key: 'other',
    label: '其他数据',
    items: [
      { key: 'main_business', label: '主营业务', table: 'saa_raw_main_business' },
      { key: 'capital', label: '股本变动', table: 'saa_capitals' },
      { key: 'dividend', label: '分红数据', table: 'saa_dividends' },
    ]
  },
]

export const fetchDisplayConfig = async (table?: string): Promise<ApiResponse<DisplayConfigResponse | DisplayTableConfig>> => {
  const params = table ? { table } : {}
  const response = await api.get('/display-field-config/', { params })
  return response.data
}

export const saveDisplayConfig = async (tableName: string, config: { fields: DisplayFieldConfig[] }): Promise<ApiResponse<null>> => {
  const response = await api.put('/display-field-config/', { table_name: tableName, config })
  return response.data
}

export const fetchStockData = async (
  symbol: string,
  tableName: string,
  page: number = 1,
  pageSize: number = 50
): Promise<ApiResponse<{ results: Record<string, unknown>[], total: number }>> => {
  const response = await api.get(`/stock-data/${symbol}/${tableName}/`, {
    params: { page, page_size: pageSize }
  })
  return response.data
}

export const fetchDisplayConfigMock = async (table?: string): Promise<ApiResponse<DisplayConfigResponse | DisplayTableConfig>> => {
  await new Promise(resolve => setTimeout(resolve, 200))

  if (table) {
    const config = DEFAULT_DISPLAY_CONFIGS[table]
    if (!config) {
      return { success: false, error: 'Table not found' }
    }
    return {
      success: true,
      data: {
        table_name: table,
        table_label: config.table_label,
        config: config.config
      }
    }
  }

  return {
    success: true,
    data: {
      groups: DATA_TYPE_GROUPS,
      configs: DEFAULT_DISPLAY_CONFIGS
    }
  }
}

export const saveDisplayConfigMock = async (tableName: string, config: { fields: DisplayFieldConfig[] }): Promise<ApiResponse<null>> => {
  await new Promise(resolve => setTimeout(resolve, 300))
  const existing = DEFAULT_DISPLAY_CONFIGS[tableName]
  DEFAULT_DISPLAY_CONFIGS[tableName] = {
    table_label: existing?.table_label ?? tableName,
    config
  }
  return { success: true, data: null }
}

function generateMockStockData(tableName: string, symbol: string): Record<string, unknown>[] {
  const results: Record<string, unknown>[] = []
  const count = 50

  if (tableName === 'saa_stocks') {
    return [{
      symbol,
      name: `${symbol}公司`,
      exchange: symbol.startsWith('6') ? 'SH' : 'SZ',
      industry_classification_id: '银行',
      listing_time: '2020-01-01',
      company_name: `${symbol}股份有限公司`,
      legal_representative: '张三',
      registered_capital: 1000000000,
      website: 'https://example.com',
    }]
  }

  if (tableName === 'saa_latest_prices') {
    return [{
      symbol,
      date: new Date().toISOString().split('T')[0],
      price: 10 + Math.random() * 90,
    }]
  }

  for (let i = 0; i < count; i++) {
    const date = new Date()
    date.setDate(date.getDate() - i * 30)

    const row: Record<string, unknown> = {
      symbol,
      date: date.toISOString().split('T')[0],
    }

    if (tableName === 'saa_prices_ex') {
      row.price = 10 + Math.random() * 90
    } else if (tableName === 'saa_raw_balance_sheet') {
      row.total_assets = 1000000000 + Math.random() * 10000000000
      row.total_current_assets = 500000000 + Math.random() * 5000000000
      row.total_liabilities = 300000000 + Math.random() * 3000000000
      row.total_current_liabilities = 200000000 + Math.random() * 2000000000
      row.total_shareholders_equity = 400000000 + Math.random() * 4000000000
      row.monetary_funds = 100000000 + Math.random() * 1000000000
      row.accounts_receivable = 50000000 + Math.random() * 500000000
      row.inventories = 30000000 + Math.random() * 300000000
      row.fixed_assets = 200000000 + Math.random() * 2000000000
      row.short_term_borrowings = 100000000 + Math.random() * 1000000000
      row.long_term_borrowings = 50000000 + Math.random() * 500000000
    } else if (tableName === 'saa_raw_income_statement') {
      row.operating_revenue = 500000000 + Math.random() * 5000000000
      row.operating_cost = 300000000 + Math.random() * 3000000000
      row.business_profit = 50000000 + Math.random() * 500000000
      row.net_profit = 30000000 + Math.random() * 300000000
      row.controlling_net_profit = 28000000 + Math.random() * 280000000
      row.basic_earnings_per_share = 0.1 + Math.random() * 2
      row.selling_expenses = 10000000 + Math.random() * 100000000
      row.administrative_expenses = 5000000 + Math.random() * 50000000
      row.financial_expenses = 3000000 + Math.random() * 30000000
    } else if (tableName === 'saa_raw_cash_flow_statement') {
      row.net_cash_flows_from_operating_activities = 50000000 + Math.random() * 500000000
      row.net_cash_flows_from_investing_activities = -100000000 - Math.random() * 1000000000
      row.net_cash_flows_from_financing_activities = -50000000 + Math.random() * 200000000
    } else if (tableName === 'saa_raw_main_business') {
      row.category = i % 2 === 0 ? 'PRODUCT' : 'REGION'
      row.item_name = i % 2 === 0 ? `产品${i % 5 + 1}` : `地区${i % 5 + 1}`
      row.main_business_income = 50000000 + Math.random() * 500000000
      row.main_business_cost = 30000000 + Math.random() * 300000000
      row.main_business_profit = 10000000 + Math.random() * 100000000
      row.gross_profit_margin = 0.1 + Math.random() * 0.4
    } else if (tableName === 'saa_capitals') {
      row.capital = 1000000000 + Math.random() * 10000000000
    } else if (tableName === 'saa_dividends') {
      row.dps = 0.1 + Math.random() * 1
      row.dividend = 100000000 + Math.random() * 1000000000
    }

    results.push(row)
  }

  return results
}

export const fetchStockDataMock = async (
  symbol: string,
  tableName: string,
  _page: number = 1,
  _pageSize: number = 50
): Promise<ApiResponse<{ results: Record<string, unknown>[], total: number }>> => {
  await new Promise(resolve => setTimeout(resolve, 300))

  const results = generateMockStockData(tableName, symbol)

  return {
    success: true,
    data: {
      results,
      total: results.length,
    }
  }
}

export default api
