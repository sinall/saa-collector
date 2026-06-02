<template>
  <div class="data-browse-type">
    <div class="page-header">
      <h3>数据浏览</h3>
    </div>
    
    <el-card>
      <template #header>
        <div class="filter-bar">
          <el-select v-model="selectedDataType" placeholder="选择数据类型" style="width: 200px" @change="onDataTypeChange">
            <el-option-group
              v-for="group in groups"
              :key="group.key"
              :label="group.label"
            >
              <el-option
                v-for="dt in groupedDataTypes[group.key]"
                :key="dt.key"
                :label="dt.label"
                :value="dt.key"
              />
            </el-option-group>
          </el-select>
          
          <el-date-picker
            v-model="dateRange"
            type="daterange"
            unlink-panels
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            style="width: 300px"
            @change="onDateRangeChange"
          />

          <el-input
            v-model="keyword"
            :placeholder="selectedDataType === 'index_weights' ? '输入指数代码' : selectedDataType === 'industry_stocks' ? '输入行业代码' : '输入关键字'"
            clearable
            style="width: 220px"
            @keyup.enter="onKeywordSearch"
            @clear="onKeywordClear"
          />

          <el-button type="primary" @click="onKeywordSearch">查询</el-button>
          
          <el-button @click="showColumnSettings = true" link>
            <el-icon><Setting /></el-icon>
            列设置
          </el-button>
        </div>
      </template>
      
      <div class="table-container" v-loading="loading">
        <AgGridVue
          :columnDefs="visibleColumnDefs"
          :rowData="tableData"
          :defaultColDef="defaultColDef"
          style="width: 100%; height: calc(100vh - 320px);"
          class="ag-theme-alpine"
        />
      </div>
      
      <div class="pagination-container">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[20, 50, 100, 200]"
          :total="totalRecords"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="onPageSizeChange"
          @current-change="onPageChange"
        />
      </div>
    </el-card>
    
    <el-dialog v-model="showColumnSettings" title="列设置" width="500px">
      <div class="column-settings">
        <div class="settings-header">
          <el-checkbox
            v-model="selectAllColumns"
            :indeterminate="isIndeterminate"
            @change="onSelectAllChange"
          >
            全选
          </el-checkbox>
          <el-button type="primary" link @click="resetColumnSettings">恢复默认</el-button>
        </div>
        
        <el-divider />
        
        <div class="column-list">
          <div
            v-for="col in editableColumns"
            :key="col.field"
            class="column-item"
          >
            <el-checkbox
              v-model="col.visible"
              :disabled="col.pinned === 'left'"
              @change="onColumnVisibilityChange"
            >
              {{ col.headerName }}
            </el-checkbox>
            <span v-if="col.pinned === 'left'" class="fixed-tag">(固定)</span>
          </div>
        </div>
      </div>
      
      <template #footer>
        <el-button @click="showColumnSettings = false">取消</el-button>
        <el-button type="primary" @click="saveColumnSettings">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { AgGridVue } from 'ag-grid-vue3'
import { ColDef } from 'ag-grid-community'
import { Setting } from '@element-plus/icons-vue'
import {
  fetchDisplayConfig,
  saveDisplayConfig,
  fetchTypeBrowseData,
  type DisplayFieldConfig,
  type DataTypeGroup,
} from '@/utils/api'
import { useDataTypes } from '@/composables/useDataTypes'

const { dataTypes, groups, groupedDataTypes, loadDataTypes } = useDataTypes()

interface EditableColDef extends ColDef {
  visible: boolean
}

type TypeBrowseRow = Record<string, unknown>

const DATA_TYPE_TO_TABLE: Record<string, string> = {
  info: 'saa_stocks',
  quote: 'saa_latest_prices',
  historical_quote: 'saa_prices_ex',
  balance_sheet: 'saa_raw_balance_sheet',
  income: 'saa_raw_income_statement',
  cash_flow: 'saa_raw_cash_flow_statement',
  main_business: 'saa_raw_main_business',
  capital: 'saa_capitals',
  dividend: 'saa_dividends',
  trade_days: 'saa_trade_days',
  index_weights: 'saa_index_weights',
  industries: 'saa_industries',
  industry_stocks: 'saa_industry_stocks',
}

