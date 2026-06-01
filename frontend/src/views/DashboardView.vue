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
                <div class="stat-date">
                  <template v-if="stat.latest_date">最新: {{ stat.latest_date }}</template>
                </div>
                <div class="stat-completeness" v-if="stat.show_completeness !== false && stat.completeness !== null">
                  <div class="completeness-bar-bg">
                    <div 
                      class="completeness-bar" 
                      :style="{ 
                        width: (stat.completeness * 100) + '%',
                        backgroundColor: getCompletenessColor(stat.completeness)
                      }"
                    ></div>
                  </div>
                  <span class="completeness-text">{{ Math.round(stat.completeness * 100) }}%</span>
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
import { useDataTypes } from '@/composables/useDataTypes'

const { dataTypes, loadDataTypes } = useDataTypes()
const dataStatus = ref<DataStatus[]>([])

onMounted(async () => {
  await loadDataTypes()
  dataStatus.value = dataTypes.value
    .filter(dt => dt.table)
    .map(dt => ({
      data_type: dt.key,
      data_type_display: dt.label,
      count: 0,
      earliest_date: null,
      latest_date: null,
      frequency: dt.frequency ?? null,
      completeness: null,
      loading: true,
      error: false,
      show_completeness: dt.show_completeness,
    }))
  loadDataStatus()
})

const loadDataStatus = async () => {
  try {
    const response = await fetchDataStatus()
    if (response.success && response.data) {
      response.data.forEach(newData => {
        const index = dataStatus.value.findIndex(
          item => item.data_type === newData.data_type
        )
        if (index !== -1) {
          const existingItem = dataStatus.value[index]
          dataStatus.value[index] = { 
            ...newData,
            show_completeness: existingItem?.show_completeness,
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

const getCompletenessColor = (completeness: number): string => {
  if (completeness < 0.5) return '#f56c6c'
  if (completeness < 0.75) return '#e6a23c'
  if (completeness < 0.9) return '#409eff'
  return '#67c23a'
}
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
  height: 160px;
  transition: all 0.3s ease;
}

.stat-card-error {
  border-color: #f56c6c;
  background-color: #fef0f0;
}

.stat-content {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.stat-title {
  font-size: 14px;
  color: #909399;
  margin-bottom: 8px;
  height: 22px;
}

.stat-value {
  font-size: 28px;
  font-weight: bold;
  color: #303133;
  height: 36px;
  line-height: 36px;
}

.stat-date {
  font-size: 12px;
  color: #909399;
  height: 20px;
  line-height: 20px;
  margin-top: 4px;
}

.stat-completeness {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: auto;
  height: 24px;
}

.completeness-bar-bg {
  flex: 1;
  height: 6px;
  background-color: #ebeef5;
  border-radius: 3px;
  overflow: hidden;
}

.completeness-bar {
  height: 100%;
  border-radius: 3px;
  transition: width 0.3s ease;
}

.completeness-text {
  font-size: 12px;
  font-weight: 500;
  color: #606266;
  min-width: 36px;
  text-align: right;
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
