<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElTree } from 'element-plus'
import { fetchIntegrityReportTreeSummary } from '@/utils/api'

export interface TreeNode {
  key: string
  label: string
  count: number
  children?: TreeNode[]
}

export interface FilterParams {
  dataTypes: string[]
  periods: string[]
  status: string
  stockCode: string
}

const props = defineProps<{
  reportId: number
}>()

const emit = defineEmits<{
  'filter-change': [params: FilterParams]
}>()

const treeData = ref<TreeNode[]>([])
const loading = ref(false)
const checkedKeys = ref<string[]>([])

const filterStatus = ref('')
const filterStockCode = ref('')

const treeExpanded = ref(true)
const filterExpanded = ref(true)

const treeRef = ref<InstanceType<typeof ElTree> | null>(null)

async function loadTreeData() {
  loading.value = true
  try {
    const response = await fetchIntegrityReportTreeSummary(props.reportId)
    if (response.success && response.data) {
      treeData.value = response.data.tree
    } else {
      console.error('Failed to load tree data:', response.error)
    }
  } finally {
    loading.value = false
  }
}

function handleCheckChange(_data: TreeNode, info: { checkedKeys: (string | number)[] }) {
  checkedKeys.value = info.checkedKeys.map(k => String(k))
  emitFilterChange()
}

function handleStatusChange() {
  emitFilterChange()
}

function handleStockCodeChange() {
  emitFilterChange()
}

function emitFilterChange() {
  emit('filter-change', getFilterParams())
}

function selectAll() {
  const allKeys = getAllNodeKeys(treeData.value)
  checkedKeys.value = allKeys
  emitFilterChange()
}

function clearSelection() {
  checkedKeys.value = []
  filterStatus.value = ''
  filterStockCode.value = ''
  emitFilterChange()
}

function getAllNodeKeys(nodes: TreeNode[]): string[] {
  const keys: string[] = []
  for (const node of nodes) {
    keys.push(node.key)
    if (node.children) {
      keys.push(...getAllNodeKeys(node.children))
    }
  }
  return keys
}

function getFilterParams(): FilterParams {
  const dataTypes = new Set<string>()
  const periods = new Set<string>()

  for (const key of checkedKeys.value) {
    const parts = key.split('-')
    if (parts.length === 1) {
      dataTypes.add(parts[0]!)
    } else if (parts.length >= 2) {
      dataTypes.add(parts[0]!)
      periods.add(parts.slice(1).join('-'))
    }
  }

  return {
    dataTypes: Array.from(dataTypes),
    periods: Array.from(periods),
    status: filterStatus.value,
    stockCode: filterStockCode.value
  }
}

defineExpose({ getFilterParams })

watch(() => props.reportId, () => {
  loadTreeData()
}, { immediate: true })
</script>

<template>
  <aside class="filter-panel" v-loading="loading">
    <div class="panel-header">
      <span class="panel-title">数据筛选</span>
      <div class="header-actions">
        <button class="quick-btn" @click="selectAll">全选</button>
        <button class="quick-btn" @click="clearSelection">清空</button>
      </div>
    </div>

    <div class="panel-content">
      <section class="filter-section">
        <div class="section-header" @click="treeExpanded = !treeExpanded">
          <h4>数据类型与周期</h4>
          <span class="toggle-icon">{{ treeExpanded ? '▼' : '▶' }}</span>
        </div>
        <div v-if="treeExpanded" class="section-content tree-content">
          <el-tree
            ref="treeRef"
            :data="treeData"
            show-checkbox
            node-key="key"
            :default-expand-all="false"
            :expand-on-click-node="false"
            :check-on-click-node="true"
            :checked-keys="checkedKeys"
            @check="handleCheckChange"
            :props="{
              label: 'label',
              children: 'children',
            }"
          >
            <template #default="{ data }">
              <span class="tree-node">
                <span class="node-label">{{ data.label }}</span>
                <span class="node-count">({{ data.count }})</span>
              </span>
            </template>
          </el-tree>
        </div>
      </section>

      <section class="filter-section">
        <div class="section-header" @click="filterExpanded = !filterExpanded">
          <h4>附加筛选</h4>
          <span class="toggle-icon">{{ filterExpanded ? '▼' : '▶' }}</span>
        </div>
        <div v-if="filterExpanded" class="section-content">
          <div class="filter-item">
            <label>修复状态</label>
            <select v-model="filterStatus" @change="handleStatusChange">
              <option value="">全部</option>
              <option value="PENDING">待修复</option>
              <option value="FIXED">已修复</option>
            </select>
          </div>
          <div class="filter-item">
            <label>股票代码</label>
            <input
              type="text"
              v-model="filterStockCode"
              placeholder="输入代码"
              @change="handleStockCodeChange"
            />
          </div>
        </div>
      </section>
    </div>
  </aside>
</template>

<style scoped>
.filter-panel {
  width: 280px;
  min-width: 280px;
  background: #fff;
  border-right: 1px solid #e0e0e0;
  display: flex;
  flex-direction: column;
  height: 100%;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  background: #f5f5f5;
  border-bottom: 1px solid #e0e0e0;
}

.panel-title {
  font-weight: 600;
  color: #333;
}

.header-actions {
  display: flex;
  gap: 0.5rem;
}

.quick-btn {
  padding: 0.15rem 0.4rem;
  font-size: 0.7rem;
  background: #f5f5f5;
  border: 1px solid #ddd;
  border-radius: 3px;
  cursor: pointer;
}

.quick-btn:hover {
  background: #e8e8e8;
}

.panel-content {
  flex: 1;
  padding: 1rem;
  display: flex;
  flex-direction: column;
}

.filter-section {
  margin-bottom: 0.5rem;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  padding: 0.5rem 0;
  border-bottom: 1px solid #eee;
  user-select: none;
}

.section-header:hover {
  background: #f9f9f9;
}

.section-header h4 {
  margin: 0;
  font-size: 0.9rem;
  color: #333;
}

.toggle-icon {
  font-size: 0.75rem;
  color: #888;
}

.section-content {
  padding-top: 0.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.tree-content {
  flex: 1;
}

.tree-node {
  display: flex;
  align-items: center;
  gap: 8px;
}

.node-label {
  font-size: 13px;
  color: #303133;
}

.node-count {
  font-size: 12px;
  color: #909399;
}

.filter-item {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.filter-item select,
.filter-item input[type="text"] {
  padding: 0.5rem;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 0.85rem;
  width: 100%;
}

.filter-item label {
  font-size: 0.85rem;
  color: #606266;
}

.filter-item select,
.filter-item input {
  padding: 0.5rem;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 0.85rem;
  width: 100%;
  box-sizing: border-box;
}
</style>
