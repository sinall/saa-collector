<template>
  <div class="collect-schedule-detail">
    <el-card v-loading="loading">
      <template #header>
        <div class="card-header" v-if="schedule">
          <div>
            <el-button link @click="$router.back()">返回</el-button>
            <span style="margin-left: 16px; font-size: 18px;">{{ schedule.name }}</span>
            <el-tag :type="schedule.enabled ? 'success' : 'info'" style="margin-left: 8px;">
              {{ schedule.enabled ? '已启用' : '已禁用' }}
            </el-tag>
          </div>
          <div>
            <el-switch
              v-model="schedule.enabled"
              active-text="启用"
              inactive-text="禁用"
              @change="toggleEnabled"
            />
          </div>
        </div>
      </template>

      <div v-if="schedule">
        <el-descriptions :column="3" border>
          <el-descriptions-item label="日程名称">{{ schedule.name }}</el-descriptions-item>
          <el-descriptions-item label="数据类型">{{ schedule.data_type_display }}</el-descriptions-item>
          <el-descriptions-item label="Cron表达式">
            <code>{{ schedule.cron_expression }}</code>
          </el-descriptions-item>
          <el-descriptions-item label="股票范围">
            <span v-if="schedule.symbols?.length">
              {{ schedule.symbols.slice(0, 5).join(', ') }}{{ schedule.symbols.length > 5 ? '...' : '' }}
            </span>
            <span v-else>全部股票</span>
          </el-descriptions-item>
          <el-descriptions-item label="日期范围">
            {{ schedule.params?.date_start || '-' }} ~ {{ schedule.params?.date_end || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="启用状态">
            <el-tag :type="schedule.enabled ? 'success' : 'info'">
              {{ schedule.enabled ? '已启用' : '已禁用' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ schedule.created_at }}</el-descriptions-item>
          <el-descriptions-item label="更新时间">{{ schedule.updated_at }}</el-descriptions-item>
        </el-descriptions>

        <div style="margin-top: 20px;">
          <div class="section-header">
            <h3>触发历史</h3>
            <el-button size="small" @click="fetchSchedule" :loading="loading">刷新</el-button>
          </div>
          <el-table :data="schedule.plans || []" style="width: 100%" v-loading="plansLoading">
            <el-table-column prop="id" label="计划ID" width="100">
              <template #default="{ row }">
                <el-link type="primary" @click="$router.push(`/collect-plans/${row.id}`)">
                  #{{ row.id }}
                </el-link>
              </template>
            </el-table-column>
            <el-table-column prop="name" label="计划名称" min-width="200" />
            <el-table-column prop="status_display" label="状态" width="100">
              <template #default="{ row }">
                <el-tag :type="getPlanStatusType(row.status)">{{ row.status_display }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="任务数" width="80">
              <template #default="{ row }">
                {{ row.success_jobs }}/{{ row.total_jobs }}
              </template>
            </el-table-column>
            <el-table-column label="触发时间" width="170">
              <template #default="{ row }">
                {{ formatDateTime(row.created_at) }}
              </template>
            </el-table-column>
          </el-table>
          <div v-if="schedule.plans?.length === 0" class="empty-hint">
            暂无触发记录
          </div>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { fetchCollectScheduleMock } from '@/utils/api'
import { ElMessage } from 'element-plus'

const props = defineProps<{ id: string }>()
const schedule = ref<any>(null)
const loading = ref(true)
const plansLoading = ref(false)

const fetchSchedule = async () => {
  loading.value = true
  try {
    const response = await fetchCollectScheduleMock(parseInt(props.id))
    if (response.success && response.data) {
      schedule.value = response.data
    } else {
      ElMessage.error(response.error || '获取采集日程详情失败')
    }
  } catch (error) {
    console.error('Failed to fetch schedule:', error)
    ElMessage.error('获取采集日程详情失败')
  } finally {
    loading.value = false
  }
}

const toggleEnabled = async () => {
  try {
    schedule.value.enabled = !schedule.value.enabled
    ElMessage.success(schedule.value.enabled ? '已启用' : '已禁用')
  } catch (error) {
    console.error('Failed to toggle enabled:', error)
    ElMessage.error('操作失败')
  }
}

const getPlanStatusType = (status: string) => {
  const types: Record<string, string> = {
    'PENDING': 'info',
    'RUNNING': 'warning',
    'COMPLETED': 'success',
    'FAILED': 'danger'
  }
  return types[status] || 'info'
}

const formatDateTime = (isoString: string) => {
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

onMounted(() => {
  fetchSchedule()
})
</script>

<style scoped>
.collect-schedule-detail {
  padding: 20px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.section-header h3 {
  margin: 0;
}
.empty-hint {
  text-align: center;
  color: #909399;
  padding: 40px 0;
}
</style>
