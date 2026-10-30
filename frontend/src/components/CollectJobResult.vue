<template>
  <el-tooltip content="查看执行结果">
    <el-button :icon="Document" aria-label="查看执行结果" @click="open" />
  </el-tooltip>
  <el-drawer v-model="visible" :title="`任务 #${jobId} 执行结果`" size="min(720px, 100vw)" append-to-body>
    <div v-loading="loading">
      <el-alert v-if="error" :title="error" type="error" :closable="false" />
      <template v-else-if="!loading">
        <p>{{ detail?.message || '暂无执行摘要' }}</p>
        <el-alert v-if="detail?.result?.truncated" title="部分问题明细未保存" type="warning" :closable="false" />
        <el-empty v-if="!issues.length" description="暂无问题明细" />
        <el-collapse v-else>
          <el-collapse-item v-for="(issue, index) in issues" :key="index" :name="index">
            <template #title>
              <span>{{ issue.symbol || '-' }} · {{ issue.code }} · {{ issue.resolved_at ? '重试已解决' : '待处理' }}</span>
            </template>
            <dl>
              <dt>报告期 / 披露日</dt><dd>{{ issue.report_date || '-' }} / {{ issue.disclosure_date || '-' }}</dd>
              <dt>来源 / 财报表</dt><dd>{{ issue.provider || '-' }} / {{ issue.table || '-' }}</dd>
              <dt>出现次数</dt><dd>{{ issue.occurrences || 1 }}</dd>
            </dl>
            <pre>{{ JSON.stringify(issue.differences || {}, null, 2) }}</pre>
          </el-collapse-item>
        </el-collapse>
      </template>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Document } from '@element-plus/icons-vue'
import { fetchCollectJobDetail, type CollectJob } from '@/utils/api'

const props = defineProps<{ jobId: number }>()
const visible = ref(false)
const loading = ref(false)
const error = ref('')
const detail = ref<CollectJob | null>(null)
const issues = computed(() => detail.value?.result?.issues || [])
async function open() {
  visible.value = true
  loading.value = true
  detail.value = null
  error.value = ''
  try {
    const response = await fetchCollectJobDetail(props.jobId)
    if (!response.success || !response.data) throw new Error('result unavailable')
    detail.value = response.data
  } catch {
    error.value = '执行结果加载失败，请关闭后重试'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
dt { color: #606266; }
dd { margin: 4px 0 12px; overflow-wrap: anywhere; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; font-size: 12px; }
</style>
