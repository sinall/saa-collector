<template>
  <div class="data-check">
    <CollectorFilterPanel
      query-button-text="检查"
      :loading="loading"
      :show-report-types="false"
      @query="handleQuery"
    />
    
    <main class="results-panel">
      <div v-if="loading" class="loading-state">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>检查中...</span>
      </div>
      
      <div v-else-if="error" class="error-message">
        <el-alert :title="error" type="error" show-icon />
      </div>
      
      <div v-else-if="result" class="results-content">
        <div class="summary-cards">
          <el-card class="summary-card">
            <div class="card-value">{{ result.summary.total }}</div>
            <div class="card-label">预期数据</div>
          </el-card>
          <el-card class="summary-card">
            <div class="card-value">{{ result.summary.existing }}</div>
            <div class="card-label">已有数据</div>
          </el-card>
          <el-card class="summary-card">
            <div class="card-value">{{ result.summary.missing }}</div>
            <div class="card-label">缺失数据</div>
          </el-card>
          <el-card class="summary-card">
            <div class="card-value">{{ (result.summary.rate * 100).toFixed(1) }}%</div>
            <div class="card-label">完整率</div>
          </el-card>
        </div>

        <el-card v-if="result.missing_details && result.missing_details.length > 0" class="details-card">
          <template #header>
            <div class="card-header">
              <span>缺失详情 ({{ result.missing_details.length }} 条)</span>
              <el-button size="small" @click="showDetails = !showDetails">
                {{ showDetails ? '收起' : '展开' }}
              </el-button>
            </div>
          </template>
          <el-table v-if="showDetails" :data="result.missing_details" stripe max-height="400">
            <el-table-column prop="code" label="股票代码" width="120" />
            <el-table-column prop="date" label="日期" width="120" />
            <el-table-column prop="missing_factors" label="缺失字段">
              <template #default="{ row }">
                <el-tag v-for="factor in row.missing_factors" :key="factor" size="small" class="mr-1">
                  {{ factor }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <el-empty v-else-if="result.summary.missing === 0" description="数据完整，无缺失" />
      </div>

      <el-empty v-else description="请选择筛选条件后点击检查" />
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import CollectorFilterPanel from '@/components/CollectorFilterPanel.vue'

interface FilterParams {
  data_type: string
  symbols: string[]
  start_date?: string
  end_date?: string
}

const loading = ref(false)
const error = ref('')
const result = ref<any>(null)
const showDetails = ref(false)

const handleQuery = async (params: FilterParams) => {
  loading.value = true
  error.value = ''
  result.value = null
  showDetails.value = false

  try {
    await new Promise(resolve => setTimeout(resolve, 1000))
    
    result.value = {
      summary: {
        total: 1000,
        existing: 950,
        missing: 50,
        rate: 0.95,
      },
      missing_details: [],
    }
    
    ElMessage.success('检查完成')
  } catch (e: any) {
    error.value = e.message || '检查失败'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.data-check {
  display: flex;
  min-height: calc(100vh - 120px);
}

.results-panel {
  flex: 1;
  padding: 1rem;
  background: #f5f7fa;
  overflow: auto;
}

.loading-state {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  height: 300px;
  gap: 1rem;
  color: #666;
}

.error-message {
  padding: 1rem;
}

.summary-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.summary-card {
  text-align: center;
}

.summary-card .card-value {
  font-size: 2rem;
  font-weight: 600;
  color: #409eff;
}

.summary-card .card-label {
  font-size: 0.85rem;
  color: #909399;
  margin-top: 0.5rem;
}

.details-card {
  margin-top: 1rem;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.mr-1 {
  margin-right: 4px;
}
</style>
