# 完整度报告「按范围修复」功能设计

## 1. 背景与问题

### 1.1 现状

完整度检查报告（`DataIntegrityReport`）生成后，会产生大量缺失项（`DataIntegrityItem`）。每条 item 对应一只股票的某个数据类型，包含一个 `missing_periods` 数组（可能有多个缺失周期）。

当前修复流程：
1. 用户在扁平表格中浏览缺失项（表格展开 `missing_periods` 为逐行显示）
2. 通过筛选 + "全选筛选"批量勾选
3. 点击"生成采集计划"，后端 `filter(selected=True)` 加载所有选中项到内存，按 `data_type` 分组生成 `CollectJob`

### 1.2 性能瓶颈

| 环节 | 问题 |
|------|------|
| 后端详情接口 `_flatten_items()` | 遍历所有 items 并展开 `missing_periods` 到内存，再做 Python 层分页。数据量大时内存和响应慢 |
| 前端选择体验 | 用户在扁平表格中翻页勾选，几万条缺失项时操作繁琐 |
| 生成计划接口 `generate-plan` | 一次性加载所有 `selected=True` 的记录到内存遍历分组 |
| 前后端传输 | 如果改为传 ID 列表，几万个 ID 的请求体本身就是问题 |

### 1.3 数据规模估算

以全市场检查为例：
- 约 5000 只股票 x 7 种数据类型 = 最多 35,000 条 `DataIntegrityItem`
- 每条 item 的 `missing_periods` 可能有几十到几百个周期
- 展开后的扁平行数可达数十万

## 2. 设计目标

1. **按维度范围修复**：用户通过选择"数据类型 + 时间范围 + 股票范围"定义修复范围，而非逐条勾选
2. **后端按条件查询**：接收维度参数（非 ID 列表），直接用 SQL WHERE 条件匹配缺失项
3. **保留现有功能**：扁平表格浏览、筛选、分页等现有功能不受影响，作为查看明细的补充

## 3. 交互设计

### 3.1 入口

在报告详情页头部操作区，新增「按范围修复」按钮，点击打开右侧 Drawer（抽屉面板）。

### 3.2 Drawer 布局

```
+---------------------------------------------+
|  按范围生成采集计划                     [关闭] |
+---------------------------------------------+
|                                             |
|  # 数据类型                                 |
|  [全选] [反选]                               |
|  [x] 历史行情 (3,200)    [x] 利润表 (1,500) |
|  [x] 资产负债表 (1,200)  [ ] 现金流量表 (800)|
|  [ ] 分红数据 (600)      [ ] 主营业务 (400)  |
|  [ ] 股本变动 (200)      [ ] 最新行情 (150)  |
|  [ ] 交易日 (50)                             |
|                                             |
|  # 时间范围                                  |
|  > [ ] 2024 (1,200)                         |
|  v [x] 2023 (800)                           |
|    > [x] Q1 (200)                           |
|    v [x] Q2 (250)                           |
|      [x] 4月 (80)                           |
|      [x] 5月 (85)                           |
|      [x] 6月 (85)                           |
|    > [ ] Q3 (180)                           |
|    > [ ] Q4 (170)                           |
|  > [ ] 2022 (600)                           |
|  ...                                        |
|                                             |
|  # 股票范围                                  |
|  (o) 全部有缺失的股票 (450只)                |
|  ( ) 指定股票                                |
|    [搜索股票代码...]                         |
|    600001 x  600002 x  000001 x             |
|                                             |
+---------------------------------------------+
|  预估：约 2,300 条缺失项 -> 2 个采集任务     |
|                        [取消]  [生成采集计划]  |
+---------------------------------------------+
```

### 3.3 三个维度的设计考量

#### 数据类型（Checkbox Group）

- 使用 `el-checkbox-group`，每个选项显示缺失数量
- 支持「全选」「反选」快捷按钮
- 节点数固定可控（约 10 个数据类型）
- **数据来源**：summary 接口的 `by_data_type` 字段

#### 时间范围（El-Tree，年->季度->月）

