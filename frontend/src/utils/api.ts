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
    { key: 'trade_days', label: '交易日' },
    { key: 'stock_info', label: '股票基本信息' },
    { key: 'quote', label: '最新行情' },
    { key: 'historical_quote', label: '历史行情' },
    { key: 'balance_sheet', label: '资产负债表' },
    { key: 'income', label: '利润表' },
    { key: 'cash_flow', label: '现金流量表' },
    { key: 'dividend', label: '分红数据' },
    { key: 'main_business', label: '主营业务' },
    { key: 'capital', label: '股本变动' },
  ]

  let periods: string[] = []
  const now = new Date()
  const startDate = new Date('2009-01-01')

  if (frequency === 'daily') {
    for (let d = new Date(startDate); d <= now; d.setDate(d.getDate() + 1)) {
      const dateStr = d.toISOString().split('T')[0]
      if (dateStr) periods.push(dateStr)
    }
  } else if (frequency === 'weekly') {
    for (let d = new Date(startDate); d <= now; d.setDate(d.getDate() + 7)) {
      const year = d.getFullYear()
      const week = Math.ceil(((d.getTime() - new Date(year, 0, 1).getTime()) / 86400000 + 1) / 7)
      periods.push(`${year}-W${String(week).padStart(2, '0')}`)
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
    matrix[dt.key] = periods.map(() => {
      const base = 0.6 + Math.random() * 0.4
      return Math.round(base * 100) / 100
    })
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
  return {
    success: true,
    data: generateMockHeatmapData(frequency),
  }
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
  const symbols = ['000001', '000002', '000003', '600000', '600001']

  if (dataType === 'historical_quote') {
    for (let i = 0; i < count; i++) {
      const basePrice = 10 + Math.random() * 90
      rows.push({
        stock_code: symbols[Math.floor(Math.random() * symbols.length)] ?? '',
        trade_date: new Date(Date.now() - Math.random() * 365 * 24 * 3600000).toISOString().split('T')[0] ?? '',
        open: Math.round(basePrice * 100) / 100,
        high: Math.round(basePrice * 1.02 * 100) / 100,
        low: Math.round(basePrice * 0.98 * 100) / 100,
        close: Math.round(basePrice * 100) / 100,
        volume: Math.floor(Math.random() * 10000000),
        amount: Math.floor(Math.random() * 100000000),
      })
    }
  } else if (dataType === 'balance_sheet') {
    for (let i = 0; i < count; i++) {
      rows.push({
        stock_code: symbols[Math.floor(Math.random() * symbols.length)] ?? '',
        report_period: `${2020 + Math.floor(Math.random() * 6)}-Q${1 + Math.floor(Math.random() * 4)}`,
        report_date: '2024-12-31',
        total_assets: Math.floor(1000000000 + Math.random() * 10000000000),
        total_liabilities: Math.floor(500000000 + Math.random() * 5000000000),
        total_equity: Math.floor(500000000 + Math.random() * 5000000000),
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
  executions: {
    id: number
    status: 'SUCCESS' | 'FAILED' | 'RUNNING'
    status_display: string
    executed_at: string
    message: string
  }[]
}

function generateMockCollectSchedules(): CollectSchedule[] {
  const schedules: CollectSchedule[] = []
  const dataTypes = ['quote', 'historical_quote', 'balance_sheet', 'income', 'cash_flow']
  const frequencies = ['daily', 'weekly', 'monthly', 'quarterly', 'yearly']
  const frequencyDisplays = ['日度', '周度', '月度', '季度', '年度']
  const stockCodes = ['000001', '000002', '600000', '600001', '600036']
  
  for (let i = 1; i <= 8; i++) {
    const date = new Date()
    date.setDate(date.getDate() - (i - 1) * 3)
    
    const frequencyIndex = Math.floor(Math.random() * frequencies.length)
    const dataTypeIndex = Math.floor(Math.random() * dataTypes.length)
    const frequency = frequencies[frequencyIndex] ?? 'daily'
    const frequencyDisplay = frequencyDisplays[frequencyIndex] ?? '日度'
    
    schedules.push({
      id: i,
      name: `${dataTypes[dataTypeIndex]} 采集日程 - ${frequency}度`,
      data_type: dataTypes[dataTypeIndex] ?? 'quote',
      data_type_display: dataTypes[dataTypeIndex] ?? 'quote',
      symbols: i % 2 === 0 ? [] : stockCodes.slice(0, 3 + Math.floor(Math.random() * 3)),
      cron_expression: frequency === 'daily' ? '0 0 * * *' : frequency === 'weekly' ? '0 0 * * * 1' : frequency === 'monthly' ? '0 0 1 * *' : frequency === 'quarterly' ? '0 0 1 1 */' : '0 0 1 1 1',
      params: {
        date_start: '2009-01-01',
        date_end: date.toISOString().split('T')[0],
      },
      enabled: Math.random() > 0.5,
      created_at: date.toISOString(),
      updated_at: new Date().toISOString(),
      executions: [
        {
          id: i * 10 + 1,
          status: 'SUCCESS',
          status_display: '执行成功',
          message: '成功采集了 100 条数据',
          executed_at: date.toISOString(),
        },
        {
          id: i * 10 + 2,
          status: Math.random() > 0.3 ? 'FAILED' : 'RUNNING',
          status_display: Math.random() > 0.3 ? '执行失败' : '执行中',
          message: Math.random() > 0.3 ? '网络错误' : '正在采集...',
          executed_at: new Date(date.getTime() - 3600000).toISOString(),
        },
      ],
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
    const status = statuses[statusIndex]
    
    plans.push({
      id: i,
      name: `采集计划 ${i}`,
      status,
      status_display: statusDisplays[statusIndex],
      execution_mode_display: '手动执行',
      source_report_name: i > 2 ? `完整性检查报告 #${i - 2}` : undefined,
      created_at: date.toISOString(),
      started_at: status !== 'PENDING' ? new Date(date.getTime() + 60000).toISOString() : undefined,
      completed_at: status === 'COMPLETED' || status === 'FAILED' ? new Date(date.getTime() + 3600000).toISOString() : undefined,
      jobs: [
        {
          data_type_display: dataTypeDisplays[i % dataTypeDisplays.length],
          symbols: stockCodes.slice(0, 3 + Math.floor(Math.random() * 3)),
          params: {
            start_date: '2009-01-01',
            end_date: date.toISOString().split('T')[0],
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
  
  const plan = generateMockCollectPlans().find(p => p.id === id)
  if (!plan) {
    return {
      success: false,
      error: '采集计划不存在',
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
  const dataTypeOptions = ['quote', 'historical_quote', 'balance_sheet', 'income', 'cash_flow', 'dividend', 'capital', 'main_business', 'trade_days', 'valuation']
  
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
  const dataTypes = ['quote', 'historical_quote', 'balance_sheet', 'income', 'cash_flow', 'dividend', 'capital', 'main_business', 'trade_days', 'valuation']
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
  data_types: { key: string; label: string }[]
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

export default api
