<template>
  <div class="integrity-report-detail">
    <el-card v-loading="loading">
      <template #header>
        <div class="card-header">
          <div>
            <el-button link @click="$router.back()">返回</el-button>
            <span style="margin-left: 16px; font-size: 18px;">{{ report?.name }}</span>
            <el-tag :type="getStatusType(report?.status)" style="margin-left: 8px;">
              {{ report?.status_display }}
            </el-tag>
          </div>
          <el-button
            type="primary"
            @click="generatePlan"
            :disabled="report?.status !== 'COMPLETED' || selectedCount === 0"
            :loading="generating"
          >
            生成采集计划
          </el-button>
        </div>
      </template>

      <div v-if="report?.status === 'GENERATING'" class="generating">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>报告生成中，请稍候...</span>
      </div>

      <div v-else>
        <div class="summary">
          <el-statistic title="缺失项总数" :value="report?.items_count || 0" />
          <el-statistic title="已选择" :value="selectedCount" />
        </div>

        <div class="filter-bar">
          <el-select
            v-model="filterDataType"
            multiple
            collapse-tags
            collapse-tags-tooltip
            placeholder="数据类型"
            clearable
            style="width: 200px;"
            @change="handleFilterChange"
          >
            <el-option
              v-for="(label, value) in DATA_TYPE_DISPLAY"
              :key="value"
              :label="label"
              :value="value"
            />
          </el-select>
          <el-input
            v-model="filterStockCode"
            placeholder="股票代码"
            clearable
            style="width: 150px;"
            @change="handleFilterChange"
          />
          <el-input
            v-model="filterPeriod"
            placeholder="缺失周期"
            clearable
            style="width: 150px;"
            @change="handleFilterChange"
          />
          <el-button @click="resetFilters">重置</el-button>
        </div>

        <div class="toolbar">
          <el-button @click="selectAllFiltered" :disabled="!hasFilteredItems">
            全选当前筛选
          </el-button>
          <el-button @click="deselectAllFiltered" :disabled="!hasFilteredItems">
            取消选择当前筛选
          </el-button>
        </div>

        <ag-grid-vue
          class="ag-theme-quartz"
          :theme="gridTheme"
          :columnDefs="columnDefs"
          :rowData="rowData"
          :defaultColDef="defaultColDef"
          :rowSelection="'multiple'"
          :suppressRowClickSelection="true"
          @grid-ready="onGridReady"
          @selection-changed="onSelectionChanged"
          style="height: 500px; width: 100%; margin-top: 16px;"
        />

        <div class="pagination-container" v-if="totalItems > 0">
          <el-pagination
            v-model:current-page="currentPage"
            v-model:page-size="pageSize"
            :page-sizes="[50, 100, 200, 500]"
            :total="totalItems"
            layout="total, sizes, prev, pager, next, jumper"
            @current-change="handlePageChange"
            @size-change="handleSizeChange"
          />
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, onActivated } from 'vue'
import { useRouter } from 'vue-router'
import { AgGridVue } from 'ag-grid-vue3'
import { themeQuartz } from 'ag-grid-community'
import api from '@/utils/api'
import { Loading } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

import type { GridApi, ColumnApi } from 'ag-grid-community'

const props = defineProps<{ id: string }>()
const router = useRouter()
const report = ref<any>(null)
const loading = ref(true)
const generating = ref(false)
let pollTimer: number | null = null

const gridApi = ref<GridApi | null>(null)
const columnApi = ref<ColumnApi | null>(null)
const rowData = ref<any[]>([])
const currentPage = ref(1)
const pageSize = ref(100)
const totalItems = ref(0)
const selectedCount = ref(0)

const filterDataType = ref<string[]>([])
const filterStockCode = ref('')
const filterPeriod = ref('')

const hasFilteredItems = computed(() => (report.value?.items_count || 0) > 0)

const gridTheme = themeQuartz

const DATA_TYPE_DISPLAY: Record<string, string> = {
  'quote': '最新行情',
  'historical_quote': '历史行情',
  'balance_sheet': '资产负债表',
  'income': '利润表',
  'cash_flow': '现金流量表',
  'dividend': '分红数据',
  'main_business': '主营业务',
  'capital': '股本变动',
  'trade_days': '交易日',
}

const columnDefs = [
  {
    headerName: '选择',
    width: 60,
    pinned: 'left',
    checkboxSelection: true,
    headerCheckboxSelection: true,
    suppressMenu: true,
    suppressMovable: true,
  },
  {
    field: 'data_type',
    headerName: '数据类型',
    width: 130,
    valueFormatter: (params: any) => DATA_TYPE_DISPLAY[params.value] || params.value,
  },
  {
    field: 'stock_code',
    headerName: '股票代码',
    width: 120,
  },
  {
    field: 'period',
    headerName: '缺失周期',
    flex: 1,
  },
]

