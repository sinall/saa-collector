# 数据完整性检查与采集计划设计

## 概述

建立完整性检查 → 任务生成的完整工作流，实现：

1. 生成数据完整性报告，展示各类数据缺失情况
2. 基于报告勾选缺失项，生成采集计划
3. 编辑采集计划参数，选择执行策略
4. 执行并追踪采集进度

## 数据模型

### DataIntegrityReport（数据完整性报告）

```python
class DataIntegrityReport(models.Model):
    STATUS_CHOICES = [
        ('GENERATING', '生成中'),
        ('COMPLETED', '已完成'),
        ('FAILED', '失败'),
    ]
    
    STOCK_SCOPE_CHOICES = [
        ('ALL', '全部股票'),
        ('SELECTED', '选定股票'),
    ]
    
    id = models.BigAutoField(primary_key=True)
    name = models.CharField('报告名称', max_length=200)
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='GENERATING')
    stock_scope = models.CharField('股票范围', max_length=20, choices=STOCK_SCOPE_CHOICES, default='ALL')
    stock_codes = models.JSONField('股票列表', default=list)  # stock_scope=SELECTED 时使用
    date_start = models.DateField('开始日期')
    date_end = models.DateField('结束日期')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    completed_at = models.DateTimeField('完成时间', null=True, blank=True)
    
    class Meta:
        db_table = 'collector_data_integrity_report'
        ordering = ['-created_at']


class DataIntegrityItem(models.Model):
    id = models.BigAutoField(primary_key=True)
    report = models.ForeignKey(DataIntegrityReport, on_delete=models.CASCADE, related_name='items')
    data_type = models.CharField('数据类型', max_length=50)
    stock_code = models.CharField('股票代码', max_length=20)
    missing_periods = models.JSONField('缺失周期', default=list)
    selected = models.BooleanField('已选择', default=False)
    
    class Meta:
        db_table = 'collector_data_integrity_item'
```

### CollectPlan（采集计划）- 新增

```python
class CollectPlan(models.Model):
    STATUS_CHOICES = [
        ('PENDING', '待执行'),
        ('RUNNING', '执行中'),
        ('COMPLETED', '已完成'),
        ('FAILED', '失败'),
    ]
    
    EXECUTION_MODE_CHOICES = [
        ('PARALLEL', '并行执行'),
        ('SEQUENTIAL', '顺序执行'),
    ]
    
    id = models.BigAutoField(primary_key=True)
    name = models.CharField('计划名称', max_length=200)
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='PENDING')
    source_report = models.ForeignKey(DataIntegrityReport, on_delete=models.SET_NULL, null=True, blank=True, related_name='plans')
    execution_mode = models.CharField('执行模式', max_length=20, choices=EXECUTION_MODE_CHOICES, default='PARALLEL')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    started_at = models.DateTimeField('开始时间', null=True, blank=True)
    completed_at = models.DateTimeField('完成时间', null=True, blank=True)
    
    class Meta:
        db_table = 'collector_collect_plan'
        ordering = ['-created_at']
```

### CollectJob（采集作业）- 扩展

```python
# 现有字段保持不变，新增：
plan = models.ForeignKey(CollectPlan, on_delete=models.SET_NULL, null=True, blank=True, related_name='jobs')

# CollectJob 可独立使用（plan=null），也可归属计划
```

## API 设计

### DataIntegrityReport API

| 方法 | 路径 | 说明 |
|-----|------|------|
| POST | `/api/integrity-reports/` | 创建并开始生成报告 |
| GET | `/api/integrity-reports/` | 列出历史报告 |
| GET | `/api/integrity-reports/{id}/` | 获取报告详情（含 items） |
| PATCH | `/api/integrity-reports/{id}/items/` | 批量更新 selected 状态 |
| POST | `/api/integrity-reports/{id}/generate-plan/` | 从报告生成 CollectPlan |

**报告生成参数**（POST 请求体）：

```json
{
  "name": "2024年Q4完整性检查",
  "stock_scope": "all" | "selected",
  "stock_codes": ["000001", "000002"],  // stock_scope=selected 时必填
  "date_start": "2024-01-01",
  "date_end": "2024-12-31"
}
```

