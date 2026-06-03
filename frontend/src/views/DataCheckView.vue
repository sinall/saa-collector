<template>
  <div class="data-check">
    <CollectorFilterPanel
      ref="filterPanelRef"
      query-button-text="检查"
      :loading="loading"
      :show-report-types="false"
      visibility-context="data_check"
      @query="handleQuery"
      @data-type-change="handleDataTypeChange"
    >
      <template #extra-filters>
        <section class="filter-section">
          <div class="section-header">
            <h4>频度</h4>
          </div>
          <div class="section-content">
            <select v-model="selectedFrequency">
              <option label="日度" value="daily" />
              <option label="周度" value="weekly" />
              <option label="月度" value="monthly" />
              <option label="季度" value="quarterly" />
              <option label="年度" value="yearly" />
            </select>
          </div>
        </section>
      </template>
    </CollectorFilterPanel>

    <main class="results-panel">
      <div class="action-bar">
        <el-button
          type="primary"
          :loading="generating"
          @click="handleGenerateReport"
        >
          生成报告
        </el-button>
      </div>

      <div v-if="loading" class="loading-state">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>检查中...</span>
      </div>

      <div v-else-if="error" class="error-message">
        <el-alert :title="error" type="error" show-icon />
      </div>

      <template v-else-if="hasChecked">
        <el-card class="summary-card">
          <template #header>
            <div class="card-header">
              <span>检查结果汇总</span>
              <span class="total-info">
                共 <strong>{{ totalExpected }}</strong> 条，缺失 <strong :class="{ 'text-danger': totalMissing > 0 }">{{ totalMissing }}</strong> 条
              </span>
            </div>
          </template>
          <el-table :data="summary" stripe style="width: 100%">
            <el-table-column prop="period" label="月份" width="120" />
            <el-table-column prop="expected" label="应有" width="100" />
            <el-table-column prop="missing" label="缺失" width="100">
              <template #default="{ row }">
                <span :class="{ 'text-danger': row.missing > 0, 'text-success': row.missing === 0 }">
                  {{ row.missing }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <el-tag v-if="row.missing === 0" type="success" size="small">完整</el-tag>
                <el-tag v-else type="danger" size="small">缺失</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="完成度">
              <template #default="{ row }">
                <el-progress
                  :percentage="row.expected > 0 ? Math.round((row.expected - row.missing) / row.expected * 100) : 100"
                  :status="row.missing === 0 ? 'success' : ''"
                />
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <el-card v-if="missingRecords.length > 0" class="table-card">
          <template #header>
            <span>缺失记录详情 ({{ missingRecords.length }} 条)</span>
          </template>
          <ag-grid-vue
            class="ag-theme-quartz"
            :theme="gridTheme"
            :columnDefs="columnDefs"
            :rowData="missingRecords"
            :pagination="true"
            :paginationPageSize="100"
            :defaultColDef="defaultColDef"
            @grid-ready="onGridReady"
            style="height: 400px; width: 100%"
          />
        </el-card>
      </template>

      <el-empty v-else description="请选择筛选条件后点击检查" />
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { AgGridVue } from 'ag-grid-vue3'
import { themeQuartz, type ColDef } from 'ag-grid-community'
import { Loading } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import CollectorFilterPanel from '@/components/CollectorFilterPanel.vue'
import { useDataTypes, isDataTypeVisible } from '@/composables/useDataTypes'
import {
  checkDataCompleteness,
  createIntegrityReport,
  type MissingDataRecord,
  type SummaryItem,
  type IntegrityReportCreateParams
} from '@/utils/api'
import { ensureAgGridRegistered } from '@/utils/ag-grid'

ensureAgGridRegistered()

const router = useRouter()
const { getConfig, loadDataTypes } = useDataTypes()
const filterPanelRef = ref<InstanceType<typeof CollectorFilterPanel> | null>(null)
const loading = ref(false)
const generating = ref(false)
const error = ref('')
const hasChecked = ref(false)
const selectedFrequency = ref('monthly')
const totalMissing = ref(0)
const totalExpected = ref(0)
const summary = ref<SummaryItem[]>([])
const missingRecords = ref<MissingDataRecord[]>([])
const gridApi = ref<any>(null)
const lastQueryParams = ref<any>(null)

const columnDefs: ColDef[] = [
  {
    field: 'symbol',
    headerName: '股票代码',
    width: 120,
    pinned: 'left',
    filter: true
  },
  {
    field: 'name',
    headerName: '名称',
    width: 150,
    filter: true
  },
  {
    field: 'date',
    headerName: '日期',
    width: 120,
    sortable: true
  },
  {
    field: 'data_type',
    headerName: '数据类型',
    width: 150,
    filter: true
  },
  {
    field: 'frequency',
    headerName: '频度',
    width: 100,
    filter: true
  },
]

const defaultColDef = {
  sortable: true,
  resizable: true,
}

const gridTheme = themeQuartz

const onGridReady = (params: any) => {
  gridApi.value = params.api
  if (missingRecords.value.length > 0) {
    params.api.setGridOption('rowData', missingRecords.value)
  }
}

const handleDataTypeChange = (dataType: string) => {
  const statementTypes = ['balance_sheet', 'income', 'cash_flow', 'dividend']
  if (statementTypes.includes(dataType)) {
    selectedFrequency.value = 'quarterly'
  }
}

const handleQuery = async (params: any) => {
  lastQueryParams.value = params
  loading.value = true
  error.value = ''
  hasChecked.value = false
  missingRecords.value = []
  totalMissing.value = 0
  totalExpected.value = 0
  summary.value = []

  try {
    const response = await checkDataCompleteness({
      data_type: params.data_type,
      symbols: params.symbols,
      start_date: params.start_date,
      end_date: params.end_date,
      frequency: selectedFrequency.value,
      page: 1,
      page_size: 1000
    })

    if (response.success && response.data) {
      totalMissing.value = response.data.total_missing
      missingRecords.value = response.data.missing_records
      summary.value = response.data.summary
      totalExpected.value = response.data.summary.reduce((sum, item) => sum + item.expected, 0)
      hasChecked.value = true

      if (totalMissing.value > 0) {
        ElMessage.warning(`发现 ${totalMissing.value} 条数据缺失`)
      } else {
        ElMessage.success('数据完整，无缺失')
      }
    } else {
      error.value = response.error || '检查失败'
      ElMessage.error(error.value)
    }
  } finally {
    loading.value = false
  }
}

const handleGenerateReport = async () => {
  const params = lastQueryParams.value
  if (!params || !params.data_type) {
    ElMessage.warning('请先进行数据检查')
    return
  }

  await loadDataTypes()
  if (!isDataTypeVisible(getConfig(params.data_type), 'integrity_report')) {
    ElMessage.warning('该数据类型不支持生成完整性报告')
    return
  }

  generating.value = true
  try {
    const data: IntegrityReportCreateParams = {
      name: generateReportName(params),
      stock_scope: params.stock_mode === 'all' || !params.symbols || params.symbols.length === 0 ? 'ALL' : 'SELECTED',
      stock_codes: params.symbols || [],
      data_types: [params.data_type],
      frequency: selectedFrequency.value,
      date_start: params.start_date || '2009-01-01',
      date_end: params.end_date || new Date().toISOString().split('T')[0]
    }

    const response = await createIntegrityReport(data)
    if (response.success && response.data) {
      ElMessage.success('报告创建成功，正在生成中...')
      router.push(`/integrity-reports/${response.data.id}`)
    } else {
      ElMessage.error(response.error || '创建报告失败')
    }
  } catch (error: any) {
    ElMessage.error('创建报告失败')
  } finally {
    generating.value = false
  }
}

const generateReportName = (params: any) => {
  const typeNames: Record<string, string> = {
    'trade_days': '交易日',
    'stock_info': '股票基本信息',
    'quote': '最新行情',
    'historical_quote': '历史行情',
    'balance_sheet': '资产负债表',
    'income': '利润表',
    'cash_flow': '现金流量表',
    'dividend': '分红数据',
    'capital': '股本变动',
    'valuation_board': '板块估值',
    'valuation_industry': '行业估值',
    'main_business': '主营业务'
  }

  const typeLabel = typeNames[params.data_type] || params.data_type

  const freqNames: Record<string, string> = {
    'daily': '日度',
    'weekly': '周度',
    'monthly': '月度',
    'quarterly': '季度',
    'yearly': '年度'
  }
  const freqLabel = freqNames[selectedFrequency.value] || selectedFrequency.value

  const date = new Date().toISOString().split('T')[0]
  return `${date} ${typeLabel}${freqLabel}完整性检查`
}

onMounted(() => {
  loadDataTypes()
})
</script>

<style scoped>
.data-check {
  display: flex;
  min-height: calc(100vh - 120px);
}

.results-panel {
  flex: 1;
  padding: 1rem;
  background: #f5f7fa;
  overflow: auto;
}

.action-bar {
  margin-bottom: 1rem;
  display: flex;
  justify-content: flex-end;
}

.loading-state {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  height: 300px;
  gap: 1rem;
  color: #666;
}

.loading-state .el-icon {
  font-size: 2rem;
  margin-right: 0.5rem;
  animation: spin 1s linear infinite;
}

.summary-card {
  margin-bottom: 1rem;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.total-info {
  font-size: 14px;
  color: #666;
}

.text-danger {
  color: #f56c6c;
}

.text-success {
  color: #67c23a;
}

.table-card {
  margin-top: 1rem;
}
</style>
