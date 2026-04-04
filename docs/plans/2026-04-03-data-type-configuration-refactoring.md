# 数据类型配置架构重构方案

**创建日期**: 2026-04-03  
**状态**: 待实施  
**优先级**: 高  

---

## 目录

1. [背景与问题](#背景与问题)
2. [改进方案](#改进方案)
3. [架构设计](#架构设计)
4. [实施计划](#实施计划)
5. [预期效果](#预期效果)
6. [风险评估](#风险评估)

---

## 背景与问题

### 当前问题

#### 1. 数据类型硬编码分散

新增数据类型需要修改**至少7个文件**：

**后端 (1处)**:
- `backend/saa_collector/views.py:95` - DataStatusView 中的硬编码列表

**前端 (6处)**:
- `frontend/src/views/DashboardView.vue:59` - EXPECTED_DATA_TYPES
- `frontend/src/components/IntegrityReportFilterPanel.vue:29` - dataTypes
- `frontend/src/components/CollectorFilterPanel.vue:37` - dataTypes
- `frontend/src/views/CollectPlansView.vue:150` - dataTypeOptions
- `frontend/src/views/DataBrowseTypeView.vue:134` - DATA_TYPE_TO_TABLE
- `frontend/src/views/CollectSchedulesView.vue:62` - dataTypeLabels

#### 2. 配置化不完整

虽然已有部分配置：
- ✅ 后端有 `DATA_TYPE_CONFIG` (在 `constants.py`)
- ✅ 前端有 `DATA_TYPE_GROUPS` 和 `DEFAULT_DISPLAY_CONFIGS` (在 `api.ts`)
- ❌ 但缺少统一的数据类型配置API
- ❌ 前后端配置可能不一致

#### 3. 实际案例

最近新增3个行业相关数据类型（index_weights, industries, industry_stocks）时：
- 只修改了 `constants.py` 和 `api.ts` 的部分配置
- 仪表盘、数据检查等页面未自动显示这些新类型
- 需要逐个检查和修改7+个文件

---

## 改进方案

### 核心原则

**单一数据源 (Single Source of Truth)**

```
后端配置 (DATA_TYPE_CONFIG) 
    ↓
API 暴露 (/api/data-types/)
    ↓
前端全局使用 (useDataTypes composable)
    ↓
所有组件自动更新
```

### 方案对比

| 方案 | 优点 | 缺点 | 推荐度 |
|------|------|------|--------|
| **配置驱动+API** | 单一数据源、前后端一致、可维护性最佳 | 需要较大重构 | ⭐⭐⭐⭐⭐ |
| **前端集中配置** | 快速实现、改动小 | 前后端配置分离、易不一致 | ⭐⭐⭐ |
| **混合方案** | 平衡性好 | 复杂度中等 | ⭐⭐⭐⭐ |

**选择方案**: 配置驱动 + API统一管理

---

## 架构设计

### 1. 后端配置结构

**文件**: `backend/saa_collector/constants.py`

#### 扩展配置字段

```python
DATA_TYPE_CONFIG = {
    'trade_days': {
        'table': 'saa_trade_days',
        'date_column': 'date',
        'data_frequency': 'daily',
        'stock_level': False,
        'label': '交易日',
        'group': 'market',              # 新增：分组
        'show_completeness': False,      # 新增：是否在仪表盘显示完整性
        'need_date': True,               # 新增：采集时是否需要日期参数
        'supports_integrity_check': True,
        'order': 1,                      # 新增：排序
    },
    'stock_info': {
        'table': 'saa_stocks',
        'date_column': None,
        'data_frequency': None,
        'stock_level': False,
        'label': '股票基本信息',
        'group': 'market',
        'show_completeness': False,
        'need_date': False,
        'supports_integrity_check': False,
        'order': 2,
    },
    'quote': {
        'table': 'saa_latest_prices',
        'date_column': None,
        'data_frequency': 'daily',
        'stock_level': True,
        'label': '最新行情',
        'group': 'market',
        'show_completeness': True,
        'need_date': False,
        'stock_column': 'code',
        'supports_integrity_check': True,
        'order': 3,
    },
    'historical_quote': {
        'table': 'saa_prices_ex',
        'date_column': 'date',
        'data_frequency': 'daily',
        'stock_level': True,
        'label': '历史行情',
        'group': 'market',
        'show_completeness': True,
        'need_date': True,
        'stock_column': 'code',
        'supports_integrity_check': True,
        'order': 4,
    },
    'balance_sheet': {
        'table': 'saa_raw_balance_sheet',
        'date_column': 'report_date',
        'data_frequency': 'quarterly',
        'stock_level': True,
        'label': '资产负债表',
        'group': 'statement',
        'show_completeness': True,
        'need_date': True,
        'stock_column': 'code',
        'supports_integrity_check': True,
        'order': 5,
    },
    'income': {
        'table': 'saa_raw_income_statement',
        'date_column': 'report_date',
        'data_frequency': 'quarterly',
        'stock_level': True,
        'label': '利润表',
        'group': 'statement',
        'show_completeness': True,
        'need_date': True,
        'stock_column': 'code',
        'supports_integrity_check': True,
        'order': 6,
    },
    'cash_flow': {
        'table': 'saa_raw_cash_flow_statement',
        'date_column': 'report_date',
        'data_frequency': 'quarterly',
        'stock_level': True,
        'label': '现金流量表',
        'group': 'statement',
        'show_completeness': True,
        'need_date': True,
        'stock_column': 'code',
        'supports_integrity_check': True,
        'order': 7,
    },
    'main_business': {
        'table': 'saa_raw_main_business',
        'date_column': 'report_date',
        'data_frequency': 'yearly',
        'stock_level': True,
        'label': '主营业务',
        'group': 'other',
        'show_completeness': True,
        'need_date': True,
        'stock_column': 'code',
        'supports_integrity_check': True,
        'order': 8,
    },
    'capital': {
        'table': 'saa_capitals',
        'date_column': 'date',
        'data_frequency': 'yearly',
        'stock_level': True,
        'label': '股本变动',
        'group': 'other',
        'show_completeness': True,
        'need_date': True,
        'stock_column': 'code',
        'supports_integrity_check': True,
        'order': 9,
    },
    'dividend': {
        'table': 'saa_dividends',
        'date_column': 'report_date',
        'data_frequency': 'yearly',
        'stock_level': True,
        'label': '分红数据',
        'group': 'other',
        'show_completeness': True,
        'need_date': True,
        'stock_column': 'code',
        'supports_integrity_check': True,
        'order': 10,
    },
    'valuation_board': {
        'table': 'saa_board_valuation_levels',
        'date_column': 'date',
        'data_frequency': 'daily',
        'stock_level': False,
        'label': '板块估值',
        'group': 'valuation',
        'show_completeness': True,
        'need_date': True,
        'supports_integrity_check': True,
        'order': 11,
    },
    'valuation_industry': {
        'table': 'saa_industry_valuation_levels',
        'date_column': 'date',
        'data_frequency': 'daily',
        'stock_level': False,
        'label': '行业估值',
        'group': 'valuation',
        'show_completeness': True,
        'need_date': True,
        'supports_integrity_check': True,
        'order': 12,
    },
    # 新增数据类型 - 第二阶段实施
    'index_weights': {
        'table': 'saa_index_weights',
        'date_column': 'date',
        'data_frequency': 'quarterly',
        'stock_level': True,
        'label': '指数成分股权重',
        'group': 'industry',
        'show_completeness': True,
        'need_date': True,
        'stock_column': 'code',
        'supports_integrity_check': True,
        'order': 13,
    },
    'industries': {
        'table': 'saa_industries',
        'date_column': 'start_date',
        'data_frequency': None,
        'stock_level': False,
        'label': '行业信息',
        'group': 'industry',
        'show_completeness': False,
        'need_date': False,
        'supports_integrity_check': True,
        'order': 14,
    },
    'industry_stocks': {
        'table': 'saa_industry_stocks',
        'date_column': 'date',
        'data_frequency': 'monthly',
        'stock_level': True,
        'label': '行业股票关系',
        'group': 'industry',
        'show_completeness': True,
        'need_date': True,
        'stock_column': 'code',
        'supports_integrity_check': True,
        'order': 15,
    },
}

# 数据类型分组定义
DATA_TYPE_GROUPS = [
    {'key': 'market', 'label': '市场数据', 'order': 1},
    {'key': 'statement', 'label': '财务报表', 'order': 2},
    {'key': 'other', 'label': '其他数据', 'order': 3},
    {'key': 'valuation', 'label': '估值数据', 'order': 4},
    {'key': 'industry', 'label': '行业相关', 'order': 5},
]
```

#### 配置字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `table` | string | ✅ | 数据库表名 |
| `date_column` | string \| null | ✅ | 日期字段名 |
| `data_frequency` | string \| null | ✅ | 更新频率: daily/weekly/monthly/quarterly/yearly/null |
| `stock_level` | boolean | ✅ | 是否股票级别数据 |
| `label` | string | ✅ | 显示名称 |
| `group` | string | ✅ | 所属分组 |
| `show_completeness` | boolean | ✅ | 是否在仪表盘显示完整性 |
| `need_date` | boolean | ✅ | 采集时是否需要日期参数 |
| `stock_column` | string | ❌ | 股票代码字段名（stock_level=True时必填） |
| `supports_integrity_check` | boolean | ✅ | 是否支持完整性检查 |
| `order` | integer | ✅ | 排序序号 |

---

### 2. 后端API

#### 新增端点

**路径**: `GET /api/data-types/`  
**权限**: IsAuthenticated  
**功能**: 返回所有数据类型配置  

**文件**: `backend/saa_collector/views.py`

```python
class DataTypesConfigView(APIView):
    """
    返回所有数据类型配置
    
    这是系统的单一数据源，前端应该从此API获取所有数据类型信息
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        from .constants import DATA_TYPE_CONFIG, DATA_TYPE_GROUPS
        
        # 转换为前端需要的格式
        data_types = []
        for key, config in DATA_TYPE_CONFIG.items():
            data_types.append({
                'key': key,
                'label': config['label'],
                'table': config['table'],
                'frequency': config.get('data_frequency'),
                'stock_level': config.get('stock_level', True),
                'group': config.get('group'),
                'show_completeness': config.get('show_completeness', True),
                'need_date': config.get('need_date', True),
                'stock_column': config.get('stock_column'),
                'supports_integrity_check': config.get('supports_integrity_check', True),
                'order': config.get('order', 99),
            })
        
        # 按order排序
        data_types.sort(key=lambda x: x['order'])
        
        return Response({
            'data_types': data_types,
            'groups': sorted(DATA_TYPE_GROUPS, key=lambda x: x['order']),
        })
```

#### 路由配置

**文件**: `backend/saa_collector/urls.py`

```python
urlpatterns = [
    # ... 现有路由
    path('data-types/', views.DataTypesConfigView.as_view(), name='data-types-config'),
    # ...
]
```

#### 响应示例

```json
{
  "data_types": [
    {
      "key": "trade_days",
      "label": "交易日",
      "table": "saa_trade_days",
      "frequency": "daily",
      "stock_level": false,
      "group": "market",
      "show_completeness": false,
      "need_date": true,
      "stock_column": null,
      "supports_integrity_check": true,
      "order": 1
    },
    // ... 更多数据类型
  ],
  "groups": [
    {"key": "market", "label": "市场数据", "order": 1},
    {"key": "statement", "label": "财务报表", "order": 2},
    {"key": "other", "label": "其他数据", "order": 3},
    {"key": "valuation", "label": "估值数据", "order": 4},
    {"key": "industry", "label": "行业相关", "order": 5}
  ]
}
```

---

### 3. 前端架构

#### 3.1 全局数据类型管理

**新文件**: `frontend/src/composables/useDataTypes.ts`

```typescript
import { ref, computed } from 'vue'
import { fetchDataTypesConfig } from '@/utils/api'

export interface DataTypeConfig {
  key: string
  label: string
  table: string
  frequency?: string | null
  stock_level: boolean
  group?: string
  show_completeness: boolean
  need_date: boolean
  stock_column?: string
  supports_integrity_check: boolean
  order: number
}

export interface DataTypeGroup {
  key: string
  label: string
  order: number
}

// 全局状态（单例模式）
const dataTypes = ref<DataTypeConfig[]>([])
const groups = ref<DataTypeGroup[]>([])
const loaded = ref(false)
const loading = ref(false)

export function useDataTypes() {
  /**
   * 从API加载数据类型配置
   * 只加载一次，后续直接使用缓存
   */
  async function loadDataTypes(forceReload = false): Promise<void> {
    if (loaded.value && !forceReload) return
    if (loading.value) return
    
    loading.value = true
    try {
      const response = await fetchDataTypesConfig()
      dataTypes.value = response.data_types
      groups.value = response.groups
      loaded.value = true
    } catch (error) {
      console.error('Failed to load data types config:', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  /**
   * 按分组获取数据类型
   */
  const groupedDataTypes = computed(() => {
    const result: Record<string, DataTypeConfig[]> = {}
    for (const dt of dataTypes.value) {
      const group = dt.group || 'other'
      if (!result[group]) {
        result[group] = []
      }
      result[group].push(dt)
    }
    return result
  })

  /**
   * 获取数据类型的显示名称
   */
  function getLabel(key: string): string {
    return dataTypes.value.find(dt => dt.key === key)?.label || key
  }

  /**
   * 获取需要显示完整性的数据类型
   */
  const completenessTypes = computed(() => 
    dataTypes.value.filter(dt => dt.show_completeness)
  )

  /**
   * 获取支持完整性检查的数据类型
   */
  const integrityCheckTypes = computed(() =>
    dataTypes.value.filter(dt => dt.supports_integrity_check)
  )

  /**
   * 根据key获取完整配置
   */
  function getConfig(key: string): DataTypeConfig | undefined {
    return dataTypes.value.find(dt => dt.key === key)
  }

  /**
   * 获取某个分组的所有数据类型
   */
  function getTypesByGroup(groupKey: string): DataTypeConfig[] {
    return dataTypes.value.filter(dt => dt.group === groupKey)
  }

  return {
    // 状态
    dataTypes,
    groups,
    loaded,
    loading,
    
    // 计算属性
    groupedDataTypes,
    completenessTypes,
    integrityCheckTypes,
    
    // 方法
    loadDataTypes,
    getLabel,
    getConfig,
    getTypesByGroup,
  }
}
```

#### 3.2 API函数

**文件**: `frontend/src/utils/api.ts`

```typescript
/**
 * 获取数据类型配置
 * 这是系统的单一数据源
 */
export async function fetchDataTypesConfig(): Promise<{
  data_types: DataTypeConfig[]
  groups: DataTypeGroup[]
}> {
  const response = await fetch('/api/data-types/')
  if (!response.ok) {
    throw new Error(`Failed to fetch data types config: ${response.statusText}`)
  }
  return response.json()
}
```

#### 3.3 应用初始化

**文件**: `frontend/src/App.vue`

```typescript
import { useDataTypes } from '@/composables/useDataTypes'

const { loadDataTypes } = useDataTypes()

onMounted(async () => {
  // 应用启动时预加载数据类型配置
  try {
    await loadDataTypes()
  } catch (error) {
    console.error('Failed to load data types config on app startup:', error)
  }
})
```

#### 3.4 组件改造示例

##### DashboardView.vue

**改造前**:
```typescript
const EXPECTED_DATA_TYPES = [
  { data_type: 'trade_days', data_type_display: '交易日' },
  { data_type: 'stock_info', data_type_display: '股票基本信息', show_completeness: false },
  // ... 硬编码12个数据类型
]

const dataStatus = ref<DataStatus[]>(
  EXPECTED_DATA_TYPES.map(item => ({
    ...item,
    count: 0,
    // ...
  }))
)
```

**改造后**:
```typescript
import { useDataTypes } from '@/composables/useDataTypes'

const { completenessTypes, loadDataTypes } = useDataTypes()
const dataStatus = ref<DataStatus[]>([])

onMounted(async () => {
  await loadDataTypes()
  // 使用从API获取的配置
  dataStatus.value = completenessTypes.value.map(dt => ({
    data_type: dt.key,
    data_type_display: dt.label,
    count: 0,
    earliest_date: null,
    latest_date: null,
    frequency: dt.frequency,
    completeness: null,
    loading: true,
    error: false,
  }))
  
  // 加载实际数据...
})
```

##### IntegrityReportFilterPanel.vue

**改造前**:
```typescript
const dataTypes = [
  { value: 'trade_days', label: '交易日' },
  { value: 'quote', label: '最新行情' },
  // ... 硬编码10个
]
```

**改造后**:
```typescript
import { useDataTypes } from '@/composables/useDataTypes'

const { dataTypes, loadDataTypes, integrityCheckTypes } = useDataTypes()

onMounted(async () => {
  await loadDataTypes()
  // dataTypes 已经是 [{key, label, ...}] 格式
})

// 使用
<option v-for="dt in integrityCheckTypes" :key="dt.key" :value="dt.key">
  {{ dt.label }}
</option>
```

##### CollectorFilterPanel.vue

**改造前**:
```typescript
const dataTypes = [
  { value: 'trade_days', label: '交易日', needDate: true },
  { value: 'stock_info', label: '股票基本信息', needDate: false },
  // ... 硬编码10个
]
```

**改造后**:
```typescript
import { useDataTypes } from '@/composables/useDataTypes'

const { dataTypes, loadDataTypes } = useDataTypes()

onMounted(async () => {
  await loadDataTypes()
})

// 使用
<option v-for="dt in dataTypes" :key="dt.key" :value="dt.key">
  {{ dt.label }}
</option>

// need_date 属性从配置中获取
const currentDataTypeConfig = computed(() => 
  dataTypes.value.find(dt => dt.key === selectedDataType.value)
)

// 根据need_date决定是否显示日期选择器
<template v-if="currentDataTypeConfig?.need_date">
  <!-- 日期选择器 -->
</template>
```

---

## 实施计划

### 总体策略

**分两阶段实施**:
1. **阶段一**: 重构既有代码（回归测试通过）
2. **阶段二**: 新增3个数据类型

---

### 阶段一：重构既有代码

**目标**: 建立配置驱动架构，所有现有数据类型迁移到新架构

#### 任务清单

##### 后端任务 (预计 1-2 小时)

- [ ] **扩展配置** `backend/saa_collector/constants.py`
  - [ ] 为所有现有数据类型添加新字段 (group, show_completeness, need_date, order)
  - [ ] 创建 `DATA_TYPE_GROUPS` 常量
  - [ ] 确保所有12个现有数据类型配置完整

- [ ] **创建API** `backend/saa_collector/views.py`
  - [ ] 实现 `DataTypesConfigView` 类
  - [ ] 添加到 `urls.py` 路由
  - [ ] 测试API返回正确数据

- [ ] **重构现有代码** `backend/saa_collector/views.py`
  - [ ] 修改 `DataStatusView` 使用 `DATA_TYPE_CONFIG` 而非硬编码
  - [ ] 确保所有使用数据类型的地方都从配置读取

- [ ] **后端测试**
  - [ ] 测试 `/api/data-types/` API
  - [ ] 测试 `/api/data-status/` 仍正常工作
  - [ ] 确保后端单元测试通过

##### 前端任务 (预计 2-3 小时)

- [ ] **基础设施**
  - [ ] 创建 `frontend/src/composables/useDataTypes.ts`
  - [ ] 在 `frontend/src/utils/api.ts` 添加 `fetchDataTypesConfig()`
  - [ ] 在 `App.vue` 添加预加载逻辑

- [ ] **组件改造** (逐个改造，每个改造后立即测试)
  - [ ] 改造 `DashboardView.vue`
    - 删除 `EXPECTED_DATA_TYPES` 硬编码
    - 使用 `useDataTypes()` composable
  - [ ] 改造 `IntegrityReportFilterPanel.vue`
    - 删除 `dataTypes` 硬编码
    - 使用 `integrityCheckTypes`
  - [ ] 改造 `CollectorFilterPanel.vue`
    - 删除 `dataTypes` 硬编码
    - 使用 `need_date` 配置
  - [ ] 改造 `CollectPlansView.vue`
    - 删除 `dataTypeOptions` 硬编码
  - [ ] 改造 `CollectScheduleEditView.vue`
    - 删除 `dataTypeOptions` 硬编码
  - [ ] 改造 `DataBrowseTypeView.vue`
    - 删除 `DATA_TYPE_TO_TABLE` 硬编码
    - 使用配置中的 `table` 字段
  - [ ] 改造 `CollectSchedulesView.vue`
    - 删除 `dataTypeLabels` 硬编码
    - 使用 `getLabel()` 方法

##### 测试任务 (预计 1-2 小时)

- [ ] **前端测试**
  - [ ] 运行 `npm run type-check` - TypeScript类型检查
  - [ ] 运行 `npm run lint` - 代码风格检查
  - [ ] 运行 `npm run test:e2e` - 所有E2E测试
  - [ ] 手动测试所有页面:
    - [ ] 仪表盘页面 - 数据类型卡片显示
    - [ ] 完整性报告列表 - 数据类型筛选
    - [ ] 完整性报告详情 - 数据类型标签
    - [ ] 采集计划列表 - 数据类型选择
    - [ ] 采集计划详情 - 数据类型显示
    - [ ] 采集计划编辑 - 数据类型选择
    - [ ] 采集调度列表 - 数据类型显示
    - [ ] 数据浏览 - 数据类型切换
    - [ ] 数据检查 - 数据类型筛选

- [ ] **回归测试**
  - [ ] 确保所有41个E2E测试通过
  - [ ] 确保所有现有功能正常
  - [ ] 检查浏览器控制台无错误

##### 文档任务

- [ ] 更新 `AGENTS.md` 添加新架构说明
- [ ] 更新 README.md 如有需要

**阶段一完成标准**:
- ✅ 所有现有数据类型通过配置管理
- ✅ 前后端配置一致
- ✅ 所有测试通过
- ✅ 无功能回归

---

### 阶段二：新增3个数据类型

**前置条件**: 阶段一完成且回归测试通过

#### 任务清单

##### 后端任务 (预计 30 分钟)

- [ ] **更新配置** `backend/saa_collector/constants.py`
  - [ ] 添加 `index_weights` 配置（已在上一提交中添加，需更新group等字段）
  - [ ] 添加 `industries` 配置（已在上一提交中添加，需更新group等字段）
  - [ ] 添加 `industry_stocks` 配置（已在上一提交中添加，需更新group等字段）
  - [ ] 确保 `DATA_TYPE_GROUPS` 包含 `industry` 分组

- [ ] **验证**
  - [ ] 测试 `/api/data-types/` 返回新增的3个数据类型
  - [ ] 测试 `/api/data-status/` 包含新增数据类型

##### 前端任务 (预计 15 分钟)

- [ ] **验证自动生效**
  - [ ] 无需修改任何前端代码
  - [ ] 新数据类型自动出现在所有相关页面

- [ ] **前端mock数据** `frontend/src/utils/api.ts`
  - [ ] 检查 `generateMockHeatmapData` 已包含新数据类型（已在上一提交中完成）
  - [ ] 检查 `generateMockTypeBrowseData` 已包含新数据类型（已在上一提交中完成）
  - [ ] 检查 `DEFAULT_DISPLAY_CONFIGS` 已包含新数据类型（已在上一提交中完成）
  - [ ] 检查 `DATA_TYPE_GROUPS` 已包含新数据类型（已在上一提交中完成）

##### 测试任务 (预计 30 分钟)

- [ ] **功能测试**
  - [ ] 仪表盘页面显示3个新数据类型
  - [ ] 完整性报告可以选择新数据类型
  - [ ] 数据浏览可以查看新数据类型
  - [ ] 采集计划可以选择新数据类型

- [ ] **E2E测试**
  - [ ] 运行所有E2E测试确保通过
  - [ ] 如需要，为新数据类型添加专项测试

**阶段二完成标准**:
- ✅ 3个新数据类型在所有页面正常显示
- ✅ 所有测试通过
- ✅ 无需修改前端组件代码

---

## 预期效果

### 开发效率提升

#### 新增数据类型的流程对比

| 操作 | 改进前 | 改进后 |
|------|--------|--------|
| **修改文件数** | 7+ 个文件 | 1 个文件 |
| **所需时间** | 30+ 分钟 | 2 分钟 |
| **出错风险** | 高（易遗漏） | 低（单一配置） |
| **测试工作量** | 需测试7个页面 | 自动生效 |

#### 改进前流程

```
1. ❌ 修改 backend/constants.py - 添加配置
2. ❌ 修改 backend/views.py - DataStatusView硬编码列表
3. ❌ 修改 frontend/DashboardView.vue - EXPECTED_DATA_TYPES
4. ❌ 修改 frontend/IntegrityReportFilterPanel.vue - dataTypes
5. ❌ 修改 frontend/CollectorFilterPanel.vue - dataTypes
6. ❌ 修改 frontend/CollectPlansView.vue - dataTypeOptions
7. ❌ 修改 frontend/DataBrowseTypeView.vue - DATA_TYPE_TO_TABLE
8. ❌ 修改 frontend/CollectSchedulesView.vue - dataTypeLabels
9. ❌ 测试所有7个页面
10. ❌ 修复遗漏的问题
```

#### 改进后流程

```
1. ✅ 修改 backend/constants.py - 在DATA_TYPE_CONFIG中添加配置项
2. ✅ 完成！所有页面自动支持
```

### 架构优势

| 维度 | 改进前 | 改进后 | 提升 |
|------|--------|--------|------|
| **可维护性** | 低（7+处修改） | 高（1处配置） | ⬆️⬆️⬆️⬆️⬆️ |
| **一致性** | 差（易遗漏） | 优（单一数据源） | ⬆️⬆️⬆️⬆️⬆️ |
| **扩展性** | 差（硬编码） | 优（声明式） | ⬆️⬆️⬆️⬆️⬆️ |
| **出错概率** | 高 | 低 | ⬇️⬇️⬇️⬇️⬇️ |
| **开发效率** | 低（30分钟+） | 高（2分钟） | ⬆️⬆️⬆️⬆️⬆️ |
| **测试成本** | 高（7个页面） | 低（自动生效） | ⬇️⬇️⬇️⬇️⬇️ |

### 代码质量提升

#### 消除重复

- **改进前**: 数据类型定义在7+个地方重复
- **改进后**: 单一数据源，零重复

#### 类型安全

- **改进前**: 各处定义类型不一致，TypeScript难以检查
- **改进后**: 统一的 `DataTypeConfig` 接口，强类型保证

#### 可追溯性

- **改进前**: 不知道某个数据类型在哪些地方使用
- **改进后**: 通过API统一管理，易于追踪

### 未来扩展能力

#### 支持更多元数据

新架构可以轻松扩展配置字段：

```python
'index_weights': {
    # ... 现有字段
    'description': '指数成分股权重数据，季度更新',  # 新增：描述
    'icon': 'chart-pie',                           # 新增：图标
    'permission': 'data:industry:view',            # 新增：权限控制
    'enabled': True,                                # 新增：启用/禁用
    'tags': ['industry', 'index'],                 # 新增：标签
}
```

#### 支持动态配置

未来可以实现：
- 从数据库读取配置（运行时修改）
- 配置版本管理
- 配置审计日志
- A/B测试不同配置

#### 支持插件化

新架构为未来的插件化系统奠定基础：
- 第三方插件可以注册自己的数据类型
- 数据类型市场
- 动态加载/卸载

---

## 风险评估

### 技术风险

| 风险 | 等级 | 影响 | 缓解措施 |
|------|------|------|----------|
| API性能问题 | 低 | 中 | API轻量，可添加缓存 |
| 前端加载慢 | 低 | 低 | 在App.vue预加载 |
| 配置不一致 | 低 | 高 | 单一数据源 + 单元测试 |
| 破坏现有功能 | 中 | 高 | 分阶段实施 + 完整回归测试 |

### 项目风险

| 风险 | 等级 | 影响 | 缓解措施 |
|------|------|------|----------|
| 重构时间超预期 | 中 | 中 | 合理估算 + 缓冲时间 |
| 团队学习曲线 | 低 | 低 | 详细文档 + 代码示例 |
| 测试覆盖不足 | 中 | 高 | E2E测试 + 手动测试清单 |

### 应对策略

1. **分阶段实施**: 先重构，验证通过后再新增功能
2. **完整测试**: 41个E2E测试 + 手动测试清单
3. **可回滚**: 每个阶段独立提交，可随时回滚
4. **文档完善**: 详细文档 + 代码注释

---

## 成功标准

### 阶段一成功标准

- [ ] 后端 `/api/data-types/` API 正常工作
- [ ] 前端所有7个组件成功改造
- [ ] 所有41个E2E测试通过
- [ ] 所有现有功能正常（无回归）
- [ ] 代码审查通过
- [ ] TypeScript类型检查通过
- [ ] Lint检查通过

### 阶段二成功标准

- [ ] 3个新数据类型在后端配置中
- [ ] 前端自动识别新数据类型
- [ ] 所有页面正确显示新数据类型
- [ ] 所有E2E测试通过
- [ ] 无需修改前端组件代码

### 最终验收标准

- [ ] 新增数据类型只需修改1个文件
- [ ] 前后端配置完全一致
- [ ] 所有测试通过
- [ ] 文档完善
- [ ] 代码质量提升
- [ ] 开发效率显著提升

---

## 附录

### A. 配置字段完整说明

#### 必填字段

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `table` | string | 数据库表名 | `'saa_index_weights'` |
| `date_column` | string \| null | 日期字段名，无日期字段时为null | `'date'` 或 `null` |
| `data_frequency` | string \| null | 更新频率 | `'daily'`, `'monthly'`, `'quarterly'`, `'yearly'`, `null` |
| `stock_level` | boolean | 是否股票级别数据 | `true` 或 `false` |
| `label` | string | 中文显示名称 | `'指数成分股权重'` |
| `group` | string | 所属分组key | `'industry'` |
| `show_completeness` | boolean | 是否在仪表盘显示完整性 | `true` 或 `false` |
| `need_date` | boolean | 采集时是否需要日期参数 | `true` 或 `false` |
| `supports_integrity_check` | boolean | 是否支持完整性检查 | `true` 或 `false` |
| `order` | integer | 排序序号（越小越靠前） | `1`, `2`, `3`... |

#### 可选字段

| 字段 | 类型 | 说明 | 何时需要 |
|------|------|------|----------|
| `stock_column` | string | 股票代码字段名 | `stock_level=True` 时必填 |

### B. 数据类型分组定义

| Group Key | Label | Order | 包含的数据类型 |
|-----------|-------|-------|---------------|
| `market` | 市场数据 | 1 | trade_days, stock_info, quote, historical_quote |
| `statement` | 财务报表 | 2 | balance_sheet, income, cash_flow |
| `other` | 其他数据 | 3 | main_business, capital, dividend |
| `valuation` | 估值数据 | 4 | valuation_board, valuation_industry |
| `industry` | 行业相关 | 5 | index_weights, industries, industry_stocks |

### C. API响应示例

#### GET /api/data-types/

```json
{
  "data_types": [
    {
      "key": "trade_days",
      "label": "交易日",
      "table": "saa_trade_days",
      "frequency": "daily",
      "stock_level": false,
      "group": "market",
      "show_completeness": false,
      "need_date": true,
      "stock_column": null,
      "supports_integrity_check": true,
      "order": 1
    },
    {
      "key": "index_weights",
      "label": "指数成分股权重",
      "table": "saa_index_weights",
      "frequency": "quarterly",
      "stock_level": true,
      "group": "industry",
      "show_completeness": true,
      "need_date": true,
      "stock_column": "code",
      "supports_integrity_check": true,
      "order": 13
    }
  ],
  "groups": [
    {"key": "market", "label": "市场数据", "order": 1},
    {"key": "statement", "label": "财务报表", "order": 2},
    {"key": "other", "label": "其他数据", "order": 3},
    {"key": "valuation", "label": "估值数据", "order": 4},
    {"key": "industry", "label": "行业相关", "order": 5}
  ]
}
```

### D. 组件改造检查清单

每个组件改造后需要检查：

- [ ] 删除所有硬编码的数据类型列表
- [ ] 导入并使用 `useDataTypes()` composable
- [ ] 在 `onMounted` 中调用 `loadDataTypes()`
- [ ] 使用 `getLabel()` 获取显示名称
- [ ] 使用配置中的字段（如 `need_date`, `stock_level`）
- [ ] TypeScript类型正确
- [ ] 无控制台错误
- [ ] 功能正常工作
- [ ] E2E测试通过

---

## 变更历史

| 日期 | 版本 | 变更内容 | 作者 |
|------|------|----------|------|
| 2026-04-03 | 1.0 | 初始版本 | Claude |

---

## 审批

- [ ] 技术负责人审批
- [ ] 架构师审批
- [ ] 开始实施

---

**文档结束**