- 使用 `el-tree` 组件，`show-checkbox` 启用级联勾选
- 三级层次：年 -> 季度（Q1/Q2/Q3/Q4）-> 月
- 每个节点显示该范围内的缺失数量
- 节点数可控：10 年 x (1 + 4 + 12) = 约 170 个节点
- **为什么不把日展开**：按天频率 10 年有约 2,500 个交易日，节点太多。月是最细粒度，选中"3月"后端用日期范围 `2024-03-01 ~ 2024-03-31` 匹配
- **级联选择**：勾选"2024年"自动选中所有季度和月份；勾选"Q1"自动选中 1/2/3 月
- **数据来源**：summary 接口的 `by_period` 字段

#### 股票范围（Radio + 搜索）

- 默认"全部有缺失的股票"（最常用场景）
- 可选"指定股票"，通过搜索框添加
- **不做树节点**：股票数量不可控（可达数千），不适合树形展示
- 指定股票时，搜索框支持模糊搜索，已选股票以标签形式展示

### 3.4 联动逻辑

```
数据类型变化 --> 重新请求 summary（传 data_types 参数）
                    |-- 更新日期树的缺失数量
                    +-- 更新底部预估数字

股票范围变化 --> 重新请求 summary（传 stock_codes 参数）
                    |-- 更新数据类型的缺失数量
                    |-- 更新日期树的缺失数量
                    +-- 更新底部预估数字

日期树勾选变化 --> 前端计算已选月份的缺失数量之和
                    +-- 更新底部预估数字
```

**注意**：数据类型和股票范围变化时需要请求后端重新统计；日期树勾选变化只需前端累加已有数字，不需要额外请求。

### 3.5 生成采集计划流程

```
用户点击「生成采集计划」
    |
    |-- 前端验证：至少选了一个数据类型 + 一个时间节点
    |
    |-- 弹出确认对话框："确定生成？预估影响 2,300 条缺失项"
    |
    |-- POST /integrity-reports/{id}/generate-plan-by-range/
    |       请求体：{ data_types, periods, stock_scope, stock_codes }
    |
    |-- 后端按条件查询匹配的 DataIntegrityItem
    |       按 data_type 分组创建 CollectJob
    |
    +-- 成功后跳转到计划编辑页 /collect-plans/{id}/edit
```

## 4. 后端 API 设计

### 4.1 分组统计接口

```
GET /api/integrity-reports/{id}/summary/
```

**请求参数**（Query String，均可选）：

| 参数 | 类型 | 说明 |
|------|------|------|
| data_types | string | 逗号分隔的数据类型，如 `income,balance_sheet` |
| stock_codes | string | 逗号分隔的股票代码，如 `600001,600002` |
| status | string | 修复状态筛选：`PENDING` / `FIXED`，默认 `PENDING` |

**响应**：

```json
{
  "success": true,
  "data": {
    "by_data_type": [
      {
        "data_type": "historical_quote",
        "label": "历史行情",
        "missing_count": 3200,
        "stock_count": 450
      },
      {
        "data_type": "income",
        "label": "利润表",
        "missing_count": 1500,
        "stock_count": 320
      }
    ],
    "by_period": [
      {
        "year": 2024,
        "missing_count": 1200,
        "quarters": [
          {
            "quarter": 1,
            "missing_count": 350,
            "months": [
              { "month": 1, "missing_count": 120 },
              { "month": 2, "missing_count": 110 },
              { "month": 3, "missing_count": 120 }
            ]
          },
          {
            "quarter": 2,
            "missing_count": 300,
            "months": [
              { "month": 4, "missing_count": 100 },
              { "month": 5, "missing_count": 100 },
              { "month": 6, "missing_count": 100 }
            ]
          }
        ]
      },
      {
        "year": 2023,
        "missing_count": 800,
        "quarters": [...]
      }
    ],
    "total_missing": 8500,
    "total_stocks": 450
  }
}
```

**实现要点**：

1. 查询 `DataIntegrityItem` 按 `data_type` 分组统计（SQL `GROUP BY`）
2. 遍历匹配的 items，解析 `missing_periods` JSON 数组中的周期字符串，提取年/月信息进行聚合
3. `missing_periods` 的格式根据报告的 frequency 不同：

| frequency | 格式示例 | 解析方式 |
|-----------|---------|---------|
| daily | `"2024-03-15"` | 提取年月，归入对应月份 |
| weekly | `"2024-W12"` | 将周数映射到月份 |
| monthly | `"2024-03"` | 直接用 |
| quarterly | `"2024-Q1"` | 映射到对应的 3 个月 |
| yearly | `"2024"` | 映射到 12 个月 |

