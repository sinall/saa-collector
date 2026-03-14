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
import { ElMessage, ElMessageBox } from 'element-plus'
import { More } from '@element-plus/icons-vue'

const schedules = ref<any[]>([])
const loading = ref(false)

const dataTypeLabels: Record<string, string> = {
  'trade_days': '交易日',
  'stock_info': '股票基本信息',
  'quote': '最新行情',
  'historical_quote': '历史行情',
  'balance_sheet': '资产负债表',
  'income': '利润表',
  'cash_flow': '现金流量表',
  'dividend': '分红数据',
  'main_business': '主营业务',
  'capital': '股本变动',
  'valuation': '估值数据'
}

const mockSchedules = [
  {
    id: 1,
    name: '每日行情采集',
    data_type: 'historical_quote',
    data_type_display: '历史行情',
    symbols: [],
    params: { date_start: 'today', date_end: 'today' },
    cron_expression: '0 9 * * 1-5',
    status: 'ENABLED',
    last_triggered_at: '2026-03-17 09:00:00',
    next_trigger_at: '2026-03-18 09:00:00'
  },
  {
    id: 2,
    name: '每周财务报表采集',
    data_type: 'balance_sheet',
    data_type_display: '资产负债表',
    symbols: ['000001', '000002', '600000'],
    params: {},
    cron_expression: '0 10 * * 1',
    status: 'ENABLED',
    last_triggered_at: '2026-03-16 10:00:00',
    next_trigger_at: '2026-03-23 10:00:00'
  },
  {
    id: 3,
    name: '每日估值数据',
    data_type: 'valuation',
    data_type_display: '估值数据',
    symbols: [],
    params: {},
    cron_expression: '0 18 * * 1-5',
    status: 'DISABLED',
    last_triggered_at: null,
    next_trigger_at: null
  }
]

const fetchSchedules = async () => {
  loading.value = true
  try {
    await new Promise(resolve => setTimeout(resolve, 500))
    schedules.value = mockSchedules.map(s => ({
      ...s,
      data_type_display: dataTypeLabels[s.data_type] || s.data_type
    }))
  } finally {
    loading.value = false
  }
}

const toggleStatus = async (row: any) => {
  const newStatus = row.status === 'ENABLED' ? 'DISABLED' : 'ENABLED'
  const action = newStatus === 'ENABLED' ? '启用' : '禁用'
  
  try {
    await ElMessageBox.confirm(`确定要${action}该采集日程吗？`, '提示', { type: 'warning' })
    row.status = newStatus
    ElMessage.success(`${action}成功`)
  } catch {
    // cancelled
  }
}

const triggerNow = async (row: any) => {
  try {
    await ElMessageBox.confirm('确定要立即执行该采集日程吗？', '提示', { type: 'info' })
    ElMessage.success(`已触发执行: ${row.name}`)
  } catch {
    // cancelled
  }
}

const deleteSchedule = async (row: any) => {
  try {
    await ElMessageBox.confirm('确定要删除该采集日程吗？', '提示', { type: 'warning' })
    schedules.value = schedules.value.filter(s => s.id !== row.id)
    ElMessage.success('删除成功')
  } catch {
    // cancelled
  }
}

onMounted(() => {
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
