<template>
  <div class="collect-schedules">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>采集日程</span>
          <el-button type="primary" @click="$router.push('/collect-schedules/new')">新建</el-button>
        </div>
      </template>

      <el-table :data="schedules" v-loading="loading">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="name" label="计划名称" min-width="150" />
        <el-table-column prop="data_type_display" label="数据类型" width="120" />
        <el-table-column label="股票范围" width="120">
          <template #default="{ row }">
            {{ row.symbols && row.symbols.length > 0 ? `${row.symbols.length}只股票` : '全部股票' }}
          </template>
        </el-table-column>
        <el-table-column prop="cron_expression" label="Cron表达式" width="130" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'ENABLED' ? 'success' : 'info'">
              {{ row.status === 'ENABLED' ? '已启用' : '已禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="next_trigger_at" label="下次触发" width="180" />
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="$router.push(`/collect-schedules/${row.id}`)">详情</el-button>
            <el-dropdown trigger="click" style="vertical-align: middle; margin-left: 8px;">
              <el-button link type="info">
                <el-icon><More /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item @click="triggerNow(row)">执行</el-dropdown-item>
                  <el-dropdown-item @click="$router.push(`/collect-schedules/${row.id}/edit`)">编辑</el-dropdown-item>
                  <el-dropdown-item @click="toggleStatus(row)">
                    {{ row.status === 'ENABLED' ? '禁用' : '启用' }}
                  </el-dropdown-item>
                  <el-dropdown-item divided @click="deleteSchedule(row)">删除</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { More } from '@element-plus/icons-vue'
import { useDataTypes } from '@/composables/useDataTypes'
import {
  fetchCollectSchedules,
  updateCollectSchedule,
  deleteCollectSchedule,
  triggerCollectSchedule
} from '@/utils/api'

const { getLabel, loadDataTypes } = useDataTypes()

const router = useRouter()

const schedules = ref<any[]>([])
const loading = ref(false)

const fetchSchedules = async () => {
  loading.value = true
  try {
    const response = await fetchCollectSchedules()
    if (response.success && response.data) {
      schedules.value = response.data.map(s => ({
        ...s,
        data_type_display: getLabel(s.data_type)
      }))
    }
  } finally {
    loading.value = false
  }
}

const toggleStatus = async (row: any) => {
  const newStatus = row.status === 'ENABLED' ? 'DISABLED' : 'ENABLED'
  const action = newStatus === 'ENABLED' ? '启用' : '禁用'

  try {
    await ElMessageBox.confirm(`确定要${action}该采集日程吗？`, '提示', { type: 'warning' })
    await updateCollectSchedule(row.id, { status: newStatus })
    row.status = newStatus
    ElMessage.success(`${action}成功`)
  } catch (error: any) {
    if (error !== 'cancel') {
      console.error('Failed to toggle status:', error)
    }
  }
}

const triggerNow = async (row: any) => {
  try {
    await ElMessageBox.confirm('确定要立即执行该采集日程吗？', '提示', { type: 'info' })
    const response = await triggerCollectSchedule(row.id)
    if (response.success && response.data?.plan_id) {
      ElMessageBox.confirm(
        '采集计划已创建，是否跳转到采集计划详情页查看？',
        '提示',
        {
          confirmButtonText: '查看计划',
          cancelButtonText: '关闭',
        }
      )      .then(() => {
        if (response.data) {
          router.push(`/collect-plans/${response.data.plan_id}`)
        }
      }).catch(() => {})
    }
  } catch (error: any) {
    if (error !== 'cancel') {
      console.error('Failed to trigger schedule:', error)
    }
  }
}

const deleteSchedule = async (row: any) => {
  try {
    await ElMessageBox.confirm('确定要删除该采集日程吗？', '提示', { type: 'warning' })
    await deleteCollectSchedule(row.id)
    schedules.value = schedules.value.filter(s => s.id !== row.id)
    ElMessage.success('删除成功')
  } catch (error: any) {
    if (error !== 'cancel') {
      console.error('Failed to delete schedule:', error)
    }
  }
}

onMounted(() => {
  loadDataTypes()
  fetchSchedules()
})
</script>

<style scoped>
.collect-schedules {
  padding: 20px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
