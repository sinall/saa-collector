<template>
  <div class="data-browse-type">
    <div class="page-header">
      <h3>数据浏览 - 按类型</h3>
      <router-link to="/data-browse/stock">
        <el-button type="primary" link>切换到按股票浏览</el-button>
      </router-link>
    </div>
    
    <el-card>
      <template #header>
        <div class="filter-bar">
          <el-select v-model="selectedDataType" placeholder="选择数据类型" style="width: 200px" @change="onDataTypeChange">
            <el-option label="历史行情" value="historical_quote" />
            <el-option label="资产负债表" value="balance_sheet" />
            <el-option label="交易日" value="trade_days" />
          </el-select>
          
          <el-date-picker
            v-model="dateRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            style="width: 300px"
            @change="onDateRangeChange"
          />
        </div>
      </template>
      
      <div class="table-container" v-loading="loading">
        <AgGridVue
          :columnDefs="columnDefs"
          :rowData="tableData"
          :pagination="true"
          :paginationPageSize="50"
          :defaultColDef="defaultColDef"
          style="width: 100%; height: calc(100vh - 280px);"
          class="ag-theme-alpine"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed, watch } from 'vue'
import { AgGridVue } from 'ag-grid-vue3'
import { ColDef } from 'ag-grid-community'
import { fetchTypeBrowseDataMock, type TypeBrowseRow } from '@/utils/api'

const selectedDataType = ref('historical_quote')
const dateRange = ref<[Date, Date] | null>(null)
const loading = ref(false)
const tableData = ref<TypeBrowseRow[]>([])

const defaultColDef = reactive<ColDef>({
  resizable: true,
  sortable: true,
  filter: true,
  minWidth: 100,
})

const historicalQuoteColumns: ColDef[] = [
  { field: 'stock_code', headerName: '股票代码', width: 120, pinned: 'left' },
  { field: 'trade_date', headerName: '交易日期', width: 130 },
  { field: 'open', headerName: '开盘价', width: 100 },
  { field: 'high', headerName: '最高价', width: 100 },
  { field: 'low', headerName: '最低价', width: 100 },
  { field: 'close', headerName: '收盘价', width: 100 },
  { field: 'volume', headerName: '成交量', width: 120, valueFormatter: (p) => formatVolume(p.value) },
  { field: 'amount', headerName: '成交额', width: 130, valueFormatter: (p) => formatAmount(p.value) },
]

const balanceSheetColumns: ColDef[] = [
  { field: 'stock_code', headerName: '股票代码', width: 120, pinned: 'left' },
  { field: 'report_period', headerName: '报告期', width: 120 },
  { field: 'report_date', headerName: '报告日期', width: 130 },
  { field: 'total_assets', headerName: '资产总计', width: 150, valueFormatter: (p) => formatMoney(p.value) },
  { field: 'total_liabilities', headerName: '负债合计', width: 150, valueFormatter: (p) => formatMoney(p.value) },
  { field: 'total_equity', headerName: '所有者权益', width: 150, valueFormatter: (p) => formatMoney(p.value) },
]

const tradeDaysColumns: ColDef[] = [
  { field: 'date', headerName: '日期', width: 150, pinned: 'left' },
  { field: 'is_open', headerName: '是否交易日', width: 120, valueFormatter: (p) => p.value === 1 ? '是' : '否' },
]

const columnDefs = computed<ColDef[]>(() => {
  switch (selectedDataType.value) {
    case 'historical_quote':
      return historicalQuoteColumns
    case 'balance_sheet':
      return balanceSheetColumns
    case 'trade_days':
      return tradeDaysColumns
    default:
      return historicalQuoteColumns
  }
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
    const response = await fetchTypeBrowseDataMock(selectedDataType.value)
    if (response.success && response.data) {
      tableData.value = response.data.results
    }
  } catch (error) {
    console.error('Failed to load data:', error)
  } finally {
    loading.value = false
  }
}

const onDataTypeChange = () => {
  loadData()
}

const onDateRangeChange = () => {
  loadData()
}

onMounted(() => {
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
</style>