const displayConfigs = ref<Record<string, { table_label: string; config: { fields: DisplayFieldConfig[] } }>>({})

const currentTable = computed(() => DATA_TYPE_TO_TABLE[selectedDataType.value] || 'saa_prices_ex')

const currentConfig = computed(() => displayConfigs.value[currentTable.value]?.config)

const router = useRouter()
const route = useRoute()
const selectedDataType = ref(route.params.type as string || 'info')
const dateRange = ref<[Date, Date] | null>(null)
const keyword = ref('')
const loading = ref(false)
const tableData = ref<Record<string, unknown>[]>([])
const showColumnSettings = ref(false)
const editableColumns = ref<EditableColDef[]>([])
const currentPage = ref(1)
const pageSize = ref(50)
const totalRecords = ref(0)

const defaultColDef = reactive<ColDef>({
  resizable: true,
  sortable: true,
  filter: true,
  minWidth: 100,
})

const onStockClick = (symbol: string) => {
  router.push(`/stock/${symbol}/${selectedDataType.value}`)
}

const loadDisplayConfig = async () => {
  const response = await fetchDisplayConfig()
  if (response.success && response.data) {
    const data = response.data as { groups: DataTypeGroup[]; configs: Record<string, { table_label: string; config: { fields: DisplayFieldConfig[] } }> }
    displayConfigs.value = data.configs
  }
}

const createColDefFromConfig = (field: DisplayFieldConfig): ColDef => {
  const colDef: ColDef = {
    field: field.name,
    headerName: field.label,
    width: field.width || 130,
    pinned: field.fixed ? 'left' : undefined,
  }
  
  if (field.name === 'stock_name' || field.name === 'name') {
    colDef.cellStyle = { color: '#409eff', cursor: 'pointer' }
    colDef.onCellClicked = (params) => {
      const row = params.data as TypeBrowseRow
      const stockCode = row.stock_code || row.symbol
      if (stockCode) onStockClick(stockCode as string)
    }
  }
  if (field.name === 'stock_code' || field.name === 'symbol') {
    colDef.cellStyle = { color: '#409eff', cursor: 'pointer' }
    colDef.onCellClicked = (params) => onStockClick(params.value)
  }
  if (field.name === 'code' && ['historical_quote', 'index_weights', 'industry_stocks'].includes(selectedDataType.value)) {
    colDef.cellStyle = { color: '#409eff', cursor: 'pointer' }
    colDef.onCellClicked = (params) => onStockClick(params.value)
  }

  const numericFormats = ['money', 'volume', 'percent', 'price']
  const isNumeric = numericFormats.includes(field.format || '')

  if (isNumeric) {
    colDef.type = 'numericColumn'
  }

  if (field.format === 'money') {
    colDef.valueFormatter = (p) => formatMoney(p.value)
  } else if (field.format === 'volume') {
    colDef.valueFormatter = (p) => formatVolume(p.value)
  } else if (field.format === 'percent') {
    colDef.valueFormatter = (p) => p.value ? (p.value * 100).toFixed(2) + '%' : '-'
  } else if (field.format === 'price') {
    colDef.valueFormatter = (p) => p.value ? (p.value as number).toFixed(2) : '-'
  }
  
  return colDef
}

const historicalQuoteColumns: ColDef[] = [
  { 
    field: 'stock_name', 
    headerName: '股票名称', 
    width: 100, 
    pinned: 'left',
    cellStyle: { color: '#409eff', cursor: 'pointer' },
    onCellClicked: (params) => {
      const row = params.data as TypeBrowseRow
      if (row.stock_code) onStockClick(row.stock_code as string)
    }
  },
  { 
    field: 'stock_code', 
    headerName: '股票代码', 
    width: 100, 
    pinned: 'left',
    cellStyle: { color: '#409eff', cursor: 'pointer' },
    onCellClicked: (params) => onStockClick(params.value)
  },
  { field: 'trade_date', headerName: '交易日期', width: 130 },
  { field: 'open', headerName: '开盘价', width: 100, type: 'numericColumn' },
  { field: 'high', headerName: '最高价', width: 100, type: 'numericColumn' },
  { field: 'low', headerName: '最低价', width: 100, type: 'numericColumn' },
  { field: 'close', headerName: '收盘价', width: 100, type: 'numericColumn' },
  { field: 'volume', headerName: '成交量', width: 120, type: 'numericColumn', valueFormatter: (p) => formatVolume(p.value) },
  { field: 'amount', headerName: '成交额', width: 130, type: 'numericColumn', valueFormatter: (p) => formatAmount(p.value) },
]

