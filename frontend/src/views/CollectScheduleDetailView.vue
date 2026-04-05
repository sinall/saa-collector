<template>
  <div class="collect-schedule-detail">
    <el-card v-loading="loading">
      <template #header>
        <div class="card-header" v-if="schedule">
          <div>
            <el-button link @click="$router.back()">返回</el-button>
            <span style="margin-left: 16px; font-size: 18px;">{{ schedule.name }}</span>
            <el-tag :type="schedule.status === 'ENABLED' ? 'success' : 'info'" style="margin-left: 8px;">
              {{ schedule.status === 'ENABLED' ? '已启用' : '已禁用' }}
            </el-tag>
          </div>
          <div>
            <el-switch
              v-model="schedule.status"
              active-value="ENABLED"
              inactive-value="DISABLED"
              active-text="启用"
              inactive-text="禁用"
              @change="toggleStatus"
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
          <el-descriptions-item label="参数配置">
            <code>{{ JSON.stringify(schedule.params) }}</code>
          </el-descriptions-item>
          <el-descriptions-item label="启用状态">
            <el-tag :type="schedule.status === 'ENABLED' ? 'success' : 'info'">
              {{ schedule.status === 'ENABLED' ? '已启用' : '已禁用' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="上次触发">
            {{ schedule.last_triggered_at ? formatDateTime(schedule.last_triggered_at) : '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="下次触发">
            {{ schedule.next_trigger_at ? formatDateTime(schedule.next_trigger_at) : '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ formatDateTime(schedule.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="更新时间">{{ formatDateTime(schedule.updated_at) }}</el-descriptions-item>
        </el-descriptions>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { fetchCollectSchedule, updateCollectSchedule } from '@/utils/api'
import { ElMessage } from 'element-plus'

const props = defineProps<{ id: string }>()
const schedule = ref<any>(null)
const loading = ref(true)

const fetchSchedule = async () => {
  loading.value = true
  try {
    const response = await fetchCollectSchedule(parseInt(props.id))
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

const toggleStatus = async () => {
  if (!schedule.value) return

  try {
    await updateCollectSchedule(schedule.value.id, { status: schedule.value.status })
    ElMessage.success(schedule.value.status === 'ENABLED' ? '已启用' : '已禁用')
  } catch (error) {
    console.error('Failed to toggle status:', error)
    ElMessage.error('操作失败')
    schedule.value.status = schedule.value.status === 'ENABLED' ? 'DISABLED' : 'ENABLED'
  }
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
</style>
