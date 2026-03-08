<template>
  <div class="collect">
    <CollectorFilterPanel
      ref="filterPanel"
      query-button-text="开始采集"
      :loading="collecting"
      :show-report-types="true"
      @query="handleCollect"
    />
    
    <main class="results-panel">
      <el-card class="jobs-card">
        <template #header>
          <div class="card-header">
            <span>采集任务列表</span>
            <el-button size="small" @click="refreshJobs">
              <el-icon><Refresh /></el-icon>
              刷新
            </el-button>
          </div>
        </template>
        
        <el-table :data="jobs" stripe v-loading="loadingJobs">
          <el-table-column prop="data_type_display" label="数据类型" width="120" />
          <el-table-column prop="status_display" label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="getStatusType(row.status)">{{ row.status_display }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="创建时间" width="180">
            <template #default="{ row }">
              {{ formatDateTime(row.created_at) }}
            </template>
          </el-table-column>
          <el-table-column prop="start_time" label="开始时间" width="180">
            <template #default="{ row }">
              {{ row.start_time ? formatDateTime(row.start_time) : '-' }}
            </template>
          </el-table-column>
          <el-table-column prop="end_time" label="结束时间" width="180">
            <template #default="{ row }">
              {{ row.end_time ? formatDateTime(row.end_time) : '-' }}
            </template>
          </el-table-column>
          <el-table-column prop="message" label="消息" show-overflow-tooltip />
        </el-table>

        <div v-if="totalJobs > pageSize" class="pagination-wrapper">
          <el-pagination
            v-model:current-page="currentPage"
            v-model:page-size="pageSize"
            :total="totalJobs"
            :page-sizes="[10, 20, 50]"
            layout="total, sizes, prev, pager, next"
            @size-change="refreshJobs"
            @current-change="refreshJobs"
          />
        </div>
      </el-card>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import CollectorFilterPanel from '@/components/CollectorFilterPanel.vue'
import {
  fetchCollectJobs,
  collectStockInfo,
  collectQuotes,
  collectHistoricalQuotes,
  collectStatements,
  collectCapital,
  collectValuation,
  collectMainBusiness,
  type CollectJob,
} from '@/utils/api'

interface FilterParams {
  data_type: string
  symbols: string[]
  start_date?: string
  end_date?: string
  report_types?: string[]
}

const jobs = ref<CollectJob[]>([])
const loadingJobs = ref(false)
const collecting = ref(false)
const currentPage = ref(1)
const pageSize = ref(20)
const totalJobs = ref(0)

const refreshJobs = async () => {
  loadingJobs.value = true
  try {
    const response = await fetchCollectJobs({
      page: currentPage.value,
      page_size: pageSize.value,
    })
    if (response.success && response.data) {
      jobs.value = response.data.results || []
      totalJobs.value = response.data.pagination?.total || 0
    }
  } catch (error) {
    console.error('Failed to load jobs:', error)
  } finally {
    loadingJobs.value = false
  }
}

const handleCollect = async (params: FilterParams) => {
  collecting.value = true
  
  try {
    const symbols = params.symbols.length > 0 ? params.symbols : undefined
    const collectParams = {
      symbols,
      start_date: params.start_date,
      end_date: params.end_date,
      report_types: params.report_types,
    }

    let response
    switch (params.data_type) {
      case 'stock_info':
        response = await collectStockInfo(symbols)
        break
      case 'quote':
        response = await collectQuotes(symbols)
        break
      case 'historical_quote':
        response = await collectHistoricalQuotes(collectParams)
        break
      case 'balance_sheet':
      case 'income':
      case 'cash_flow':
      case 'dividend':
        response = await collectStatements(collectParams)
        break
      case 'capital':
        response = await collectCapital(collectParams)
        break
      case 'valuation':
        response = await collectValuation(symbols)
        break
      case 'main_business':
        response = await collectMainBusiness(collectParams)
        break
      default:
        throw new Error('Unknown data type')
    }

    if (response.success) {
      ElMessage.success('采集任务已创建')
      refreshJobs()
    } else {
      ElMessage.error(response.error || '创建采集任务失败')
    }
  } catch (error) {
    console.error('Failed to start collect:', error)
    ElMessage.error('创建采集任务失败')
  } finally {
    collecting.value = false
  }
}

const formatDateTime = (dateStr: string): string => {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN')
}

const getStatusType = (status: string): string => {
  const types: Record<string, string> = {
    'PENDING': 'info',
    'RUNNING': 'warning',
    'SUCCESS': 'success',
    'FAILED': 'danger',
  }
  return types[status] || 'info'
}

onMounted(() => {
  refreshJobs()
})
</script>

<style scoped>
.collect {
  display: flex;
  min-height: calc(100vh - 120px);
}

.results-panel {
  flex: 1;
  padding: 1rem;
  background: #f5f7fa;
  overflow: auto;
}

.jobs-card {
  height: fit-content;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.pagination-wrapper {
  margin-top: 1rem;
  display: flex;
  justify-content: flex-end;
}
</style>
