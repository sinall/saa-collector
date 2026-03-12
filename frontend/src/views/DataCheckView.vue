<template>
  <div class="data-check">
    <CollectorFilterPanel
      query-button-text="检查"
      :loading="loading"
      :show-report-types="false"
      @query="handleQuery"
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
            </select>
          </div>
        </section>
      </template>
    </CollectorFilterPanel>

    <main class="results-panel">
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
            <span>缺失记录详情</span>
          </template>
          <ag-grid-vue
            class="ag-theme-alpine"
            :column-defs="columnDefs"
            :row-data="missingRecords"
            :pagination="true"
            :pagination-page-size="100"
            :default-col-def="defaultColDef"
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
import { ref, computed } from 'vue'
import { AgGridVue } from 'ag-grid-vue3'
import 'ag-grid-community/styles/ag-grid.css'
import 'ag-grid-community/styles/ag-theme-alpine.css'
import { Loading } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import CollectorFilterPanel from '@/components/CollectorFilterPanel.vue'
import { checkDataCompleteness, type MissingDataRecord, type SummaryItem } from '@/utils/api'

const loading = ref(false)
const error = ref('')
const hasChecked = ref(false)
const selectedFrequency = ref('monthly')
const totalMissing = ref(0)
const totalExpected = ref(0)
const summary = ref<SummaryItem[]>([])
const missingRecords = ref<MissingDataRecord[]>([])
const gridApi = ref<any>(null)

const columnDefs = [
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

const onGridReady = (params: any) => {
  gridApi.value = params.api
}

const handleQuery = async (params: any) => {
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