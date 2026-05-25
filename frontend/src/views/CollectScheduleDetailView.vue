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
          <div class="header-actions">
            <el-button type="primary" @click="triggerNow">执行</el-button>
            <el-button @click="goToEdit">编辑</el-button>
            <el-switch
              v-model="schedule.status"
              active-value="ENABLED"
              inactive-value="DISABLED"
              active-text="启用"
              inactive-text="禁用"
              @change="toggleStatus"
            />
            <el-button type="danger" plain @click="deleteCurrentSchedule">删除</el-button>
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
import { ref, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  deleteCollectSchedule,
  fetchCollectSchedule,
  triggerCollectSchedule,
  updateCollectSchedule
} from '@/utils/api'
import { ElMessage, ElMessageBox } from 'element-plus'

const props = defineProps<{ id: string }>()
const router = useRouter()
const schedule = ref<any>(null)
const loading = ref(true)

const fetchSchedule = async () => {
  const requestedId = props.id
  loading.value = true
  try {
    const response = await fetchCollectSchedule(parseInt(requestedId))
    if (requestedId !== props.id) {
      return
    }

    if (response.success && response.data) {
      schedule.value = response.data
    } else {
      ElMessage.error(response.error || '获取采集日程详情失败')
    }
  } catch (error) {
    console.error('Failed to fetch schedule:', error)
    ElMessage.error('获取采集日程详情失败')
  } finally {
    if (requestedId === props.id) {
      loading.value = false
    }
  }
}

const loadCurrentSchedule = () => {
  schedule.value = null
  fetchSchedule()
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

const goToEdit = () => {
  if (!schedule.value) return
  router.push(`/collect-schedules/${schedule.value.id}/edit`)
}

const triggerNow = async () => {
  if (!schedule.value) return

  try {
    await ElMessageBox.confirm('确定要立即执行该采集日程吗？', '提示', { type: 'info' })
    const response = await triggerCollectSchedule(schedule.value.id)
    const plan = response.data?.plan
    const planId = plan?.id || response.data?.plan_id
    if (response.success && planId) {
      await fetchSchedule()
      ElMessageBox.confirm(
        '采集计划已创建，是否跳转到采集计划详情页查看？',
        '提示',
        {
          confirmButtonText: '查看计划',
          cancelButtonText: '关闭',
        }
      ).then(() => {
        router.push(`/collect-plans/${planId}`)
      }).catch(() => {})
    }
  } catch (error: any) {
    if (error !== 'cancel') {
      console.error('Failed to trigger schedule:', error)
    }
  }
}

const deleteCurrentSchedule = async () => {
  if (!schedule.value) return

  try {
    await ElMessageBox.confirm('确定要删除该采集日程吗？', '提示', { type: 'warning' })
    await deleteCollectSchedule(schedule.value.id)
    ElMessage.success('删除成功')
    router.push('/collect-schedules')
  } catch (error: any) {
    if (error !== 'cancel') {
      console.error('Failed to delete schedule:', error)
    }
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

onMounted(loadCurrentSchedule)

watch(
  () => props.id,
  (newId, oldId) => {
    if (newId === oldId) return
    loadCurrentSchedule()
  }
)
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
.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}
</style>