4. 按年->季度->月层级聚合统计

### 4.2 按范围生成计划接口

```
POST /api/integrity-reports/{id}/generate-plan-by-range/
```

**请求体**：

```json
{
  "data_types": ["income", "balance_sheet"],
  "periods": ["2024-01", "2024-02", "2023-04", "2023-05", "2023-06"],
  "stock_scope": "ALL",
  "stock_codes": []
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| data_types | string[] | 是 | 选中的数据类型列表 |
| periods | string[] | 是 | 选中的月份列表，格式统一为 `YYYY-MM` |
| stock_scope | string | 是 | `ALL`（全部有缺失的股票）或 `SELECTED`（指定股票） |
| stock_codes | string[] | 条件必填 | `stock_scope=SELECTED` 时提供 |

**前端传参说明**：

日期树中用户可能勾选的是年、季度或月节点。前端在提交时，统一展开为月份列表：
- 勾选"2024年" -> `["2024-01", "2024-02", ..., "2024-12"]`
- 勾选"Q1" -> `["2024-01", "2024-02", "2024-03"]`
- 勾选"3月" -> `["2024-03"]`

**响应**：

```json
{
  "success": true,
  "data": {
    "id": 123,
    "name": "来自报告: xxx（按范围修复）",
    "jobs_count": 2
  }
}
```

**后端实现逻辑**：

```python
def post(self, request, pk):
    report = get_object_or_404(DataIntegrityReport, pk=pk)

    data_types = request.data['data_types']
    periods = request.data['periods']        # ["2024-01", "2024-02", ...]
    stock_scope = request.data['stock_scope']
    stock_codes = request.data.get('stock_codes', [])

    # 1. 按条件查询匹配的 DataIntegrityItem
    items_qs = DataIntegrityItem.objects.filter(
        report=report,
        data_type__in=data_types,
        status='PENDING'
    )

    if stock_scope == 'SELECTED' and stock_codes:
        items_qs = items_qs.filter(stock_code__in=stock_codes)

    # 2. 遍历 items，筛选出 missing_periods 与选中月份有交集的项
    #    按 data_type 分组，收集 stock_codes 和匹配的 periods
    selected_months = set(periods)
    data_type_groups = {}

    for item in items_qs.iterator():
        matched = match_periods(item.missing_periods, selected_months, report.frequency)
        if not matched:
            continue

        if item.data_type not in data_type_groups:
            data_type_groups[item.data_type] = {
                'stock_codes': set(),
                'periods': set()
            }
        if item.stock_code:
            data_type_groups[item.data_type]['stock_codes'].add(item.stock_code)
        data_type_groups[item.data_type]['periods'].update(matched)

    # 3. 创建 CollectPlan 和 CollectJob
    plan = CollectPlan.objects.create(
        name=f"来自报告: {report.name}（按范围修复）",
        source_report=report,
        execution_mode='PARALLEL'
    )

    for data_type, info in data_type_groups.items():
        sorted_periods = sorted(info['periods'])
        CollectJob.objects.create(
            plan=plan,
            data_type=data_type,
            symbols=list(info['stock_codes']),
            params={
                'start_date': sorted_periods[0],
                'end_date': sorted_periods[-1],
            },
            status='PENDING'
        )

    return Response({'success': True, 'data': {...}})
```

**`match_periods` 函数的匹配逻辑**：

根据 report 的 frequency，将 `missing_periods` 中的每个值映射到月份，然后检查是否在用户选中的月份中。

```python
def period_to_months(period, frequency):
    """
    将 period 字符串映射到 YYYY-MM 格式的集合。
    一个 period 可能对应多个月（如 quarterly, yearly）。
    """
    if frequency == 'daily':
        # "2024-03-15" -> {"2024-03"}
        return {period[:7]}
    elif frequency == 'weekly':
        # "2024-W12" -> 计算该周属于哪个月
        year, week = int(period[:4]), int(period[6:])
        from datetime import date, timedelta
        d = date(year, 1, 1) + timedelta(weeks=week - 1)
        return {f"{d.year}-{d.month:02d}"}
    elif frequency == 'monthly':
        # "2024-03" -> {"2024-03"}
        return {period}
    elif frequency == 'quarterly':
        # "2024-Q1" -> {"2024-01", "2024-02", "2024-03"}
        year, q = int(period[:4]), int(period[-1])
        start_month = (q - 1) * 3 + 1
        return {f"{year}-{m:02d}" for m in range(start_month, start_month + 3)}
    elif frequency == 'yearly':
        # "2024" -> {"2024-01", ..., "2024-12"}
        year = int(period)
        return {f"{year}-{m:02d}" for m in range(1, 13)}
    return set()


