<template>
  <div class="integrity-report-detail">
    <el-card v-loading="loading">
      <template #header>
        <div class="card-header">
          <div>
            <el-button link @click="$router.back()">返回</el-button>
            <span style="margin-left: 16px; font-size: 16px;">{{ report?.name }}</span>
            <el-tag v-if="report" :type="getStatusType(report.status)" style="margin-left: 8px;">
              {{ report.status_display }}
            </el-tag>
          </div>
          <div>
            <el-button
              type="primary"
              @click="handleGeneratePlan"
              :disabled="report?.status === 'GENERATING'"
              :loading="generating"
            >
              生成采集计划
            </el-button>
            <el-button
              @click="refreshReportAction"
              :disabled="report?.status === 'GENERATING'"
              :loading="refreshing"
            >
              刷新报告
            </el-button>
          </div>
        </div>
      </template>

      <div v-if="report?.status === 'GENERATING'" class="generating">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>报告生成中，请稍候...</span>
      </div>

      <template v-else>
        <el-card v-if="report" class="filter-info-card">
          <template #header>
            <span>数据筛选条件</span>
          </template>
          <el-descriptions :column="4" border size="small">
            <el-descriptions-item label="数据类型">
              <el-tag v-for="dt in visibleReportDataTypes" :key="dt" size="small" style="margin-right: 4px;">
                {{ getDataTypeLabel(dt) }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="频度">{{ getFrequencyLabel(report.frequency) }}</el-descriptions-item>
            <el-descriptions-item label="股票范围">
              {{ report.stock_scope === 'ALL' ? '全部股票' : `选定股票 (${report.stock_codes?.length || 0} 只)` }}
            </el-descriptions-item>
            <el-descriptions-item label="时间范围">{{ report.date_start }} 至 {{ report.date_end }}</el-descriptions-item>
          </el-descriptions>
        </el-card>

        <el-card class="heatmap-card">
          <CompletenessHeatmap
            :external-data="heatmapData"
            :hide-frequency-selector="true"
            :view-frequency="report?.frequency || 'monthly'"
          />
        </el-card>

        <el-card class="data-card">
          <div class="content-layout">
            <div class="tree-panel">
              <IntegrityReportTreeFilter
                ref="treeFilterRef"
                :report-id="parseInt(props.id)"
                @filter-change="handleFilterChange"
              />
            </div>
            <div class="right-content">
              <ag-grid-vue
                class="ag-theme-quartz"
                :theme="gridTheme"
                :columnDefs="columnDefs"
                :rowData="rowData"
                :defaultColDef="defaultColDef"
                @grid-ready="onGridReady"
                style="height: 100%; width: 100%;"
              />

              <div class="pagination-container" v-if="totalItems > 0">
                <el-pagination
                  v-model:current-page="currentPage"
                  v-model:page-size="pageSize"
                  :page-sizes="[50, 100, 200, 500]"
                  :total="totalItems"
                  layout="total, sizes, prev, pager, next"
                  @current-change="handlePageChange"
                  @size-change="handleSizeChange"
                />
              </div>
            </div>
          </div>
        </el-card>
      </template>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, onActivated, computed } from 'vue'
import { useRouter } from 'vue-router'
import { AgGridVue } from 'ag-grid-vue3'
import { themeQuartz } from 'ag-grid-community'
import {
  fetchIntegrityReportDetail,
  refreshReport,
  fetchIntegrityReportHeatmap,
  generatePlan,
  type IntegrityReportItem,
  type IntegrityReportHeatmapData
} from '@/utils/api'
import { Loading } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import CompletenessHeatmap from '@/components/CompletenessHeatmap.vue'
import IntegrityReportTreeFilter, { type FilterParams } from '@/components/IntegrityReportTreeFilter.vue'
import { useDataTypes, isDataTypeVisible } from '@/composables/useDataTypes'

import type { GridApi } from 'ag-grid-community'

const props = defineProps<{ id: string }>()
const router = useRouter()
const { getConfig, loadDataTypes } = useDataTypes()
const report = ref<any>(null)
const loading = ref(true)
const generating = ref(false)
const refreshing = ref(false)
let pollTimer: number | null = null

const treeFilterRef = ref<InstanceType<typeof IntegrityReportTreeFilter> | null>(null)
const heatmapData = ref<IntegrityReportHeatmapData | null>(null)
const gridApi = ref<GridApi | null>(null)
const rowData = ref<IntegrityReportItem[]>([])
const currentPage = ref(1)
const pageSize = ref(100)
const totalItems = ref(0)

const currentFilter = ref<FilterParams>({
  dataTypes: [],
  periods: [],
  status: '',
  stockCode: ''
})

const visibleReportDataTypes = computed(() =>
  (report.value?.data_types || []).filter((dataType: string) => {
    const config = getConfig(dataType)
    return isDataTypeVisible(config, 'integrity_report')
  })
)