const defaultColDef = {
  sortable: true,
  resizable: true,
}

const onGridReady = (params: any) => {
  gridApi.value = params.api
  columnApi.value = params.columnApi
  loadItems()
}

const buildQueryParams = () => {
  const params: any = {
    page: currentPage.value,
    page_size: pageSize.value,
  }

  if (filterDataType.value.length > 0) {
    params.data_type = filterDataType.value.join(',')
  }
  if (filterStockCode.value) {
    params.stock_code = filterStockCode.value
  }
  if (filterPeriod.value) {
    params.period = filterPeriod.value
  }

  return params
}

const loadItems = async () => {
  if (!gridApi.value) return

  try {
    const params = buildQueryParams()
    const response = await api.get(`/integrity-reports/${props.id}/`, { params })

    if (response.data.success) {
      report.value = response.data.data
      rowData.value = response.data.data.items || []
      totalItems.value = response.data.data.items_count || 0
      selectedCount.value = response.data.data.selected_count || 0
    }
  } catch (error) {
    console.error('Failed to load items:', error)
    ElMessage.error('加载数据失败')
  }
}

const handleFilterChange = () => {
  currentPage.value = 1
  loadItems()
}

const resetFilters = () => {
  filterDataType.value = []
  filterStockCode.value = ''
  filterPeriod.value = ''
  currentPage.value = 1
  loadItems()
}

const handlePageChange = (page: number) => {
  currentPage.value = page
  loadItems()
}

const handleSizeChange = (size: number) => {
  pageSize.value = size
  currentPage.value = 1
  loadItems()
}

const onSelectionChanged = (event: any) => {
  const selectedRows = gridApi.value?.getSelectedRows() || []
  selectedCount.value = selectedRows.length
}

const fetchReport = async () => {
  try {
    const response = await api.get(`/integrity-reports/${props.id}/`)
    report.value = response.data.data
    return report.value.status
  } catch (error) {
    console.error('Failed to fetch report:', error)
    return null
  }
}

const pollReport = async () => {
  const status = await fetchReport()
  if (status === 'GENERATING') {
    pollTimer = window.setTimeout(pollReport, 3000)
  } else {
    loading.value = false
    loadItems()
  }
}

const selectAllFiltered = async () => {
  try {
    const response = await api.post(`/integrity-reports/${props.id}/items/select-all/`, {
      data_types: filterDataType.value.length > 0 ? filterDataType.value : undefined,
      stock_code: filterStockCode.value || undefined,
      period: filterPeriod.value || undefined,
      selected: true,
    })
    ElMessage.success(`已选择 ${response.data.data.updated_count} 项`)
    loadItems()
  } catch (error) {
    ElMessage.error('操作失败')
  }
}

const deselectAllFiltered = async () => {
  try {
    const response = await api.post(`/integrity-reports/${props.id}/items/select-all/`, {
      data_types: filterDataType.value.length > 0 ? filterDataType.value : undefined,
      stock_code: filterStockCode.value || undefined,
      period: filterPeriod.value || undefined,
      selected: false,
    })
    ElMessage.success(`已取消选择 ${response.data.data.updated_count} 项`)
    loadItems()
  } catch (error) {
    ElMessage.error('操作失败')
  }
}

const generatePlan = async () => {
  generating.value = true
  try {
    const response = await api.post(`/integrity-reports/${props.id}/generate-plan/`)
    ElMessage.success('计划已生成')
    router.push(`/collect-plans/${response.data.data.id}/edit`)
  } catch (error: any) {
    ElMessage.error(error.response?.data?.error || '生成失败')
  } finally {
    generating.value = false
  }
}

const getStatusType = (status: string) => {
  const types: Record<string, string> = {
    'GENERATING': 'warning',
    'COMPLETED': 'success',
    'FAILED': 'danger',
  }
  return types[status] || 'info'
}

onMounted(() => {
  pollReport()
})

onActivated(() => {
  loading.value = true
  pollReport()
})

onUnmounted(() => {
  if (pollTimer) {
    clearTimeout(pollTimer)
  }
})
</script>

<style scoped>
.integrity-report-detail {
  padding: 20px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.summary {
  display: flex;
  gap: 40px;
}
.filter-bar {
  margin-top: 16px;
  display: flex;
  gap: 12px;
  align-items: center;
}
.toolbar {
  margin-top: 12px;
  display: flex;
  gap: 8px;
}
.generating {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 40px;
  color: #909399;
}
.pagination-container {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
</style>