const balanceSheetColumns: ColDef[] = [
  { 
    field: 'stock_name', 
    headerName: '股票名称', 
    width: 100, 
    pinned: 'left',
    cellStyle: { color: '#409eff', cursor: 'pointer' },
    onCellClicked: (params) => {
      const row = params.data as TypeBrowseRow
      if (row.stock_code) onStockClick(row.stock_code as string)
    }
  },
  { 
    field: 'stock_code', 
    headerName: '股票代码', 
    width: 100, 
    pinned: 'left',
    cellStyle: { color: '#409eff', cursor: 'pointer' },
    onCellClicked: (params) => onStockClick(params.value)
  },
  { field: 'report_period', headerName: '报告期', width: 120 },
  { field: 'report_date', headerName: '报告日期', width: 130 },
  { field: 'total_assets', headerName: '资产总计', width: 150, type: 'numericColumn', valueFormatter: (p) => formatMoney(p.value) },
  { field: 'total_liabilities', headerName: '负债合计', width: 150, type: 'numericColumn', valueFormatter: (p) => formatMoney(p.value) },
  { field: 'total_equity', headerName: '所有者权益', width: 150, type: 'numericColumn', valueFormatter: (p) => formatMoney(p.value) },
]

const tradeDaysColumns: ColDef[] = [
  { field: 'date', headerName: '日期', width: 150, pinned: 'left' },
  { field: 'is_open', headerName: '是否交易日', width: 120, valueFormatter: (p) => p.value === 1 ? '是' : '否' },
]

const indexWeightsColumns: ColDef[] = [
  { field: 'index', headerName: '指数代码', width: 120, pinned: 'left' },
  { field: 'date', headerName: '日期', width: 110, pinned: 'left' },
  { field: 'stock_name', headerName: '股票名称', width: 120 },
  { field: 'code', headerName: '股票代码', width: 100 },
  { field: 'display_name', headerName: '显示名称', width: 120 },
  { field: 'weight', headerName: '权重', width: 100, type: 'numericColumn', valueFormatter: (p) => p.value ? (p.value * 100).toFixed(2) + '%' : '-' },
]

const industryStocksColumns: ColDef[] = [
  { field: 'industry_code', headerName: '行业代码', width: 120, pinned: 'left' },
  { field: 'date', headerName: '日期', width: 110, pinned: 'left' },
  { field: 'stock_name', headerName: '股票名称', width: 120 },
  { field: 'code', headerName: '股票代码', width: 100 },
]

const infoColumns: ColDef[] = [
  { 
    field: 'stock_name', 
    headerName: '股票名称', 
    width: 100, 
    pinned: 'left',
    cellStyle: { color: '#409eff', cursor: 'pointer' },
    onCellClicked: (params) => {
      const row = params.data as TypeBrowseRow
      if (row.stock_code) onStockClick(row.stock_code as string)
    }
  },
  { 
    field: 'stock_code', 
    headerName: '股票代码', 
    width: 100, 
    pinned: 'left',
    cellStyle: { color: '#409eff', cursor: 'pointer' },
    onCellClicked: (params) => onStockClick(params.value)
  },
  { field: 'exchange', headerName: '交易所', width: 100 },
  { field: 'industry', headerName: '所属行业', width: 120 },
  { field: 'list_date', headerName: '上市日期', width: 120 },
]