def match_periods(missing_periods, selected_months, frequency):
    """
    返回 missing_periods 中与 selected_months 有交集的原始 period 值。
    """
    matched = []
    for period in missing_periods:
        period_months = period_to_months(period, frequency)
        if period_months & selected_months:  # 集合交集
            matched.append(period)
    return matched
```

### 4.3 URL 配置

```python
# backend/saa_collector/urls.py 新增
path('integrity-reports/<int:pk>/summary/',
     views.DataIntegrityReportSummaryView.as_view(),
     name='integrity-report-summary'),

path('integrity-reports/<int:pk>/generate-plan-by-range/',
     views.DataIntegrityReportGeneratePlanByRangeView.as_view(),
     name='integrity-report-generate-plan-by-range'),
```

## 5. 前端设计

### 5.1 文件结构

```
frontend/src/
|-- components/
|   +-- RangeRepairDrawer.vue      # 新增：按范围修复抽屉组件
|-- views/
|   +-- IntegrityReportDetailView.vue  # 修改：添加入口按钮
+-- utils/
    +-- api.ts                      # 修改：添加新接口
```

### 5.2 RangeRepairDrawer 组件

**Props**：

```typescript
interface Props {
  visible: boolean            // 控制 Drawer 显示
  reportId: number            // 报告 ID
  reportFrequency: string     // 报告频率（daily/monthly/quarterly/yearly）
}
```

**Events**：

```typescript
emit('update:visible', boolean)  // 关闭 Drawer
emit('plan-created', planId)     // 计划创建成功
```

**内部状态**：

```typescript
// summary 数据
const summaryData = ref<SummaryData | null>(null)
const summaryLoading = ref(false)

// 数据类型选择
const selectedDataTypes = ref<string[]>([])

// 日期树
const periodTreeData = ref<TreeNode[]>([])
const checkedPeriodKeys = ref<string[]>([])

// 股票范围
const stockScope = ref<'ALL' | 'SELECTED'>('ALL')
const selectedStocks = ref<string[]>([])

// 预估
const estimatedCount = computed(() => { ... })

// 生成中
const generating = ref(false)
```

### 5.3 日期树数据结构

后端 `by_period` 返回的数据转换为 El-Tree 所需的 `TreeNode` 格式：

```typescript
interface PeriodTreeNode {
  id: string          // "2024" | "2024-Q1" | "2024-01"
  label: string       // "2024年" | "Q1" | "1月"
  count: number       // 缺失数量
  children?: PeriodTreeNode[]
}