const gridTheme = themeQuartz

const columnDefs = [
  {
    field: 'status_display',
    headerName: '状态',
    width: 100,
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
    width: 140,
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
        'valuation_board': '板块估值',
        'valuation_industry': '行业估值',
      }
      const typeColors: Record<string, string> = {
        'quote': '#409eff',
        'historical_quote': '#67c23a',
        'balance_sheet': '#e6a23c',
        'income': '#f56c6c',
        'cash_flow': '#909399',
        'dividend': '#b37beb',
        'main_business': '#ff85c0',
        'capital': '#87e8de',
        'trade_days': '#ffd666',
        'valuation_board': '#ff9c6e',
        'valuation_industry': '#ffa940',
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
}

const buildQueryParams = () => {
  const params: any = {
    page: currentPage.value,
    page_size: pageSize.value,
  }
  if (currentFilter.value.status) {
    params.status = currentFilter.value.status
  }
  if (currentFilter.value.stockCode) {
    params.stock_code = currentFilter.value.stockCode
  }
  if (currentFilter.value.dataTypes.length > 0) {
    params.data_type = currentFilter.value.dataTypes.join(',')
  }
  if (currentFilter.value.periods.length > 0) {
    params.period = currentFilter.value.periods.join(',')
  }
  return params
}

const loadItems = async () => {
  if (!gridApi.value) return
  try {
    const params = buildQueryParams()
    const response = await fetchIntegrityReportDetail(parseInt(props.id), params)
    if (response.success && response.data) {
      report.value = response.data
      rowData.value = response.data.items || []
      totalItems.value = response.data.items_count || 0
    } else {
      ElMessage.error(response.error || '加载数据失败')
    }
  } catch (error) {
    console.error('Failed to load items:', error)
    ElMessage.error('加载数据失败')
  }
}

const handleFilterChange = (filterParams: FilterParams) => {
  currentFilter.value = filterParams
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

const fetchReport = async () => {
  try {
    const response = await fetchIntegrityReportDetail(parseInt(props.id))
    if (response.success && response.data) {
      report.value = response.data
      return response.data.status
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
    loadHeatmapData()
  }
}

const refreshReportAction = async () => {
  refreshing.value = true
  try {
    const response = await refreshReport(parseInt(props.id))
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





const handleGeneratePlan = async () => {
  try {
    await ElMessageBox.confirm(
      '确定要生成采集计划吗？将基于报告的所有缺失项生成任务。',
      '确认生成',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'info',
      }
    )
    generating.value = true

    const response = await generatePlan(parseInt(props.id))

    if (response.success && response.data) {
      ElMessage.success(`采集计划已生成`)
      router.push(`/collect-plans/${response.data.id}`)
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

const getDataTypeLabel = (dataType: string) => {
  const labels: Record<string, string> = {
    'trade_days': '交易日',
    'quote': '最新行情',
    'historical_quote': '历史行情',
    'balance_sheet': '资产负债表',
    'income': '利润表',
    'cash_flow': '现金流量表',
    'dividend': '分红数据',
    'capital': '股本变动',
    'valuation_board': '板块估值',
    'valuation_industry': '行业估值',
    'main_business': '主营业务',
  }
  return labels[dataType] || dataType
}

const getFrequencyLabel = (frequency: string) => {
  const labels: Record<string, string> = {
    'daily': '日度',
    'weekly': '周度',
    'monthly': '月度',
    'quarterly': '季度',
    'yearly': '年度',
  }
  return labels[frequency] || frequency
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
  try {
    const response = await fetchIntegrityReportHeatmap(parseInt(props.id))
    if (response.success && response.data) {
      heatmapData.value = response.data
    }
  } catch (error) {
    console.error('Failed to load heatmap data:', error)
  }
}

onMounted(() => {
  loadDataTypes()
  pollReport()
  loadHeatmapData()
})

onActivated(() => {
  loadDataTypes()
  loading.value = true
  pollReport()
  loadHeatmapData()
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

.filter-info-card {
  margin-bottom: 16px;
}

.filter-info-card :deep(.el-card__body) {
  padding: 12px 16px;
}

.heatmap-card {
  margin-bottom: 16px;
}

.data-card :deep(.el-card__body) {
  padding: 16px;
  height: calc(100vh - 380px);
}

.data-card {
  background: #fff;
}

.content-layout {
  display: flex;
  gap: 16px;
  height: 100%;
}

.tree-panel {
  width: 280px;
  flex-shrink: 0;
}

.right-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.pagination-container {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
  align-items: center;
}

.generating {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
  color: #909399;
}

.generating .el-icon {
  font-size: 24px;
  margin-right: 8px;
}

:deep(.ag-theme-quartz) {
  --ag-header-background-color: #f5f7fa;
  --ag-header-foreground-color: #333;
  --ag-border-color: #e4e7ed;
}
</style>