const quoteColumns: ColDef[] = [
  { 
    field: 'stock_name', 
    headerName: '股票名称', 
    width: 100, 
    pinned: 'left',
    cellStyle: { color: '#409eff', cursor: 'pointer' },
    onCellClicked: (params) => {
      const row = params.data as TypeBrowseRow
      if (row.stock_code) onStockClick(row.stock_code as string)
    }
  },
  { 
    field: 'stock_code', 
    headerName: '股票代码', 
    width: 100, 
    pinned: 'left',
    cellStyle: { color: '#409eff', cursor: 'pointer' },
    onCellClicked: (params) => onStockClick(params.value)
  },
  { field: 'date', headerName: '日期', width: 120 },
  { field: 'price', headerName: '最新价', width: 100, type: 'numericColumn' },
  { field: 'change_pct', headerName: '涨跌幅', width: 100, type: 'numericColumn', valueFormatter: (p) => p.value ? (p.value * 100).toFixed(2) + '%' : '-' },
]

const incomeColumns: ColDef[] = [
  { 
    field: 'stock_name', 
    headerName: '股票名称', 
    width: 100, 
    pinned: 'left',
    cellStyle: { color: '#409eff', cursor: 'pointer' },
    onCellClicked: (params) => {
      const row = params.data as TypeBrowseRow
      if (row.stock_code) onStockClick(row.stock_code as string)
    }
  },
  { 
    field: 'stock_code', 
    headerName: '股票代码', 
    width: 100, 
    pinned: 'left',
    cellStyle: { color: '#409eff', cursor: 'pointer' },
    onCellClicked: (params) => onStockClick(params.value)
  },
  { field: 'report_period', headerName: '报告期', width: 120 },
  { field: 'report_date', headerName: '报告日期', width: 130 },
  { field: 'operating_revenue', headerName: '营业收入', width: 150, type: 'numericColumn', valueFormatter: (p) => formatMoney(p.value) },
  { field: 'operating_cost', headerName: '营业成本', width: 150, type: 'numericColumn', valueFormatter: (p) => formatMoney(p.value) },
  { field: 'net_profit', headerName: '净利润', width: 150, type: 'numericColumn', valueFormatter: (p) => formatMoney(p.value) },
]

const cashFlowColumns: ColDef[] = [
  { 
    field: 'stock_name', 
    headerName: '股票名称', 
    width: 100, 
    pinned: 'left',
    cellStyle: { color: '#409eff', cursor: 'pointer' },
    onCellClicked: (params) => {
      const row = params.data as TypeBrowseRow
      if (row.stock_code) onStockClick(row.stock_code as string)
    }
  },
  { 
    field: 'stock_code', 
    headerName: '股票代码', 
    width: 100, 
    pinned: 'left',
    cellStyle: { color: '#409eff', cursor: 'pointer' },
    onCellClicked: (params) => onStockClick(params.value)
  },
  { field: 'report_period', headerName: '报告期', width: 120 },
  { field: 'report_date', headerName: '报告日期', width: 130 },
  { field: 'operating_cash_flow', headerName: '经营活动现金流', width: 160, type: 'numericColumn', valueFormatter: (p) => formatMoney(p.value) },
  { field: 'investing_cash_flow', headerName: '投资活动现金流', width: 160, type: 'numericColumn', valueFormatter: (p) => formatMoney(p.value) },
  { field: 'financing_cash_flow', headerName: '筹资活动现金流', width: 160, type: 'numericColumn', valueFormatter: (p) => formatMoney(p.value) },
]

const mainBusinessColumns: ColDef[] = [
  { 
    field: 'stock_name', 
    headerName: '股票名称', 
    width: 100, 
    pinned: 'left',
    cellStyle: { color: '#409eff', cursor: 'pointer' },
    onCellClicked: (params) => {
      const row = params.data as TypeBrowseRow
      if (row.stock_code) onStockClick(row.stock_code as string)
    }
  },
  { 
    field: 'stock_code', 
    headerName: '股票代码', 
    width: 100, 
    pinned: 'left',
    cellStyle: { color: '#409eff', cursor: 'pointer' },
    onCellClicked: (params) => onStockClick(params.value)
  },
  { field: 'report_period', headerName: '报告期', width: 120 },
  { field: 'business_type', headerName: '业务类型', width: 150 },
  { field: 'revenue', headerName: '营业收入', width: 150, type: 'numericColumn', valueFormatter: (p) => formatMoney(p.value) },
  { field: 'revenue_ratio', headerName: '收入占比', width: 100, type: 'numericColumn', valueFormatter: (p) => p.value ? (p.value * 100).toFixed(2) + '%' : '-' },
]

