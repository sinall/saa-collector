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
        
        <el-divider>采集任务</el-divider>
        
        <div v-for="(job, index) in form.jobs" :key="index" class="job-item">
          <el-card shadow="never">
            <el-row :gutter="20">
              <el-col :span="24">
                <el-form-item label="数据类型">
                  <el-select v-model="job.data_type">
                    <el-option
                      v-for="item in selectableDataTypes"
                      :key="item.key"
                      :label="item.label"
                      :value="item.key"
                    />
                  </el-select>
                </el-form-item>
              </el-col>
            </el-row>
            <el-row :gutter="20">
              <el-col :span="8">
                <el-form-item label="开始日期">
                  <el-date-picker
                    v-model="job.date_start"
                    type="date"
                    value-format="YYYY-MM-DD"
                  />
                </el-form-item>
              </el-col>
              <el-col :span="16">
                <el-form-item label="结束日期">
                  <div class="end-date-control">
                    <el-radio-group v-model="job.end_date_mode" size="small" class="end-date-mode-group">
                      <el-radio-button value="EXECUTION_DAY">执行当天</el-radio-button>
                      <el-radio-button value="FIXED">固定日期</el-radio-button>
                    </el-radio-group>
                    <el-date-picker
                      v-if="job.end_date_mode === 'FIXED'"
                      v-model="job.date_end"
                      class="end-date-picker"
                      type="date"
                      value-format="YYYY-MM-DD"
                      placeholder="结束日期"
                      :disabled-date="(date: Date) => isBeforeDate(date, job.date_start)"
                    />
                    <span v-else class="floating-end-date">执行当天</span>
                  </div>
                </el-form-item>
              </el-col>
            </el-row>
            <el-form-item label="股票范围">
              <el-radio-group v-model="job.stock_scope">
                <el-radio-button value="ALL">全市场</el-radio-button>
                <el-radio-button value="SELECTED">指定股票</el-radio-button>
                <el-radio-button value="INDEX">中证800</el-radio-button>
              </el-radio-group>
            </el-form-item>
            <el-form-item v-if="job.stock_scope === 'SELECTED'" label="股票代码">
              <el-input
                v-model="job.symbols_input"
                type="textarea"
                placeholder="每行一个股票代码，留空则全量"
                :rows="3"
              />
            </el-form-item>
            <el-form-item v-if="job.stock_scope === 'INDEX'" label="指数代码">
              <el-select v-model="job.stock_list_code" style="width: 100%">
                <el-option label="中证800 (000906)" value="000906" />
              </el-select>
            </el-form-item>
            <el-form-item v-if="job.data_type === 'extras'" label="补全周期">
              <el-radio-group v-model="job.data_frequency">
                <el-radio-button value="daily">按天</el-radio-button>
                <el-radio-button value="monthly">月度</el-radio-button>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="已有数据">
              <el-switch
                v-model="job.skip_existing"
                active-text="跳过"
                inactive-text="重采"
              />
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
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { fetchCollectPlan, createCollectPlan, updateCollectPlan, type CollectPlanJobPayload } from '@/utils/api'
import { useDataTypes, isDataTypeVisible } from '@/composables/useDataTypes'
import { ElMessage } from 'element-plus'

const { dataTypes, loadDataTypes } = useDataTypes()
const selectableDataTypes = computed(() => dataTypes.value.filter(dt => isDataTypeVisible(dt, 'collect_plan')))

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
    stock_scope: 'ALL',
    stock_list_code: '000906',
    end_date_mode: 'EXECUTION_DAY',
    symbols_input: '',
    date_start: null,
    date_end: null,
    data_frequency: 'daily',
    skip_existing: true
  })
}

const removeJob = (index: number) => {
  form.value.jobs.splice(index, 1)
}

const buildJobsPayload = (): CollectPlanJobPayload[] => form.value.jobs.map((job: any) => ({
  id: job.id ?? undefined,
  data_type: job.data_type,
  stock_scope: job.stock_scope,
  stock_list_code: job.stock_scope === 'INDEX' ? job.stock_list_code : null,
  symbols: job.symbols_input
    ? job.symbols_input.split('\n').map((s: string) => s.trim()).filter(Boolean)
    : [],
  start_date: job.date_start,
  end_date: job.end_date_mode === 'FIXED' ? job.date_end : null,
  end_date_mode: job.end_date_mode,
  data_frequency: job.data_frequency,
  skip_existing: Boolean(job.skip_existing)
}))

