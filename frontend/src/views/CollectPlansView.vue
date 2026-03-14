<template>
  <div class="collect-plans">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>采集计划</span>
          <el-button type="primary" @click="$router.push('/collect-plans/new')">新建计划</el-button>
        </div>
      </template>
      
      <el-table :data="plans" v-loading="loading">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="name" label="计划名称" />
        <el-table-column prop="status_display" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)">{{ row.status_display }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="execution_mode_display" label="执行模式" width="100" />
        <el-table-column prop="jobs_count" label="作业数" width="80" />
        <el-table-column prop="created_at" label="创建时间" width="180" />
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <el-button link type="primary" @click="viewPlan(row.id)">查看</el-button>
            <el-button 
              link 
              type="primary" 
              v-if="row.status === 'PENDING'"
              @click="$router.push(`/collect-plans/${row.id}/edit`)"
            >编辑</el-button>
            <el-button 
              link 
              type="danger" 
              v-if="row.status === 'PENDING'"
              @click="deletePlan(row.id)"
            >删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/utils/api'
import { ElMessage, ElMessageBox } from 'element-plus'

const router = useRouter()
const plans = ref<any[]>([])
const loading = ref(false)

const fetchPlans = async () => {
  loading.value = true
  try {
    const response = await api.get('/collect-plans/')
    plans.value = response.data.results || response.data
  } finally {
    loading.value = false
  }
}

const viewPlan = (id: number) => {
  router.push(`/collect-plans/${id}`)
}

const deletePlan = async (id: number) => {
  try {
    await ElMessageBox.confirm('确定要删除该计划吗？', '提示', {
      type: 'warning'
    })
    await api.delete(`/collect-plans/${id}/`)
    ElMessage.success('删除成功')
    fetchPlans()
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error.response?.data?.error || '删除失败')
    }
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

onMounted(() => {
  fetchPlans()
})
</script>

<style scoped>
.collect-plans {
  padding: 20px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