**进度轮询机制**：
- 前端创建报告后，每 3 秒轮询 `GET /api/integrity-reports/{id}/`
- 根据 `status` 字段判断是否完成
- 完成后停止轮询，展示报告详情

### CollectPlan API

| 方法 | 路径 | 说明 |
|-----|------|------|
| POST | `/api/collect-plans/` | 创建计划（可独立创建） |
| GET | `/api/collect-plans/` | 列出计划 |
| GET | `/api/collect-plans/{id}/` | 获取计划详情 |
| PATCH | `/api/collect-plans/{id}/` | 编辑计划（仅 PENDING 状态） |
| POST | `/api/collect-plans/{id}/execute/` | 开始执行计划 |
| DELETE | `/api/collect-plans/{id}/` | 删除计划（仅 PENDING 状态） |

## 前端页面

### 导航栏结构

```
├── 仪表盘
├── 数据检查          ← 现有，快速检查（暂保留）
├── 完整性报告        ← 新增，完整报告生成
├── 数据采集          ← 现有，即时采集
├── 采集计划          ← 新增，计划管理
└── 股票列表
```

### 页面路由

| 路由 | 说明 |
|-----|------|
| `/integrity-reports` | 报告列表页 |
| `/integrity-reports/{id}` | 报告详情页（可勾选、生成计划） |
| `/collect-plans` | 计划列表页 |
| `/collect-plans/new` | 新建计划页（可独立创建） |
| `/collect-plans/{id}` | 计划详情页（查看进度） |
| `/collect-plans/{id}/edit` | 计划编辑页 |

### 报告详情页交互

1. 显示各 data_type 分组统计
2. 每个缺失项可勾选
3. 底部"生成计划"按钮 → 跳转到计划编辑页，预填充数据

### 计划详情页交互

1. 显示计划状态和进度
2. 显示各 CollectJob 执行状态
3. PENDING 状态可编辑、执行
4. RUNNING/COMPLETED 状态只读

## 执行机制

### CollectPlan 执行流程

```
POST /api/collect-plans/{id}/execute/
    │
    ├── 检查 status = PENDING
    ├── 更新 status = RUNNING
    ├── 记录 started_at
    │
    ├── execution_mode = PARALLEL
    │       └── 并发执行所有 jobs（threading）
    │
    └── execution_mode = SEQUENTIAL
            └── 按顺序执行 jobs

每个 CollectJob 执行：
    └── 复用现有逻辑
        └── BaseCollectView 中的执行逻辑抽取为 CollectJobExecutor
```

### 与现有代码集成

1. **抽取 CollectJobExecutor service**
   - 从 `BaseCollectView` 抽取执行逻辑
   - 接收 CollectJob 实例，执行采集

2. **CollectPlan 执行器**
   - 调用 CollectJobExecutor 执行每个 job
   - 根据 execution_mode 决定并行或顺序

3. **现有手动触发 API**
   - 保持不变，仍可直接创建独立 CollectJob

## 与现有组件关系

| 现有组件 | 新设计中的角色 |
|---------|--------------|
| APScheduler + jobs/*.py | 保持不变，周期任务继续使用 |
| views.py 中的 Collect*View | 保持不变，兼容现有手动触发 |
| CompoundServiceFactory | 被 CollectJobExecutor 复用 |
| CollectJob 模型 | 扩展 plan 外键，向后兼容 |

## 实现步骤

### 阶段一：数据模型

1. 创建 DataIntegrityReport、DataIntegrityItem 模型
2. 创建 CollectPlan 模型
3. 扩展 CollectJob 模型（添加 plan 外键）
4. 执行数据库迁移

### 阶段二：后端 API

1. 实现 DataIntegrityReport API
2. 实现 CollectPlan API
3. 抽取 CollectJobExecutor service
4. 实现计划执行逻辑

### 阶段三：前端页面

1. 报告列表页、详情页
2. 计划列表页、详情页、编辑页
3. 页面间导航和状态同步

### 阶段四：集成测试

1. 完整工作流测试
2. 并行/顺序执行测试
3. 与现有功能兼容性测试
