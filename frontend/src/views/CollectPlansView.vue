<template>
  <div class="collect-plans">
    <el-card>
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <span>采集计划</span>
            <el-radio-group v-model="sourceFilter" size="small" style="margin-left: 20px" @change="handleSourceFilterChange">
              <el-radio-button value="">全部</el-radio-button>
              <el-radio-button value="MANUAL">即时采集</el-radio-button>
              <el-radio-button value="INTEGRITY">修复计划</el-radio-button>
              <el-radio-button value="SCHEDULE">定时触发</el-radio-button>
            </el-radio-group>
          </div>
          <el-button type="primary" @click="showInstantCollectDialog">即时采集</el-button>
        </div>
      </template>

      <el-table :data="displayPlans" v-loading="loading">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="name" label="计划名称" min-width="180" />
        <el-table-column label="来源" width="100">
          <template #default="{ row }">
            <el-tag :type="getSourceType(row.source)">
              {{ getSourceLabel(row.source) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="来源详情" width="150">
          <template #default="{ row }">
            <template v-if="row.source === 'INTEGRITY'">
              <el-link type="primary" @click="$router.push(`/integrity-reports/${row.source_report_id}`)">
                查看报告
              </el-link>
            </template>
            <template v-else-if="row.source === 'SCHEDULE'">
              <div>
                <div>{{ row.source_schedule_name }}</div>
                <el-tag v-if="row.trigger_type" size="small" style="margin-top: 4px">
                  {{ row.trigger_type === 'MANUAL' ? '手动触发' : '自动触发' }}
                </el-tag>
              </div>
            </template>
            <template v-else>
              <span>-</span>
            </template>
          </template>
        </el-table-column>
        <el-table-column prop="status_display" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)">{{ row.status_display }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="execution_mode_display" label="执行模式" width="100" />
        <el-table-column label="任务数" width="80">
          <template #default="{ row }">
            {{ row.success_jobs }}/{{ row.total_jobs }}
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180" />
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="viewPlan(row.id)">查看</el-button>
            <el-dropdown trigger="click" style="vertical-align: middle; margin-left: 8px;" v-if="row.status === 'PENDING' || row.status === 'QUEUED' || row.status === 'RUNNING' || row.status === 'STOPPED' || row.status === 'COMPLETED' || row.status === 'FAILED'">
              <el-button link type="info">
                <el-icon><More /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item v-if="canEditPlan(row)" @click="$router.push(`/collect-plans/${row.id}/edit`)">编辑</el-dropdown-item>
                  <el-dropdown-item v-if="row.status === 'PENDING'" @click="executePlan(row)">执行</el-dropdown-item>
                  <el-dropdown-item v-if="row.status === 'QUEUED' || row.status === 'RUNNING'" @click="stopPlan(row)">停止</el-dropdown-item>
                  <el-dropdown-item v-if="row.status === 'STOPPED'" @click="continuePlan(row)">继续</el-dropdown-item>
                  <el-dropdown-item v-if="row.status === 'STOPPED' || row.status === 'FAILED' || row.status === 'COMPLETED'" @click="resetPlan(row)">重置</el-dropdown-item>
                  <el-dropdown-item v-if="row.status === 'COMPLETED' || row.status === 'FAILED'" @click="executePlan(row)">重新执行</el-dropdown-item>
                  <el-dropdown-item v-if="row.status === 'PENDING'" divided @click="deletePlan(row.id)">删除</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-container" v-if="totalPlans > 0">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[20, 50, 100]"
          :total="totalPlans"
          layout="total, sizes, prev, pager, next"
          @current-change="fetchPlans"
          @size-change="handlePageSizeChange"
        />
      </div>
    </el-card>

    <el-dialog
      v-model="instantCollectVisible"
      title="即时采集"
      width="500px"
    >
      <el-form :model="instantForm" label-width="100px">
        <el-form-item label="计划名称">
          <el-input v-model="instantForm.name" placeholder="可选，自动生成" />
        </el-form-item>
        <el-form-item label="数据类型" required>
          <el-select v-model="instantForm.data_type" placeholder="请选择数据类型" style="width: 100%">
            <el-option
              v-for="item in instantCollectDataTypes"
              :key="item.key"
              :label="item.label"
              :value="item.key"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-if="instantSupportsStockScope" label="股票范围">
          <el-radio-group v-model="instantForm.stock_scope">
            <el-radio-button value="ALL">全市场</el-radio-button>
            <el-radio-button value="SELECTED">指定股票</el-radio-button>
            <el-radio-button value="INDEX">中证800</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="instantSupportsStockScope && instantForm.stock_scope === 'SELECTED'" label="股票代码">
          <el-select
            v-model="instantForm.symbols"
            multiple
            filterable
            allow-create
            placeholder="输入股票代码"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item v-if="instantSupportsStockScope && instantForm.stock_scope === 'INDEX'" label="指数代码">
          <el-select v-model="instantForm.stock_list_code" style="width: 100%">
            <el-option label="中证800 (000906)" value="000906" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="instantForm.data_type === 'extras'" label="补全周期">
          <el-radio-group v-model="instantForm.data_frequency">
            <el-radio-button value="daily">按天</el-radio-button>
            <el-radio-button value="monthly">月度</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="开始日期">
          <el-date-picker
            v-model="instantForm.start_date"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="开始日期"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="结束日期">
          <div class="end-date-control">
            <el-radio-group v-model="instantForm.end_date_mode" size="small" class="end-date-mode-group">
              <el-radio-button value="EXECUTION_DAY">执行当天</el-radio-button>
              <el-radio-button value="FIXED">固定日期</el-radio-button>
            </el-radio-group>
            <el-date-picker
              v-if="instantForm.end_date_mode === 'FIXED'"
              v-model="instantForm.end_date"
              class="end-date-picker"
              type="date"
              value-format="YYYY-MM-DD"
              placeholder="结束日期"
              :disabled-date="(date: Date) => isBeforeDate(date, instantForm.start_date)"
            />
            <span v-else class="floating-end-date">执行当天</span>
          </div>
        </el-form-item>
        <el-form-item label="已有数据">
          <el-switch
            v-model="instantForm.skip_existing"
            active-text="跳过"
            inactive-text="重采"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="instantCollectVisible = false">取消</el-button>
        <el-button type="primary" @click="createInstantPlan" :loading="creating">创建并执行</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onActivated, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { More } from '@element-plus/icons-vue'
import {
  fetchCollectPlans,
  executeCollectPlan,
  stopCollectPlan,
  continueCollectPlan,
  resetCollectPlan,
  deleteCollectPlan,
  createCollectPlan
} from '@/utils/api'
import type { CollectPlan } from '@/utils/api'
import { useDataTypes, isDataTypeVisible } from '@/composables/useDataTypes'

const { dataTypes, loadDataTypes, getLabel } = useDataTypes()
const instantCollectDataTypes = computed(() => dataTypes.value.filter(dt => isDataTypeVisible(dt, 'collect_plan')))
const STOCK_SCOPE_DATA_TYPES = new Set([
  'stock_info',
  'quote',
  'historical_quote',
  'price_adjust_factor',
  'extras',
  'index_weights',
  'financial_statements',
  'balance_sheet',
  'income',
  'cash_flow',
  'dividend',
  'capital',
  'main_business',
])
const supportsStockScope = (dataType: string) => STOCK_SCOPE_DATA_TYPES.has(dataType)
const instantSupportsStockScope = computed(() => supportsStockScope(instantForm.value.data_type))

const router = useRouter()
const plans = ref<CollectPlan[]>([])
const loading = ref(false)
const hasLoadedOnce = ref(false)
const sourceFilter = ref('')
const currentPage = ref(1)
const pageSize = ref(20)
const totalPlans = ref(0)

const instantCollectVisible = ref(false)
const creating = ref(false)
const instantForm = ref({
  name: '',
  data_type: '',
  stock_scope: 'ALL' as 'ALL' | 'SELECTED' | 'INDEX',
  stock_list_code: '000906',
  data_frequency: 'daily' as 'daily' | 'monthly',
  symbols: [] as string[],
  start_date: '',
  end_date_mode: 'EXECUTION_DAY' as 'FIXED' | 'EXECUTION_DAY',
  end_date: '',
  skip_existing: true
})

const formatDateKey = (date: Date) => {
  const year = date.getFullYear()
  const month = `${date.getMonth() + 1}`.padStart(2, '0')
  const day = `${date.getDate()}`.padStart(2, '0')
  return `${year}-${month}-${day}`
}

const isBeforeDate = (date: Date, minDate?: string | null) => {
  return Boolean(minDate && formatDateKey(date) < minDate)
}

interface DisplayPlan {
  id: number
  name: string
  status: string
  status_display: string
  source: string
  source_report_id: number | null
  source_schedule_id: number | null
  source_schedule_name: string | null
  trigger_type?: 'AUTO' | 'MANUAL'
  execution_mode: string
  execution_mode_display: string
  total_jobs: number
  success_jobs: number
  created_at: string
}

const getSuccessJobs = (plan: CollectPlan): number => {
  if (!plan.jobs) return 0
  return plan.jobs.filter(j => j.status === 'SUCCESS').length
}

const displayPlans = computed<DisplayPlan[]>(() => {
  return plans.value.map(plan => ({
    id: plan.id,
    name: plan.name,
    status: plan.status,
    status_display: plan.status_display,
    source: plan.source,
    source_report_id: plan.source_report || null,
    source_schedule_id: plan.source_schedule_id || null,
    source_schedule_name: plan.source_schedule_name || null,
    trigger_type: plan.trigger_type,
    execution_mode: plan.execution_mode || 'PARALLEL',
    execution_mode_display: plan.execution_mode_display,
    total_jobs: plan.jobs_count || (plan.jobs?.length || 0),
    success_jobs: getSuccessJobs(plan),
    created_at: plan.created_at
  }))
})

const fetchPlans = async () => {
  loading.value = true
  try {
    const response = await fetchCollectPlans({
      source: sourceFilter.value || undefined,
      page: currentPage.value,
      page_size: pageSize.value
    })
    if (response.success && response.data) {
      plans.value = response.data.results
      totalPlans.value = response.data.pagination.total
    }
  } catch (error) {
    console.error('Failed to fetch plans:', error)
    ElMessage.error('获取采集计划列表失败')
  } finally {
    loading.value = false
  }
}

const handleSourceFilterChange = () => {
  currentPage.value = 1
  fetchPlans()
}

const handlePageSizeChange = () => {
  currentPage.value = 1
  fetchPlans()
}

const getSourceType = (source: string) => {
  const types: Record<string, string> = {
    'MANUAL': 'primary',
    'INTEGRITY': 'warning',
    'SCHEDULE': 'success'
  }
  return types[source] || 'info'
}

const getSourceLabel = (source: string) => {
  const labels: Record<string, string> = {
    'MANUAL': '即时采集',
    'INTEGRITY': '修复计划',
    'SCHEDULE': '定时触发'
  }
  return labels[source] || source
}

const getStatusType = (status: string) => {
  const types: Record<string, string> = {
    'QUEUED': 'info',
    'PENDING': 'info',
    'RUNNING': 'warning',
    'STOPPED': 'danger',
    'COMPLETED': 'success',
    'FAILED': 'danger'
  }
  return types[status] || 'info'
}

const canEditPlan = (plan: DisplayPlan) => {
  return plan.source === 'MANUAL' && plan.status !== 'QUEUED' && plan.status !== 'RUNNING'
}

const viewPlan = (id: number) => {
  router.push(`/collect-plans/${id}`)
}

const executePlan = async (row: DisplayPlan) => {
  try {
    await ElMessageBox.confirm('确定要执行该计划吗？', '提示', { type: 'info' })
    const response = await executeCollectPlan(row.id)
    if (response.success) {
      ElMessage.success('计划已开始执行')
      fetchPlans()
    } else {
      ElMessage.error(response.error || '执行失败')
    }
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error.response?.data?.error || '执行失败')
    }
  }
}

