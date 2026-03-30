<template>
  <div class="collect-plan-detail">
    <el-card v-loading="loading">
      <template #header>
        <div class="card-header">
          <div>
            <el-button link @click="$router.back()">返回</el-button>
            <span style="margin-left: 16px; font-size: 18px;">{{ plan?.name }}</span>
            <el-tag :type="getStatusType(plan?.status)" style="margin-left: 8px;">
              {{ plan?.status_display }}
            </el-tag>
          </div>
          <div>
            <el-button 
              v-if="plan?.status === 'PENDING'"
              @click="$router.push(`/collect-plans/${plan?.id}/edit`)"
            >编辑</el-button>
            <el-button 
              type="primary" 
              v-if="plan?.status === 'PENDING'"
              @click="executePlan"
              :loading="executing"
            >执行</el-button>
            <el-button 
              type="primary" 
              v-if="plan?.status === 'COMPLETED' || plan?.status === 'FAILED'"
              @click="reExecutePlan"
              :loading="executing"
            >重新执行</el-button>
          </div>
        </div>
      </template>
      
      <el-descriptions :column="3" border>
        <el-descriptions-item label="计划名称">{{ plan?.name }}</el-descriptions-item>
        <el-descriptions-item label="执行模式">{{ plan?.execution_mode_display }}</el-descriptions-item>
        <el-descriptions-item label="任务数量">{{ plan?.jobs_count || 0 }} 个</el-descriptions-item>
        <el-descriptions-item label="创建时间">{{ plan?.created_at }}</el-descriptions-item>
        <el-descriptions-item label="开始时间">{{ plan?.started_at || '-' }}</el-descriptions-item>
        <el-descriptions-item label="完成时间">{{ plan?.completed_at || '-' }}</el-descriptions-item>
      </el-descriptions>

      <div v-if="plan?.source_report" class="source-report-section">
        <div class="section-header">
          <span class="section-title">来源报告</span>
          <el-button link type="primary" @click="goToReport">查看完整报告</el-button>
        </div>
        <div class="report-summary">
          <div class="summary-item">
            <span class="summary-label">报告名称</span>
            <span class="summary-value">{{ plan?.source_report_name }}</span>
          </div>
          <div class="summary-item">
            <span class="summary-label">缺失项</span>
            <span class="summary-value">{{ reportSummary?.total_missing || '-' }} 条</span>
          </div>
          <div class="summary-item">
            <span class="summary-label">数据类型</span>
            <span class="summary-value">{{ reportSummary?.by_data_type?.length || 0 }} 种</span>
          </div>
          <div class="summary-item">
            <span class="summary-label">涉及股票</span>
            <span class="summary-value">{{ reportSummary?.total_stocks || 0 }} 只</span>
          </div>
        </div>
      </div>
      
      <h3 style="margin-top: 20px;">采集任务</h3>
      <el-table :data="plan?.jobs" style="margin-top: 12px;">
        <el-table-column prop="data_type_display" label="数据类型" width="150" />
        <el-table-column label="股票范围">
          <template #default="{ row }">
            <span>{{ row.symbols?.slice(0, 5).join(', ') }}{{ row.symbols?.length > 5 ? '...' : '' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="开始日期" width="120">
          <template #default="{ row }">
            {{ row.params?.start_date || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="结束日期" width="120">
          <template #default="{ row }">
            {{ row.params?.end_date || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="status_display" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getJobStatusType(row.status)">{{ row.status_display }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="开始时间" width="150">
          <template #default="{ row }">
            {{ formatDateTime(row.start_time) }}
          </template>
        </el-table-column>
        <el-table-column label="结束时间" width="150">
          <template #default="{ row }">
            {{ formatDateTime(row.end_time) }}
          </template>
        </el-table-column>
        <el-table-column prop="message" label="消息" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import api, { fetchCollectPlan, fetchIntegrityReportSummary } from '@/utils/api'
import { ElMessage, ElMessageBox } from 'element-plus'

const props = defineProps<{ id: string }>()
const router = useRouter()
const plan = ref<any>(null)
const reportSummary = ref<any>(null)
const loading = ref(true)
const executing = ref(false)
let pollTimer: number | null = null

const fetchPlan = async () => {
  try {
    const response = await fetchCollectPlan(parseInt(props.id))
    if (response.success && response.data) {
      plan.value = response.data
      if (response.data.source_report) {
        const summaryResponse = await fetchIntegrityReportSummary(response.data.source_report)
        if (summaryResponse.success && summaryResponse.data) {
          reportSummary.value = summaryResponse.data
        }
      }
      return response.data.status
    } else {
      ElMessage.error(response.error || '获取采集计划详情失败')
      return null
    }
  } catch (error) {
    console.error('Failed to fetch plan:', error)
    ElMessage.error('获取采集计划详情失败')
    return null
  }
}

const pollPlan = async () => {
  const status = await fetchPlan()
  if (status === 'RUNNING') {
    pollTimer = window.setTimeout(pollPlan, 3000)
  } else {
    loading.value = false
  }
}

const executePlan = async () => {
  executing.value = true
  try {
    await api.post(`/collect-plans/${props.id}/execute/`)
    ElMessage.success('计划开始执行')
    loading.value = true
    pollPlan()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.error || '执行失败')
  } finally {
    executing.value = false
  }
}

const reExecutePlan = async () => {
  try {
    await ElMessageBox.confirm(
      '确定要重新执行该计划吗？将重置所有任务状态。',
      '确认重新执行',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )
    executing.value = true
    await api.post(`/collect-plans/${props.id}/execute/`)
    ElMessage.success('计划开始重新执行')
    loading.value = true
    pollPlan()
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error.response?.data?.error || '执行失败')
    }
  } finally {
    executing.value = false
  }
}

const getStatusType = (status: string) => {
  const types: Record<string, string> = {
    'PENDING': 'info',
    'RUNNING': 'warning',
    'COMPLETED': 'success',
    'FAILED': 'danger'
  }
  return types[status] || 'info'
}

const getJobStatusType = (status: string) => {
  const types: Record<string, string> = {
    'PENDING': 'info',
    'RUNNING': 'warning',
    'SUCCESS': 'success',
    'FAILED': 'danger'
  }
  return types[status] || 'info'
}

const formatDateTime = (isoString: string | undefined) => {
  if (!isoString) return '-'
  const date = new Date(isoString)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  }).replace(/\//g, '-')
}

const goToReport = () => {
  if (plan.value?.source_report) {
    router.push(`/integrity-reports/${plan.value.source_report}`)
  }
}

onMounted(() => {
  fetchPlan().then(() => {
    loading.value = false
  })
})

onUnmounted(() => {
  if (pollTimer) {
    clearTimeout(pollTimer)
  }
})
</script>

<style scoped>
.collect-plan-detail {
  padding: 20px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.source-report-section {
  margin-top: 20px;
  padding: 16px;
  background: #f5f7fa;
  border-radius: 8px;
}
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.section-title {
  font-weight: 600;
  font-size: 15px;
  color: #303133;
}
.report-summary {
  display: flex;
  gap: 32px;
  flex-wrap: wrap;
}
.summary-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.summary-label {
  font-size: 12px;
  color: #909399;
}
.summary-value {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
}
</style>
