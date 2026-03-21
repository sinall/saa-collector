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
          <div>
            <el-button
              @click="refreshReport"
              :disabled="report?.status === 'GENERATING'"
              :loading="refreshing"
            >
              刷新报告
            </el-button>
            <el-button
              type="primary"
              @click="generatePlan"
              :disabled="report?.status !== 'COMPLETED' || selectedCount === 0"
              :loading="generating"
            >
              生成采集计划
            </el-button>
          </div>
        </div>
      </template>

      <div v-if="report?.status === 'GENERATING'" class="generating">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>报告生成中，请稍候...</span>
      </div>

      <div v-else>
        <div class="heatmap-section">
          <div v-loading="heatmapLoading" class="heatmap-chart" ref="heatmapChartRef"></div>
        </div>

        <div class="filter-bar">
          <el-select
            v-model="filterStatus"
            placeholder="修复状态"
            clearable
            style="width: 120px;"
            @change="handleFilterChange"
          >
            <el-option label="待修复" value="PENDING" />
            <el-option label="已修复" value="FIXED" />
          </el-select>
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
          <div class="filter-bar-actions">
            <el-button size="small" @click="selectAllFiltered" :disabled="!hasFilteredItems">
              全选筛选
            </el-button>
            <el-button size="small" @click="deselectAllFiltered" :disabled="!hasFilteredItems">
              取消全选
            </el-button>
          </div>
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
          <span class="selection-info">已选择 {{ selectedCount }} 项</span>
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
import * as echarts from 'echarts'
import {
  fetchIntegrityReportDetailMock,
  fetchIntegrityReportHeatmapMock,
  selectItemsMock,
  refreshReportMock,
  generatePlanMock,
  type IntegrityReportItem
} from '@/utils/api'
import { Loading } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import type { GridApi } from 'ag-grid-community'

const props = defineProps<{ id: string }>()
const router = useRouter()
const report = ref<any>(null)
const loading = ref(true)
const generating = ref(false)
let pollTimer: number | null = null

const heatmapChartRef = ref<HTMLElement>()
const heatmapLoading = ref(false)
let heatmapChartInstance: echarts.ECharts | null = null

const gridApi = ref<GridApi | null>(null)
const rowData = ref<IntegrityReportItem[]>([])
const currentPage = ref(1)
const pageSize = ref(100)
const totalItems = ref(0)
const selectedCount = ref(0)

const filterDataType = ref<string[]>([])
const filterStockCode = ref('')
const filterPeriod = ref('')
const filterStatus = ref('')

const hasFilteredItems = computed(() => (report.value?.items_count || 0) > 0)

const gridTheme = themeQuartz

const refreshing = ref(false)

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
    pinned: 'left' as const,
    checkboxSelection: true,
    headerCheckboxSelection: true,
    suppressMenu: true,
    suppressMovable: true,
  },
  {
    field: 'status_display',
    headerName: '状态',
    width: 120,
    cellRenderer: (params: any) => {
      const status = params.data?.status
      const icon = status === 'FIXED' ? '✓' : '⏳'
      const text = status === 'FIXED' ? '已修复' : '待修复'
      const color = status === 'FIXED' ? '#67c23a' : '#e6a23c'
      return `<span style="color: ${color}; font-weight: 500;">${icon} ${text}</span>`
    },
  },
  {
    field: 'data_type',
    headerName: '数据类型',
    width: 150,
    cellRenderer: (params: any) => {
      const typeLabels: Record<string, string> = {
        'quote': '最新行情',
        'historical_quote': '历史行情',
        'balance_sheet': '资产负债表',
        'income': '利润表',
        'cash_flow': '现金流量表',
        'dividend': '分红数据',
        'main_business': '主营业务',
        'capital': '股本变动',
        'trade_days': '交易日',
        'valuation': '估值数据',
      }
      
      const typeColors: Record<string, string> = {
        'quote': '#409eff',
        'historical_quote': '#67c23a',
        'balance_sheet': '#e6a23c',
        'income': '#f56c6c',
        'cash_flow': '#909399',
        'dividend': '#b37feb',
        'main_business': '#ff85c0',
        'capital': '#87e8de',
        'trade_days': '#ffd666',
        'valuation': '#ff9c6e',
      }
      
      const value = params.value ?? ''
      const label = typeLabels[value] || value
      const color = typeColors[value] || '#909399'
      
      return `<span style="
        background: ${color}20;
        color: ${color};
        padding: 4px 8px;
        border-radius: 4px;
        font-size: 12px;
        font-weight: 500;
      ">${label}</span>`
    },
  },
  {
    field: 'stock_code',
    headerName: '股票代码',
    width: 120,
    cellRenderer: (params: any) => {
      const code = params.value ?? ''
      return `<a href="/stock/${code}" style="color: #409eff; text-decoration: none;">${code}</a>`
    },
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
  loadItems()
}