const stopPlan = async (row: DisplayPlan) => {
  try {
    await ElMessageBox.confirm('确定要停止该计划吗？', '提示', { type: 'warning' })
    const response = await stopCollectPlan(row.id)
    if (response.success) {
      ElMessage.success('计划已停止')
      fetchPlans()
    } else {
      ElMessage.error(response.error || '停止失败')
    }
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error.response?.data?.error || '停止失败')
    }
  }
}

const continuePlan = async (row: DisplayPlan) => {
  try {
    const response = await continueCollectPlan(row.id)
    if (response.success) {
      ElMessage.success('计划已继续执行')
      fetchPlans()
    } else {
      ElMessage.error(response.error || '继续失败')
    }
  } catch (error: any) {
    ElMessage.error(error.response?.data?.error || '继续失败')
  }
}

const resetPlan = async (row: DisplayPlan) => {
  try {
    await ElMessageBox.confirm('确定要重置该计划吗？', '提示', { type: 'warning' })
    const response = await resetCollectPlan(row.id)
    if (response.success) {
      ElMessage.success('计划已重置')
      fetchPlans()
    } else {
      ElMessage.error(response.error || '重置失败')
    }
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error.response?.data?.error || '重置失败')
    }
  }
}

const deletePlan = async (id: number) => {
  try {
    await ElMessageBox.confirm('确定要删除该计划吗？', '提示', { type: 'warning' })
    const response = await deleteCollectPlan(id)
    if (response.success) {
      ElMessage.success('删除成功')
      fetchPlans()
    } else {
      ElMessage.error(response.error || '删除失败')
    }
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error.response?.data?.error || '删除失败')
    }
  }
}

