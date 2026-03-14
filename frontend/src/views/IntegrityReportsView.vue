<template>
  <div class="integrity-reports">
    <IntegrityReportFilterPanel
      query-button-text="生成报告"
      :loading="generating"
      @query="handleGenerateReport"
    />

    <main class="results-panel">
      <el-card>
        <template #header>
          <div class="card-header">
            <span>完整性报告列表</span>
          </div>
        </template>

        <el-table :data="reports" v-loading="loading">
          <el-table-column prop="id" label="ID" width="80" />
          <el-table-column prop="name" label="报告名称" />
          <el-table-column prop="status_display" label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="getStatusType(row.status)">{{ row.status_display }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="frequency_display" label="频度" width="80" />
          <el-table-column prop="items_count" label="缺失项数" width="100" />
          <el-table-column prop="created_at_display" label="创建时间" width="180" />
          <el-table-column label="操作" width="150">
            <template #default="{ row }">
              <el-button link type="primary" @click="viewReport(row.id)">查看</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import IntegrityReportFilterPanel from '@/components/IntegrityReportFilterPanel.vue'
import api from '@/utils/api'

const router = useRouter()
const reports = ref<any[]>([])
const loading = ref(false)
const generating = ref(false)

const fetchReports = async () => {
  loading.value = true
  try {
    const response = await api.get('/integrity-reports/')
    reports.value = response.data.results || response.data
  } finally {
    loading.value = false
  }
}

const handleGenerateReport = async (params: any) => {
  if (!params.data_types || params.data_types.length === 0) {
    ElMessage.warning('请至少选择一种数据类型')
    return
  }

  generating.value = true
  try {
    const data = {
      name: generateReportName(params),
      stock_scope: params.symbols && params.symbols.length > 0 ? 'SELECTED' : 'ALL',
      stock_codes: params.symbols || [],
      data_types: params.data_types,
      frequency: params.frequency,
      date_start: params.start_date,
      date_end: params.end_date
    }

    const response = await api.post('/integrity-reports/', data)
    ElMessage.success('报告创建成功')
    router.push(`/integrity-reports/${response.data.data.id}`)
  } catch (error: any) {
    ElMessage.error(error.response?.data?.error || '创建失败')
  } finally {
    generating.value = false
  }
}

const generateReportName = (params: any) => {
  const typeNames: Record<string, string> = {
    'trade_days': '交易日',
    'quote': '最新行情',
    'historical_quote': '历史行情',
    'balance_sheet': '资产负债表',
    'income': '利润表',
    'cash_flow': '现金流量表',
    'dividend': '分红数据',
    'capital': '股本变动',
    'valuation': '估值数据',
    'main_business': '主营业务'
  }

  const typeLabel = params.data_types.length === 1
    ? typeNames[params.data_types[0]] || params.data_types[0]
    : `${params.data_types.length}种数据类型`

  const freqNames: Record<string, string> = {
    'daily': '日度',
    'weekly': '周度',
    'monthly': '月度',
    'quarterly': '季度',
    'yearly': '年度'
  }
  const freqLabel = freqNames[params.frequency] || params.frequency

  const date = new Date().toISOString().split('T')[0]
  return `${date} ${typeLabel}${freqLabel}完整性检查`
}

const viewReport = (id: number) => {
  router.push(`/integrity-reports/${id}`)
}

const getStatusType = (status: string) => {
  const types: Record<string, string> = {
    'GENERATING': 'warning',
    'COMPLETED': 'success',
    'FAILED': 'danger'
  }
  return types[status] || 'info'
}

onMounted(() => {
  fetchReports()
})
</script>

<style scoped>
.integrity-reports {
  display: flex;
  min-height: calc(100vh - 120px);
}

.results-panel {
  flex: 1;
  padding: 1rem;
  background: #f5f7fa;
  overflow: auto;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