const capitalColumns: ColDef[] = [
  { 
    field: 'stock_name', 
    headerName: '股票名称', 
    width: 100, 
    pinned: 'left',
    cellStyle: { color: '#409eff', cursor: 'pointer' },
    onCellClicked: (params) => {
      const row = params.data as TypeBrowseRow
      if (row.stock_code) onStockClick(row.stock_code as string)
    }
  },
  { 
    field: 'stock_code', 
    headerName: '股票代码', 
    width: 100, 
    pinned: 'left',
    cellStyle: { color: '#409eff', cursor: 'pointer' },
    onCellClicked: (params) => onStockClick(params.value)
  },
  { field: 'change_date', headerName: '变动日期', width: 120 },
  { field: 'total_shares', headerName: '总股本', width: 150, type: 'numericColumn', valueFormatter: (p) => formatVolume(p.value) },
  { field: 'circulating_shares', headerName: '流通股', width: 150, type: 'numericColumn', valueFormatter: (p) => formatVolume(p.value) },
  { field: 'change_reason', headerName: '变动原因', width: 150 },
]

const dividendColumns: ColDef[] = [
  { 
    field: 'stock_name', 
    headerName: '股票名称', 
    width: 100, 
    pinned: 'left',
    cellStyle: { color: '#409eff', cursor: 'pointer' },
    onCellClicked: (params) => {
      const row = params.data as TypeBrowseRow
      if (row.stock_code) onStockClick(row.stock_code as string)
    }
  },
  { 
    field: 'stock_code', 
    headerName: '股票代码', 
    width: 100, 
    pinned: 'left',
    cellStyle: { color: '#409eff', cursor: 'pointer' },
    onCellClicked: (params) => onStockClick(params.value)
  },
  { field: 'report_period', headerName: '报告期', width: 120 },
  { field: 'dividend_date', headerName: '分红日期', width: 120 },
  { field: 'dividend_per_share', headerName: '每股分红', width: 100, type: 'numericColumn', valueFormatter: (p) => p.value ? (p.value as number).toFixed(2) + '元' : '-' },
  { field: 'dividend_type', headerName: '分红类型', width: 100 },
]

const columnDefs = computed<ColDef[]>(() => {
  const config = currentConfig.value
  if (config && config.fields && config.fields.length > 0) {
    return config.fields
      .filter(f => f.visible)
      .sort((a, b) => a.order - b.order)
      .map(f => createColDefFromConfig(f))
  }
  switch (selectedDataType.value) {
    case 'info':
      return infoColumns
    case 'quote':
      return quoteColumns
    case 'historical_quote':
      return historicalQuoteColumns
    case 'balance_sheet':
      return balanceSheetColumns
    case 'income':
      return incomeColumns
    case 'cash_flow':
      return cashFlowColumns
    case 'main_business':
      return mainBusinessColumns
    case 'capital':
      return capitalColumns
    case 'dividend':
      return dividendColumns
    case 'trade_days':
      return tradeDaysColumns
    case 'index_weights':
      return indexWeightsColumns
    case 'industry_stocks':
      return industryStocksColumns
    case 'industries':
      return [
        { field: 'index', headerName: '行业代码', width: 120, pinned: 'left' },
        { field: 'name', headerName: '行业名称', width: 160 },
        { field: 'start_date', headerName: '开始日期', width: 120 },
      ]
    default:
      return historicalQuoteColumns
  }
})

const initEditableColumns = () => {
  const config = currentConfig.value
  if (config && config.fields && config.fields.length > 0) {
    editableColumns.value = config.fields
      .sort((a, b) => a.order - b.order)
      .map(f => ({
        ...createColDefFromConfig(f),
        visible: f.visible,
      }))
  } else {
    editableColumns.value = columnDefs.value.map(col => ({
      ...col,
      visible: true
    }))
  }
}