const showInstantCollectDialog = () => {
  instantForm.value = {
    name: '',
    data_type: '',
    stock_scope: 'ALL' as 'ALL' | 'SELECTED' | 'INDEX',
    stock_list_code: '000906',
    data_frequency: 'daily' as 'daily' | 'monthly',
    symbols: [],
    start_date: '',
    end_date_mode: 'EXECUTION_DAY' as 'FIXED' | 'EXECUTION_DAY',
    end_date: '',
    skip_existing: true
  }
  instantCollectVisible.value = true
}

const createInstantPlan = async () => {
  if (!instantForm.value.data_type) {
    ElMessage.warning('请选择数据类型')
    return
  }

  creating.value = true
  try {
    const dataTypeName = getLabel(instantForm.value.data_type)
    const name = instantForm.value.name || `即时采集-${dataTypeName}-${new Date().toISOString().split('T')[0]}`

    if (instantForm.value.end_date_mode === 'FIXED' && !instantForm.value.end_date) {
      ElMessage.warning('请选择结束日期或改为执行当天')
      return
    }

    const stockScope = instantSupportsStockScope.value ? instantForm.value.stock_scope : 'ALL'
    const params: any = {
      name,
      execution_mode: 'PARALLEL',
      jobs: [{
        data_type: instantForm.value.data_type,
        stock_scope: stockScope,
        stock_list_code: stockScope === 'INDEX' ? instantForm.value.stock_list_code : null,
        data_frequency: instantForm.value.data_type === 'extras' ? instantForm.value.data_frequency : undefined,
        end_date_mode: instantForm.value.end_date_mode,
        symbols: stockScope === 'SELECTED' ? instantForm.value.symbols : [],
        skip_existing: instantForm.value.skip_existing,
      }]
    }

    params.jobs[0].start_date = instantForm.value.start_date || undefined
    params.jobs[0].end_date = instantForm.value.end_date_mode === 'FIXED' ? (instantForm.value.end_date || undefined) : null
    if (instantForm.value.end_date_mode === 'FIXED' && instantForm.value.start_date && instantForm.value.end_date && instantForm.value.end_date < instantForm.value.start_date) {
      ElMessage.warning('结束日期不能早于开始日期')
      return
    }

    const response = await createCollectPlan(params)
    if (response.success) {
      ElMessage.success('即时采集计划创建成功')
      instantCollectVisible.value = false
      fetchPlans()
    } else {
      ElMessage.error(response.error || '创建失败')
    }
  } catch (error: any) {
    ElMessage.error(error.response?.data?.error || '创建失败')
  } finally {
    creating.value = false
  }
}

onMounted(async () => {
  try {
    await loadDataTypes()
    await fetchPlans()
  } finally {
    hasLoadedOnce.value = true
  }
})

onActivated(() => {
  if (hasLoadedOnce.value) {
    fetchPlans()
  }
})

watch(
  () => instantForm.value.data_type,
  (dataType) => {
    if (!supportsStockScope(dataType)) {
      instantForm.value.stock_scope = 'ALL'
      instantForm.value.symbols = []
    }
  },
)
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
.header-left {
  display: flex;
  align-items: center;
}
.pagination-container {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
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
