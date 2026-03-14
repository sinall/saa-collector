<template>
  <div class="dashboard">
    <CompletenessHeatmap />

    <el-card class="stats-card">
      <template #header>
        <div class="card-header">
          <span>数据统计</span>
          <el-button type="primary" size="small" @click="refreshStats">刷新</el-button>
        </div>
      </template>
      <el-row :gutter="20" class="stats-row">
        <el-col :span="6" v-for="stat in dataStatus" :key="stat.data_type">
          <el-card class="stat-card" :class="{ 'stat-card-error': stat.error }">
            <div class="stat-content">
              <div class="stat-title">{{ stat.data_type_display }}</div>
              
              <div v-if="stat.loading" class="stat-skeleton">
                <el-skeleton :rows="1" animated />
              </div>
              
              <div v-else-if="stat.error" class="stat-error">
                <el-icon><WarningFilled /></el-icon>
                <span>加载失败</span>
              </div>
              
              <template v-else>
                <div class="stat-value">{{ formatNumber(stat.count) }}</div>
                <div class="stat-date" v-if="stat.latest_date">
                  最新: {{ stat.latest_date }}
                </div>
              </template>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { WarningFilled } from '@element-plus/icons-vue'
import { fetchDataStatus, type DataStatus } from '@/utils/api'
import CompletenessHeatmap from '@/components/CompletenessHeatmap.vue'

const EXPECTED_DATA_TYPES = [
  { data_type: 'trade_days', data_type_display: '交易日' },
  { data_type: 'stock_info', data_type_display: '股票基本信息' },
  { data_type: 'quote', data_type_display: '最新行情' },
  { data_type: 'historical_quote', data_type_display: '历史行情' },
  { data_type: 'balance_sheet', data_type_display: '资产负债表' },
  { data_type: 'income', data_type_display: '利润表' },
  { data_type: 'cash_flow', data_type_display: '现金流量表' },
  { data_type: 'dividend', data_type_display: '分红数据' },
  { data_type: 'main_business', data_type_display: '主营业务' },
  { data_type: 'capital', data_type_display: '股本变动' },
]

const dataStatus = ref<DataStatus[]>(
  EXPECTED_DATA_TYPES.map(item => ({
    ...item,
    count: 0,
    earliest_date: null,
    latest_date: null,
    loading: true,
    error: false,
  }))
)

const loadDataStatus = async () => {
  try {
    const response = await fetchDataStatus()
    if (response.success && response.data) {
      response.data.forEach(newData => {
        const index = dataStatus.value.findIndex(
          item => item.data_type === newData.data_type
        )
        if (index !== -1) {
          dataStatus.value[index] = { 
            ...newData, 
            loading: false, 
            error: false 
          }
        } else {
          dataStatus.value.push({
            ...newData,
            loading: false,
            error: false,
          })
        }
      })
    } else {
      dataStatus.value.forEach(item => {
        item.loading = false
        item.error = true
      })
    }
  } catch (error) {
    console.error('Failed to load data status:', error)
    dataStatus.value.forEach(item => {
      item.loading = false
      item.error = true
    })
  }
}

const refreshStats = () => {
  dataStatus.value.forEach(item => {
    item.loading = true
    item.error = false
  })
  loadDataStatus()
}

const formatNumber = (num: number): string => {
  if (num >= 1000000) {
    return (num / 1000000).toFixed(1) + 'M'
  } else if (num >= 1000) {
    return (num / 1000).toFixed(1) + 'K'
  }
  return num.toString()
}

onMounted(() => {
  loadDataStatus()
})
</script>

<style scoped>
.dashboard {
  padding: 0;
}

.stats-card {
  margin-top: 20px;
}

.stats-row {
  margin: 0;
}

.stat-card {
  height: 120px;
  transition: all 0.3s ease;
}

.stat-card-error {
  border-color: #f56c6c;
  background-color: #fef0f0;
}

.stat-content {
  display: flex;
  flex-direction: column;
  justify-content: center;
  height: 100%;
}

.stat-title {
  font-size: 14px;
  color: #909399;
  margin-bottom: 8px;
}

.stat-value {
  font-size: 28px;
  font-weight: bold;
  color: #303133;
}

.stat-date {
  font-size: 12px;
  color: #909399;
  margin-top: 8px;
}

.stat-skeleton {
  padding: 10px 0;
}

.stat-error {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #f56c6c;
  font-size: 14px;
  padding: 10px 0;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
