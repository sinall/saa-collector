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
        <el-descriptions :column="2" border>
          <el-descriptions-item label="日程名称">{{ schedule.name }}</el-descriptions-item>
          <el-descriptions-item label="启用状态">
            <el-tag :type="schedule.enabled ? 'success' : 'info'">
              {{ schedule.enabled ? '已启用' : '已禁用' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ schedule.created_at }}</el-descriptions-item>
          <el-descriptions-item label="更新时间">{{ schedule.updated_at }}</el-descriptions-item>
        </el-descriptions>

        <div style="margin-top: 20px;">
          <h3>执行历史</h3>
          <el-table :data="schedule.executions || []" style="width: 100%">
            <el-table-column prop="id" label="ID" width="80" />
            <el-table-column prop="status_display" label="状态" width="100">
              <template #default="{ row }">
                <el-tag :type="getExecutionStatusType(row.status)">{{ row.status_display }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="message" label="消息" />
          </el-table>
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

const fetchSchedule = async () => {
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

const getExecutionStatusType = (status: string) => {
  const types: Record<string, string> = {
    'SUCCESS': 'success',
    'FAILED': 'danger',
    'RUNNING': 'warning'
  }
  return types[status] || 'info'
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