const buildQueryParams = () => {
  const params: any = {
    page: currentPage.value,
    page_size: pageSize.value,
  }

  if (filterStatus.value) {
    params.status = filterStatus.value
  }
  if (filterDataType.value && filterDataType.value.length > 0) {
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
    const response = await fetchIntegrityReportDetailMock(parseInt(props.id), params)

    if (response.success && response.data) {
      report.value = response.data.report
      rowData.value = response.data.items || []
      totalItems.value = response.data.items_count || 0
      selectedCount.value = response.data.selected_count || 0
    } else {
      ElMessage.error(response.error || '加载数据失败')
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
  filterStatus.value = ''
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
    const response = await fetchIntegrityReportDetailMock(parseInt(props.id))
    if (response.success && response.data) {
      report.value = response.data.report
      return response.data.report.status
    }
    return null
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
    const response = await selectItemsMock(parseInt(props.id), {
      data_types: filterDataType.value.length > 0 ? filterDataType.value : undefined,
      stock_code: filterStockCode.value || undefined,
      period: filterPeriod.value || undefined,
      status: filterStatus.value || undefined,
      selected: true,
    })
    if (response.success && response.data) {
      ElMessage.success(`已选择 ${response.data.updated_count} 项`)
      loadItems()
    } else {
      ElMessage.error(response.error || '操作失败')
    }
  } catch (error) {
    ElMessage.error('操作失败')
  }
}

const deselectAllFiltered = async () => {
  try {
    const response = await selectItemsMock(parseInt(props.id), {
      data_types: filterDataType.value.length > 0 ? filterDataType.value : undefined,
      stock_code: filterStockCode.value || undefined,
      period: filterPeriod.value || undefined,
      status: filterStatus.value || undefined,
      selected: false,
    })
    if (response.success && response.data) {
      ElMessage.success(`已取消选择 ${response.data.updated_count} 项`)
      loadItems()
    } else {
      ElMessage.error(response.error || '操作失败')
    }
  } catch (error) {
    ElMessage.error('操作失败')
  }
}

const refreshReport = async () => {
  refreshing.value = true
  try {
    const response = await refreshReportMock(parseInt(props.id))
    if (response.success) {
      ElMessage.success('报告刷新已开始')
      loading.value = true
      pollReport()
    } else {
      ElMessage.error(response.error || '刷新失败')
    }
  } catch (error: any) {
    ElMessage.error('刷新失败')
  } finally {
    refreshing.value = false
  }
}

const generatePlan = async () => {
  try {
    await ElMessageBox.confirm(
      `确定要生成采集计划吗？已选择 ${selectedCount.value} 项缺失数据。`,
      '确认生成',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'info',
      }
    )
    
    generating.value = true
    const response = await generatePlanMock(parseInt(props.id))
    
    if (response.success && response.data) {
      ElMessage.success('计划已生成')
      router.push(`/collect-plans/${response.data.id}/edit`)
    } else {
      ElMessage.error(response.error || '生成失败')
    }
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error('生成失败')
    }
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

const loadHeatmapData = async () => {
  if (!heatmapChartRef.value) return
  
  heatmapLoading.value = true
  try {
    const response = await fetchIntegrityReportHeatmapMock(parseInt(props.id))
    if (response.success && response.data) {
      renderHeatmap(response.data)
    }
  } catch (error) {
    console.error('Failed to load heatmap data:', error)
  } finally {
    heatmapLoading.value = false
  }
}

const renderHeatmap = (data: { data_types: { key: string; label: string }[]; periods: string[]; matrix: Record<string, number[]> }) => {
  if (!heatmapChartRef.value) return

  if (!heatmapChartInstance) {
    heatmapChartInstance = echarts.init(heatmapChartRef.value)
  }

  const { data_types, periods, matrix } = data

  const chartData: [number, number, number][] = []
  data_types.forEach((dt, yIndex) => {
    const values = matrix[dt.key] || []
    values.forEach((value, xIndex) => {
      chartData.push([xIndex, yIndex, value])
    })
  })

  const maxValue = Math.max(...chartData.map(d => d[2]), 1)

  const option: echarts.EChartsOption = {
    tooltip: {
      position: 'top',
      formatter: (params: any) => {
        const [xIndex, yIndex, value] = params.data
        const period = periods[xIndex] ?? ''
        const dataType = data_types[yIndex]?.label ?? ''
        return `${period}<br/>${dataType}: ${value} 项缺失`
      },
    },
    grid: {
      top: 20,
      bottom: 60,
      left: 100,
      right: 30,
    },
    xAxis: {
      type: 'category',
      data: periods,
      axisLabel: {
        rotate: 45,
        fontSize: 11,
      },
      splitArea: { show: false },
    },
    yAxis: {
      type: 'category',
      data: data_types.map(dt => dt.label),
      splitArea: { show: false },
    },
    visualMap: {
      min: 0,
      max: maxValue,
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      inRange: {
        color: ['#f0f9eb', '#e6f7d0', '#bae637', '#52c41a', '#237804'],
      },
      text: ['多', '少'],
    },
    series: [
      {
        type: 'heatmap',
        data: chartData,
        label: { show: false },
        emphasis: {
          itemStyle: {
            shadowBlur: 10,
            shadowColor: 'rgba(0, 0, 0, 0.5)',
          },
        },
      },
    ],
  }

  heatmapChartInstance.setOption(option, true)
}

const handleResize = () => {
  heatmapChartInstance?.resize()
}

onMounted(() => {
  pollReport()
  loadHeatmapData()
  window.addEventListener('resize', handleResize)
})

onActivated(() => {
  loading.value = true
  pollReport()
})

onUnmounted(() => {
  if (pollTimer) {
    clearTimeout(pollTimer)
  }
  window.removeEventListener('resize', handleResize)
  heatmapChartInstance?.dispose()
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
.heatmap-section {
  background: #fafafa;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
}
.heatmap-chart {
  width: 100%;
  height: 250px;
}
.filter-bar {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}
.filter-bar-actions {
  margin-left: auto;
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
  align-items: center;
  gap: 16px;
}
.selection-info {
  color: #606266;
  font-size: 14px;
}

:deep(.ag-theme-quartz) {
  --ag-header-background-color: #f5f7fa;
  --ag-header-foreground-color: #333;
  --ag-border-color: #e4e7ed;
}

:deep(.ag-row-selected) {
  background-color: #ecf5ff !important;
}

:deep(.ag-row-hover) {
  background-color: #f5f7fa !important;
}
</style>
