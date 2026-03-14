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
          </div>
        </div>
      </template>
      
      <el-descriptions :column="3" border>
        <el-descriptions-item label="计划名称">{{ plan?.name }}</el-descriptions-item>
        <el-descriptions-item label="执行模式">{{ plan?.execution_mode_display }}</el-descriptions-item>
        <el-descriptions-item label="来源报告">{{ plan?.source_report_name || '无' }}</el-descriptions-item>
        <el-descriptions-item label="创建时间">{{ plan?.created_at }}</el-descriptions-item>
        <el-descriptions-item label="开始时间">{{ plan?.started_at || '-' }}</el-descriptions-item>
        <el-descriptions-item label="完成时间">{{ plan?.completed_at || '-' }}</el-descriptions-item>
      </el-descriptions>
      
      <h3 style="margin-top: 20px;">采集作业</h3>
      <el-table :data="plan?.jobs" style="margin-top: 12px;">
        <el-table-column prop="data_type_display" label="数据类型" width="150" />
        <el-table-column label="股票范围">
          <template #default="{ row }">
            <span>{{ row.symbols?.slice(0, 5).join(', ') }}{{ row.symbols?.length > 5 ? '...' : '' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="日期范围" width="200">
          <template #default="{ row }">
            <span>{{ row.params?.start_date || '-' }} ~ {{ row.params?.end_date || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="status_display" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getJobStatusType(row.status)">{{ row.status_display }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="执行时间" width="180">
          <template #default="{ row }">
            <span v-if="row.start_time">{{ row.start_time }}</span>
            <span v-if="row.end_time"> ~ {{ row.end_time }}</span>
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
import api from '@/utils/api'
import { ElMessage } from 'element-plus'

const props = defineProps<{ id: string }>()
const router = useRouter()
const plan = ref<any>(null)
const loading = ref(true)
const executing = ref(false)
let pollTimer: number | null = null

const fetchPlan = async () => {
  try {
    const response = await api.get(`/collect-plans/${props.id}/`)
    plan.value = response.data.data
    return response.data.data.status
  } catch (error) {
    console.error('Failed to fetch plan:', error)
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
</style>
