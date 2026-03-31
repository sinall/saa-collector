# 数据库模型重构计划

## 背景

在"检查报告 → 修复计划 → 修复任务"链路中，筛选条件的设计需要权衡灵活性与类型安全。本文档分析两种方案并确定最终设计。

## 方案对比

### 一、DataIntegrityReport（检查报告）

筛选字段：`stock_scope`, `stock_codes`, `data_types`, `frequency`, `date_start`, `date_end`

| 维度 | 大 JSON (`filters`) | 拆分独立字段 |
|------|---------------------|-------------|
| 扩展性 | 加筛选条件只改前端，不改 model/migration | 每加一个条件都要加列、做 migration |
| 数据校验 | 需要自定义 serializer/validator 校验 JSON 结构 | Django model 的 `choices`、`DateField` 天然提供类型和值域校验 |
| 查询能力 | PostgreSQL 支持 JSON 查询，但语法啰嗦 | 标准 SQL，ORM 直接 `filter(frequency='monthly')` |
| 可读性 | 数据库直接看是一坨 JSON，不直观 | 每列独立，一眼看清 |
| "快照"语义 | 天然表达"这是一组生成时的条件快照" | 独立字段容易被误解为可变的业务状态 |

**判断：** Report 表的筛选条件是**一次性快照**，不会用来做列表过滤查询，数据量极小。JSON 方案扩展性优势明显，劣势几乎不体现。

### 二、CollectPlan（修复计划）

Plan 通过 `source_report` FK 关联 Report，筛选条件从 Report 继承，不需要单独存。两种方案对此表无实质差异。

### 三、CollectJob（修复任务）

当前字段：`data_type`, `symbols` (JSON), `params` (JSON)

| 维度 | 大 JSON (`config`，保留 `data_type` 独立) | 拆分独立字段 |
|------|------------------------------------------|-------------|
| 按 data_type 查询 | `data_type` 独立列，直接过滤 | 同左 |
| 不同 data_type 的参数差异 | JSON 天然适配 | 需要通用 `params` JSON 或大量可空列 |
| 从 Report/Plan 派生 | 从 `filters` JSON 提取，直接赋值 | 需要逐字段提取赋值 |

**判断：** 保留 `data_type` 独立用于查询过滤，其余参数合并为 `config` JSON。

### 四、综合结论

| 维度 | 大 JSON 方案 | 拆分独立字段方案 |
|------|-------------|-----------------|
| 开发效率 | 高。增减筛选条件只改前端和 validator | 低。每次都要 model + migration + serializer |
| 类型安全 | 弱。JSON 内字段无编译时类型检查 | 强。Django model field 提供类型约束 |
| 数据量 | 三张表数据量都极小，性能无差异 | 同左 |

**结论：推荐大 JSON 方案**。理由：
1. 筛选条件是"用户操作的快照记录"，不是"会被持续查询和修改的业务状态"
2. 三张表数据量都很小，JSON 查询性能劣势不存在
3. 筛选条件会演进，JSON 方案扩展成本为零
4. 链路传递简单：Report.filters → 提取子集 → Job.config

---

## 最终设计

### 1. DataIntegrityReport

**变更：**
- 删除字段：`stock_scope`, `stock_codes`, `data_types`, `frequency`, `date_start`, `date_end`
- 新增字段：`filters` (JSONField)

**filters JSON Schema：**
```json
{
  "stock_scope": "ALL",
  "stock_codes": ["000001", "600000"],
  "data_types": ["quote", "balance_sheet"],
  "frequency": "monthly",
  "date_start": "2023-01-01",
  "date_end": "2024-12-31"
}
```

### 2. DataIntegrityItem

**变更：**
- 删除字段：`missing_periods` (JSONField, list)
- 新增字段：`miss_period` (CharField, max_length=20)

**语义变化：** 一条缺失记录 = 一行。粒度从 (stock_code, data_type) 变为 (stock_code, data_type, miss_period)。

**好处：**
- 状态管理更清晰，一个缺失周期一个修复状态
- `selected` 和 `status` 不需要处理"部分修复"的复杂状态
- 前端操作更直观

### 3. CollectJob

**变更：**
- 删除字段：`symbols` (JSONField), `params` (JSONField)
- 新增字段：`config` (JSONField)
- 保留字段：`data_type` (独立列)

**config JSON Schema：**
```json
{
  "symbols": ["000001", "600000"],
  "start_date": "2024-01-01",
  "end_date": "2024-12-31"
}
```

---

## 实施步骤

### 1. 执行数据库 SQL（手动）

```sql
-- ============================================
-- 1. collector_data_integrity_report 表
-- ============================================
-- 新增 filters 字段
ALTER TABLE collector_data_integrity_report ADD COLUMN filters JSON DEFAULT (JSON_OBJECT());

-- 迁移旧数据到 filters（可选，如果需要保留旧数据）
UPDATE collector_data_integrity_report
SET filters = JSON_OBJECT(
    'stock_scope', stock_scope,
    'stock_codes', stock_codes,
    'data_types', data_types,
    'frequency', frequency,
    'date_start', date_start,
    'date_end', date_end
);

-- 删除旧字段
ALTER TABLE collector_data_integrity_report DROP COLUMN stock_scope;
ALTER TABLE collector_data_integrity_report DROP COLUMN stock_codes;
ALTER TABLE collector_data_integrity_report DROP COLUMN data_types;
ALTER TABLE collector_data_integrity_report DROP COLUMN frequency;
ALTER TABLE collector_data_integrity_report DROP COLUMN date_start;
ALTER TABLE collector_data_integrity_report DROP COLUMN date_end;

-- ============================================
-- 2. collector_data_integrity_item 表
-- ============================================
-- 新增 miss_period 字段
ALTER TABLE collector_data_integrity_item ADD COLUMN miss_period varchar(20);

-- 注意：missing_periods 到 miss_period 的迁移需要展开
-- 旧的一条记录可能变成多条，这里只提供清空重建的方案
-- 如果需要保留数据，需要写脚本处理

-- 删除旧字段
ALTER TABLE collector_data_integrity_item DROP COLUMN missing_periods;

-- ============================================
-- 3. collector_collect_job 表
-- ============================================
-- 新增 config 字段
ALTER TABLE collector_collect_job ADD COLUMN config JSON DEFAULT (JSON_OBJECT());

-- 迁移旧数据到 config（可选）
UPDATE collector_collect_job
SET config = JSON_OBJECT(
    'symbols', symbols,
    'params', params
);

-- 删除旧字段
ALTER TABLE collector_collect_job DROP COLUMN symbols;
ALTER TABLE collector_collect_job DROP COLUMN params;
```

### 2. 修改 `backend/saa_collector/models.py`

### 3. 修改对应的 serializer 和 viewset

### 4. 修改前端相关组件

### 5. 运行测试验证
