<template>
  <div class="collect-plan-edit">
    <el-card v-loading="loading">
      <template #header>
        <div class="card-header">
          <span>{{ isEdit ? '编辑计划' : '新建计划' }}</span>
        </div>
      </template>
      
      <el-form :model="form" label-width="100px" style="max-width: 800px;">
        <el-form-item label="计划名称" required>
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="执行模式">
          <el-radio-group v-model="form.execution_mode">
            <el-radio value="PARALLEL">并行执行</el-radio>
            <el-radio value="SEQUENTIAL">顺序执行</el-radio>
          </el-radio-group>
        </el-form-item>
        
        <el-divider>采集作业</el-divider>
        
        <div v-for="(job, index) in form.jobs" :key="index" class="job-item">
          <el-card shadow="never">
            <el-row :gutter="20">
              <el-col :span="8">
                <el-form-item label="数据类型">
                  <el-select v-model="job.data_type">
                    <el-option label="交易日" value="trade_days" />
                    <el-option label="股票基本信息" value="stock_info" />
                    <el-option label="最新行情" value="quote" />
                    <el-option label="历史行情" value="historical_quote" />
                    <el-option label="资产负债表" value="balance_sheet" />
                    <el-option label="利润表" value="income" />
                    <el-option label="现金流量表" value="cash_flow" />
                    <el-option label="分红数据" value="dividend" />
                    <el-option label="主营业务" value="main_business" />
                    <el-option label="股本变动" value="capital" />
                    <el-option label="估值数据" value="valuation" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="开始日期">
                  <el-date-picker v-model="job.date_start" type="date" value-format="YYYY-MM-DD" />
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="结束日期">
                  <el-date-picker v-model="job.date_end" type="date" value-format="YYYY-MM-DD" />
                </el-form-item>
              </el-col>
            </el-row>
            <el-form-item label="股票代码">
              <el-input v-model="job.symbols_input" type="textarea" placeholder="每行一个股票代码，留空则全量" :rows="3" />
            </el-form-item>
            <el-button type="danger" link @click="removeJob(index)">删除此作业</el-button>
          </el-card>
        </div>
        
        <el-button type="primary" link @click="addJob" style="margin-top: 12px;">
          + 添加作业
        </el-button>
        
        <el-form-item style="margin-top: 24px;">
          <el-button type="primary" @click="savePlan" :loading="saving">保存</el-button>
          <el-button @click="$router.back()">取消</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import api from '@/utils/api'
import { ElMessage } from 'element-plus'

const router = useRouter()
const route = useRoute()
const loading = ref(false)
const saving = ref(false)

const isEdit = computed(() => !!route.params.id)

const form = ref({
  name: '',
  execution_mode: 'PARALLEL',
  jobs: [] as any[]
})

const addJob = () => {
  form.value.jobs.push({
    id: null,
    data_type: 'quote',
    symbols_input: '',
    date_start: null,
    date_end: null
  })
}

const removeJob = (index: number) => {
  form.value.jobs.splice(index, 1)
}

const fetchPlan = async () => {
  if (!route.params.id) return
  loading.value = true
  try {
    const response = await api.get(`/collect-plans/${route.params.id}/`)
    const plan = response.data.data
    form.value.name = plan.name
    form.value.execution_mode = plan.execution_mode
    form.value.jobs = plan.jobs.map((job: any) => ({
      id: job.id,
      data_type: job.data_type,
      symbols_input: job.symbols?.join('\n') || '',
      date_start: job.params?.start_date || null,
      date_end: job.params?.end_date || null
    }))
  } finally {
    loading.value = false
  }
}

const savePlan = async () => {
  if (!form.value.name) {
    ElMessage.warning('请输入计划名称')
    return
  }
  
  saving.value = true
  try {
    const data = {
      name: form.value.name,
      execution_mode: form.value.execution_mode
    }
    
    if (isEdit.value) {
      await api.patch(`/collect-plans/${route.params.id}/`, data)
      ElMessage.success('保存成功')
      router.push(`/collect-plans/${route.params.id}`)
    } else {
      const response = await api.post('/collect-plans/', data)
      ElMessage.success('创建成功')
      router.push(`/collect-plans/${response.data.data.id}`)
    }
  } catch (error: any) {
    ElMessage.error(error.response?.data?.error || '保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  if (isEdit.value) {
    fetchPlan()
  } else {
    addJob()
  }
})
</script>

<style scoped>
.collect-plan-edit {
  padding: 20px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.job-item {
  margin-bottom: 16px;
}
</style>