// 转换函数
function buildPeriodTree(byPeriod: PeriodYearData[]): PeriodTreeNode[] {
  return byPeriod.map(year => ({
    id: `${year.year}`,
    label: `${year.year}年`,
    count: year.missing_count,
    children: year.quarters.map(q => ({
      id: `${year.year}-Q${q.quarter}`,
      label: `Q${q.quarter}`,
      count: q.missing_count,
      children: q.months.map(m => ({
        id: `${year.year}-${String(m.month).padStart(2, '0')}`,
        label: `${m.month}月`,
        count: m.missing_count,
      }))
    }))
  }))
}
```

### 5.4 提交时的 periods 展开逻辑

El-Tree 勾选的节点可能是年、季度或月。提交时统一展开为月份列表：

```typescript
function expandCheckedToMonths(checkedKeys: string[]): string[] {
  const months = new Set<string>()

  for (const key of checkedKeys) {
    if (/^\d{4}$/.test(key)) {
      // 年节点 "2024" -> 12个月
      for (let m = 1; m <= 12; m++) {
        months.add(`${key}-${String(m).padStart(2, '0')}`)
      }
    } else if (/^\d{4}-Q\d$/.test(key)) {
      // 季度节点 "2024-Q1" -> 3个月
      const year = key.slice(0, 4)
      const q = parseInt(key.slice(6))
      const startMonth = (q - 1) * 3 + 1
      for (let m = startMonth; m < startMonth + 3; m++) {
        months.add(`${year}-${String(m).padStart(2, '0')}`)
      }
    } else if (/^\d{4}-\d{2}$/.test(key)) {
      // 月节点 "2024-01"
      months.add(key)
    }
  }

  return Array.from(months).sort()
}
```

**注意**：El-Tree 在 `check-strictly=false` 模式下，`getCheckedKeys` 会返回所有勾选的叶子和半选的父节点。为避免重复展开，提交时只取叶子节点（月份级别）即可，或用 `expandCheckedToMonths` 对所有层级做去重展开。

### 5.5 详情页集成

在 `IntegrityReportDetailView.vue` 中：

```vue
<!-- 头部操作区新增按钮 -->
<el-button
  type="success"
  @click="rangeRepairVisible = true"
  :disabled="report?.status !== 'COMPLETED'"
>
  按范围修复
</el-button>

<!-- Drawer 组件 -->
<RangeRepairDrawer
  v-model:visible="rangeRepairVisible"
  :report-id="parseInt(props.id)"
  :report-frequency="report?.frequency || 'monthly'"
  @plan-created="onPlanCreated"
/>
```

### 5.6 API 层新增

```typescript
// api.ts

// Summary 响应类型
interface IntegrityReportSummary {
  by_data_type: Array<{
    data_type: string
    label: string
    missing_count: number
    stock_count: number
  }>
  by_period: Array<{
    year: number
    missing_count: number
    quarters: Array<{
      quarter: number
      missing_count: number
      months: Array<{
        month: number
        missing_count: number
      }>
    }>
  }>
  total_missing: number
  total_stocks: number
}

// 获取分组统计
export const fetchIntegrityReportSummary = async (
  reportId: number,
  params?: {
    data_types?: string
    stock_codes?: string
    status?: string
  }
): Promise<ApiResponse<IntegrityReportSummary>> => {
  const response = await api.get(
    `/integrity-reports/${reportId}/summary/`,
    { params }
  )
  return response.data
}

// 按范围生成采集计划
export const generatePlanByRange = async (
  reportId: number,
  params: {
    data_types: string[]
    periods: string[]
    stock_scope: 'ALL' | 'SELECTED'
    stock_codes?: string[]
  }
): Promise<ApiResponse<{ id: number; name: string; jobs_count: number }>> => {
  const response = await api.post(
    `/integrity-reports/${reportId}/generate-plan-by-range/`,
    params
  )
  return response.data
}
```

## 6. 实现计划

### Phase 1: 后端接口

1. 实现 `DataIntegrityReportSummaryView`
   - 按 `data_type` 分组统计
   - 解析 `missing_periods`，按年->季度->月聚合
   - 支持 `data_types`、`stock_codes`、`status` 筛选参数

2. 实现 `DataIntegrityReportGeneratePlanByRangeView`
   - 接收维度参数
   - 匹配缺失项并按 `data_type` 分组
   - 创建 `CollectPlan` 和 `CollectJob`

3. 注册 URL 路由

### Phase 2: 前端组件

4. 创建 `RangeRepairDrawer.vue`
   - 数据类型 Checkbox Group
   - 日期树（El-Tree）
   - 股票范围选择
   - 预估统计 + 生成按钮

5. `api.ts` 添加 `fetchIntegrityReportSummary` 和 `generatePlanByRange`

6. `IntegrityReportDetailView.vue` 添加入口按钮和 Drawer 引用

### Phase 3: 测试验证

7. Playwright 测试：Drawer 打开/关闭、维度选择、生成计划流程
8. 手动验证：大数据量下的 summary 接口性能

## 7. 不改动的部分

- 现有扁平表格浏览、筛选、分页功能（保留作为查看明细的方式）
- 现有的"全选筛选 -> 生成采集计划"流程（保留作为精细操作的备选）
- 热力图
- `DataIntegrityItem` 模型结构