const visibleColumnDefs = computed<ColDef[]>(() => {
  return editableColumns.value.filter(col => col.visible)
})

const selectAllColumns = computed({
  get: () => editableColumns.value.every(c => c.visible),
  set: () => {}
})

const isIndeterminate = computed(() => {
  const visibleCount = editableColumns.value.filter(c => c.visible).length
  return visibleCount > 0 && visibleCount < editableColumns.value.length
})

const onSelectAllChange = (val: boolean) => {
  editableColumns.value.forEach(col => {
    if (col.pinned !== 'left') {
      col.visible = val
    }
  })
}

const onColumnVisibilityChange = () => {
}

const resetColumnSettings = () => {
  initEditableColumns()
}

const saveColumnSettings = async () => {
  const config = currentConfig.value
  if (!config) {
    showColumnSettings.value = false
    return
  }
  
  const newFields: DisplayFieldConfig[] = config.fields.map(f => {
    const editableCol = editableColumns.value.find(c => c.field === f.name)
    return {
      ...f,
      visible: editableCol?.visible ?? f.visible
    }
  })
  
  const response = await saveDisplayConfig(currentTable.value, { fields: newFields })
  
  if (response.success) {
    const existing = displayConfigs.value[currentTable.value]
    displayConfigs.value[currentTable.value] = {
      table_label: existing?.table_label ?? currentTable.value,
      config: { fields: newFields }
    }
    initEditableColumns()
  }
  
  showColumnSettings.value = false
}

watch(selectedDataType, () => {
  initEditableColumns()
})

const formatVolume = (value: number | null): string => {
  if (value === null) return '-'
  if (value >= 100000000) return (value / 100000000).toFixed(2) + '亿'
  if (value >= 10000) return (value / 10000).toFixed(2) + '万'
  return value.toLocaleString()
}

const formatAmount = (value: number | null): string => {
  if (value === null) return '-'
  return (value / 100000000).toFixed(2) + '亿'
}

const formatMoney = (value: number | null): string => {
  if (value === null) return '-'
  return (value / 100000000).toFixed(2) + '亿'
}

const loadData = async () => {
  loading.value = true
  try {
    const tableName = DATA_TYPE_TO_TABLE[selectedDataType.value]
    if (!tableName) return
    
    const startDate = dateRange.value?.[0]?.toISOString().split('T')[0]
    const endDate = dateRange.value?.[1]?.toISOString().split('T')[0]
    
    const response = await fetchTypeBrowseData(
      tableName,
      currentPage.value,
      pageSize.value,
      startDate,
      endDate,
      keyword.value.trim() || undefined
    )
    if (response.success && response.data) {
      tableData.value = response.data.results
      totalRecords.value = response.data.total
    }
  } catch (error) {
    console.error('Failed to load data:', error)
  } finally {
    loading.value = false
  }
}

const onDataTypeChange = () => {
  router.replace(`/data-browse/${selectedDataType.value}`)
  currentPage.value = 1
  keyword.value = ''
  loadData()
}

const onKeywordSearch = () => {
  currentPage.value = 1
  loadData()
}

const onKeywordClear = () => {
  currentPage.value = 1
  loadData()
}

const onDateRangeChange = () => {
  currentPage.value = 1
  loadData()
}

const onPageSizeChange = (val: number) => {
  pageSize.value = val
  currentPage.value = 1
  loadData()
}

const onPageChange = (val: number) => {
  currentPage.value = val
  loadData()
}

onMounted(async () => {
  await loadDataTypes()
  await loadDisplayConfig()
  initEditableColumns()
  loadData()
})
</script>

<style scoped>
.data-browse-type {
  height: 100%;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.page-header h3 {
  margin: 0;
  color: #303133;
}

.filter-bar {
  display: flex;
  gap: 16px;
  align-items: center;
}

.table-container {
  width: 100%;
}

.column-settings {
  max-height: 400px;
  overflow-y: auto;
}

.settings-header {
  display: flex;
  justify-content: flex-start;
  align-items: center;
  gap: 16px;
}

.column-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.column-item {
  display: flex;
  align-items: center;
 }

.pagination-container {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
 }
</style>
