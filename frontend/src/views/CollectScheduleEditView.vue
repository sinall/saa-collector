<template>
  <div class="collect-schedule-edit">
    <el-card v-loading="loading">
      <template #header>
        <div class="card-header">
          <span>{{ isEdit ? '编辑采集日程' : '新建采集日程' }}</span>
        </div>
      </template>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="120px"
        style="max-width: 600px"
      >
        <el-form-item label="日程名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入日程名称" />
        </el-form-item>

        <el-form-item label="数据类型" prop="data_type">
          <el-select v-model="form.data_type" placeholder="请选择数据类型" style="width: 100%">
            <el-option
              v-for="item in dataTypes"
              :key="item.key"
              :label="item.label"
              :value="item.key"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="股票范围">
          <el-radio-group v-model="stockScope">
            <el-radio value="all">全部股票</el-radio>
            <el-radio value="selected">指定股票</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item v-if="stockScope === 'selected'" label="股票代码" prop="symbols">
          <el-select
            v-model="form.symbols"
            multiple
            filterable
            allow-create
            placeholder="输入股票代码"
            style="width: 100%"
          />
        </el-form-item>

        <el-form-item label="Cron表达式" prop="cron_expression">
          <el-input v-model="form.cron_expression" placeholder="例如: 0 9 * * 1-5">
            <template #append>
              <el-tooltip content="格式: 分 时 日 月 周。例如 0 9 * * 1-5 表示工作日9点">
                <el-icon><QuestionFilled /></el-icon>
              </el-tooltip>
            </template>
          </el-input>
        </el-form-item>

        <el-form-item label="常用预设">
          <el-button-group>
            <el-button size="small" @click="setCron('0 9 * * 1-5')">每日9点(工作日)</el-button>
            <el-button size="small" @click="setCron('0 10 * * 1')">每周一10点</el-button>
            <el-button size="small" @click="setCron('0 18 * * 1-5')">每日18点(工作日)</el-button>
          </el-button-group>
        </el-form-item>

        <el-form-item label="采集参数">
          <el-form-item label="日期开始">
            <el-input v-model="form.params.date_start" placeholder="例如: today 或 2024-01-01" />
          </el-form-item>
          <el-form-item label="日期结束">
            <el-input v-model="form.params.date_end" placeholder="例如: today 或 2024-12-31" />
          </el-form-item>
        </el-form-item>

        <el-form-item label="是否启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" @click="handleSubmit" :loading="submitting">
            {{ isEdit ? '保存' : '创建' }}
          </el-button>
          <el-button @click="$router.back()">取消</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { useDataTypes } from '@/composables/useDataTypes'
import {
  fetchCollectSchedule,
  createCollectSchedule,
  updateCollectSchedule
} from '@/utils/api'

const { dataTypes, loadDataTypes } = useDataTypes()

const route = useRoute()
const router = useRouter()
const formRef = ref<FormInstance>()
const submitting = ref(false)
const loading = ref(false)

const isEdit = computed(() => !!route.params.id)

const stockScope = ref<'all' | 'selected'>('all')

const buildDefaultForm = () => ({
  name: '',
  data_type: '',
  symbols: [] as string[],
  cron_expression: '',
  params: {
    date_start: 'today',
    date_end: 'today'
  },
  enabled: true
})

const form = ref(buildDefaultForm())

const rules: FormRules = {
  name: [{ required: true, message: '请输入日程名称', trigger: 'blur' }],
  data_type: [{ required: true, message: '请选择数据类型', trigger: 'change' }],
  cron_expression: [{ required: true, message: '请输入Cron表达式', trigger: 'blur' }]
}

const setCron = (cron: string) => {
  form.value.cron_expression = cron
}

const resetFormState = () => {
  form.value = buildDefaultForm()
  stockScope.value = 'all'
}

const fetchSchedule = async () => {
  if (!isEdit.value) {
    resetFormState()
    return
  }

  loading.value = true
  try {
    const id = parseInt(route.params.id as string)
    const response = await fetchCollectSchedule(id)
    if (response.success && response.data) {
      const schedule = response.data
      form.value = {
        name: schedule.name,
        data_type: schedule.data_type,
        symbols: schedule.symbols || [],
        cron_expression: schedule.cron_expression,
        params: {
          date_start: (schedule.params as Record<string, any>)?.date_start || 'today',
          date_end: (schedule.params as Record<string, any>)?.date_end || 'today'
        },
        enabled: schedule.status === 'ENABLED'
      }
      stockScope.value = (schedule.symbols && schedule.symbols.length > 0) ? 'selected' : 'all'
    } else {
      ElMessage.error(response.error || '获取采集日程失败')
      router.push('/collect-schedules')
    }
  } catch (error: any) {
    ElMessage.error(error.message || '获取采集日程失败')
    router.push('/collect-schedules')
  } finally {
    loading.value = false
  }
}

const handleSubmit = async () => {
  if (!formRef.value) return

  await formRef.value.validate(async (valid) => {
    if (!valid) return

    submitting.value = true
    try {
      const payload = {
        name: form.value.name,
        data_type: form.value.data_type,
        symbols: stockScope.value === 'all' ? [] : form.value.symbols,
        cron_expression: form.value.cron_expression,
        params: form.value.params,
        status: form.value.enabled ? 'ENABLED' as const : 'DISABLED' as const
      }

      if (isEdit.value) {
        const id = parseInt(route.params.id as string)
        await updateCollectSchedule(id, payload)
        ElMessage.success('保存成功')
        router.push(`/collect-schedules/${id}`)
      } else {
        await createCollectSchedule(payload)
        ElMessage.success('创建成功')
        router.push('/collect-schedules')
      }
    } catch (error: any) {
      ElMessage.error(error.message || '操作失败')
    } finally {
      submitting.value = false
    }
  })
}

onMounted(() => {
  loadDataTypes()
  fetchSchedule()
})

watch(
  () => route.params.id,
  (newId, oldId) => {
    if (route.name !== 'collect-schedule-edit') return
    if (newId === oldId) return
    fetchSchedule()
  }
)
</script>

<style scoped>
.collect-schedule-edit {
  padding: 20px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