const getJobParam = (job: any, key: 'start_date' | 'end_date') => {
  return job.config?.params?.[key] ?? job.config?.[key] ?? job.params?.[key] ?? null
}

const formatDateKey = (date: Date) => {
  const year = date.getFullYear()
  const month = `${date.getMonth() + 1}`.padStart(2, '0')
  const day = `${date.getDate()}`.padStart(2, '0')
  return `${year}-${month}-${day}`
}

const isBeforeDate = (date: Date, minDate?: string | null) => {
  return Boolean(minDate && formatDateKey(date) < minDate)
}

const hasInvalidJobDateRange = () => {
  return form.value.jobs.some((job: any) => (
    job.end_date_mode === 'FIXED' && job.date_start && job.date_end && job.date_end < job.date_start
  ))
}

const fetchPlan = async () => {
  if (!route.params.id) return
  loading.value = true
  try {
    const response = await fetchCollectPlan(Number(route.params.id))
    if (!response.success || !response.data) {
      ElMessage.error(response.error || '获取计划失败')
      return
    }
    const plan = response.data
    form.value.name = plan.name
    form.value.execution_mode = plan.execution_mode || 'PARALLEL'
    form.value.jobs = plan.jobs?.map((job: any) => ({
      id: job.id,
      data_type: job.data_type,
      stock_scope: job.config?.stock_scope || job.config?.params?.stock_scope || 'ALL',
      stock_list_code: job.config?.stock_list_code || job.config?.params?.stock_list_code || '000906',
      end_date_mode: job.config?.params?.end_date_mode || (getJobParam(job, 'end_date') ? 'FIXED' : 'EXECUTION_DAY'),
      symbols_input: job.config?.symbols?.join('\n') || '',
      date_start: getJobParam(job, 'start_date'),
      date_end: getJobParam(job, 'end_date'),
      data_frequency: job.config?.params?.data_frequency || job.config?.data_frequency || 'daily',
      skip_existing: Boolean(job.config?.params?.skip_existing ?? job.config?.skip_existing)
    })) || []
  } finally {
    loading.value = false
  }
}

const savePlan = async () => {
  if (!form.value.name) {
    ElMessage.warning('请输入计划名称')
    return
  }
  if (form.value.jobs.some((job: any) => job.end_date_mode === 'FIXED' && !job.date_end)) {
    ElMessage.warning('请选择结束日期或改为执行当天')
    return
  }
  if (hasInvalidJobDateRange()) {
    ElMessage.warning('结束日期不能早于开始日期')
    return
  }

  saving.value = true
  try {
    if (isEdit.value) {
      await updateCollectPlan(Number(route.params.id), {
        name: form.value.name,
        execution_mode: form.value.execution_mode as 'PARALLEL' | 'SEQUENTIAL',
        jobs: buildJobsPayload()
      })
      ElMessage.success('保存成功')
      router.push(`/collect-plans/${route.params.id}`)
    } else {
      const jobs = buildJobsPayload()

      const response = await createCollectPlan({
        name: form.value.name,
        execution_mode: form.value.execution_mode as 'PARALLEL' | 'SEQUENTIAL',
        jobs
      })

      if (response.success && response.data) {
        ElMessage.success('创建成功')
        router.push(`/collect-plans/${response.data.id}`)
      } else {
        ElMessage.error(response.error || '创建失败')
      }
    }
  } catch (error: any) {
    ElMessage.error(error.message || '操作失败')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  loadDataTypes()
  if (isEdit.value) {
    fetchPlan()
  } else {
    addJob()
  }
})

watch(
  () => route.params.id,
  (newId, oldId) => {
    if (route.name === 'collect-plan-edit' && newId && newId !== oldId) {
      fetchPlan()
    }
  }
)
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
.end-date-control {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}
.end-date-mode-group {
  flex: 0 0 auto;
}
.end-date-picker {
  width: 220px;
}
.floating-end-date {
  color: #909399;
  font-size: 14px;
  line-height: 32px;
}
</style>
