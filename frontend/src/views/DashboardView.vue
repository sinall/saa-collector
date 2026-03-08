<template>
  <div class="dashboard">
    <el-row :gutter="20" class="stats-row">
      <el-col :span="6" v-for="stat in dataStatus" :key="stat.data_type">
        <el-card class="stat-card">
          <div class="stat-content">
            <div class="stat-title">{{ stat.data_type_display }}</div>
            <div class="stat-value">{{ formatNumber(stat.count) }}</div>
            <div class="stat-date" v-if="stat.latest_date">
              最新: {{ stat.latest_date }}
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card class="recent-jobs">
      <template #header>
        <div class="card-header">
          <span>最近采集任务</span>
          <el-button type="primary" size="small" @click="refreshJobs">刷新</el-button>
        </div>
      </template>
      <el-table :data="recentJobs" stripe>
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
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { fetchDataStatus, fetchCollectJobs, type DataStatus, type CollectJob } from '@/utils/api'

const dataStatus = ref<DataStatus[]>([])
const recentJobs = ref<CollectJob[]>([])

const loadDataStatus = async () => {
  try {
    const response = await fetchDataStatus()
    if (response.success && response.data) {
      dataStatus.value = response.data
    }
  } catch (error) {
    console.error('Failed to load data status:', error)
  }
}

const loadRecentJobs = async () => {
  try {
    const response = await fetchCollectJobs({ page_size: 10 })
    if (response.success && response.data) {
      recentJobs.value = response.data.results || []
    }
  } catch (error) {
    console.error('Failed to load recent jobs:', error)
  }
}

const refreshJobs = () => {
  loadRecentJobs()
}

const formatNumber = (num: number): string => {
  if (num >= 1000000) {
    return (num / 1000000).toFixed(1) + 'M'
  } else if (num >= 1000) {
    return (num / 1000).toFixed(1) + 'K'
  }
  return num.toString()
}

const formatDateTime = (dateStr: string): string => {
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
  loadDataStatus()
  loadRecentJobs()
})
</script>

<style scoped>
.dashboard {
  padding: 20px;
}

.stats-row {
  margin-bottom: 20px;
}

.stat-card {
  height: 120px;
}

.stat-content {
  display: flex;
  flex-direction: column;
  justify-content: center;
  height: 100%;
}

.stat-title {
  font-size: 14px;
  color: #909399;
  margin-bottom: 8px;
}

.stat-value {
  font-size: 28px;
  font-weight: bold;
  color: #303133;
}

.stat-date {
  font-size: 12px;
  color: #909399;
  margin-top: 8px;
}

.recent-jobs {
  margin-top: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
