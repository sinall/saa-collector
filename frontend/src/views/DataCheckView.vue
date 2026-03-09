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
        <el-card v-if="totalMissing > 0" class="summary-card">
          <div class="summary-info">
            <el-icon><WarningFilled /></el-icon>
            <span>共发现 <strong>{{ totalMissing }}</strong> 条数据缺失</span>
          </div>
        </el-card>
        
        <el-card v-if="missingRecords.length > 0" class="table-card">
          <ag-grid-vue
            class="ag-theme-alpine"
            :column-defs="columnDefs"
            :row-data="missingRecords"
            :pagination="true"
            :pagination-page-size="100"
            :default-col-def="defaultColDef"
            @grid-ready="onGridReady"
            style="height: 600px; width: 100%"
          />
        </el-card>
        
        <el-empty v-else-if="hasChecked && totalMissing === 0" description="数据完整，无缺失" />
      </template>
      
      <el-empty v-else description="请选择筛选条件后点击检查" />
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { AgGridVue } from 'ag-grid-vue3'
import 'ag-grid-community/styles/ag-grid.css'
import 'ag-grid-community/styles/ag-theme-alpine.css'
import { Loading, WarningFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import CollectorFilterPanel from '@/components/CollectorFilterPanel.vue'
import { checkDataCompleteness, type MissingDataRecord } from '@/utils/api'

const loading = ref(false)
const error = ref('')
const hasChecked = ref(false)
const selectedFrequency = ref('monthly')
const totalMissing = ref(0)
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

</style>