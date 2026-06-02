# 数据完整度计算模块设计文档

> 历史设计文档。当前数据类型配置与完整度计算规则见 `../../openspec/specs/collector-data-configuration/spec.md`。
>
> 2026-06 更新：本文早期将多数数据统一抽象为“有数据股票数 / 应有股票数”。当前规则已改为按 `completeness_model` 区分交易日、证券主数据快照、周期性证券数据、事件型证券数据和非证券周期数据。尤其是分红等不定时事件不再按“每只股票每年都应有记录”计算缺失。

## 1. 背景

当前系统中存在两个热力图功能需要计算数据完整度：
1. **仪表盘热力图** (`DataCompletenessHeatmapView`)：展示全局数据完整度
2. **完整度报告热力图** (`DataIntegrityReportHeatmapView`)：展示特定报告的数据完整度

两边的计算逻辑存在重复代码，且计算方式不够准确。

## 2. 当前问题

### 2.1 仪表盘热力图
```python
# 用最大记录数作为分母
max_count = max(period_counts.values())
completeness = count / max_count
```
**问题**：早期 period（如 2020-01）的完整度被低估，因为当时上市股票数较少。

### 2.2 完整度报告热力图
```python
# 用固定总股票数作为分母
completeness = 1 - (missing / total_stocks)
```
**问题**：同样，早期 period 的分母应该更小。

### 2.3 代码重复
两边有大量重复的 `_generate_periods`、`_convert_date_to_period`、`_get_period_range` 等方法。

## 3. 设计目标

1. **准确性**：每个 period 的分母应该是该时间点已上市的股票数
2. **复用性**：一个计算模块同时服务仪表盘和完整度报告
3. **灵活性**：支持不同的数据类型、频率、股票范围

## 4. 计算逻辑

### 4.1 核心公式

```
完整度 = 有数据股票数 / 应有股票数

其中：
- 有数据股票数（分子）：从数据表查询 COUNT(DISTINCT symbol)
- 应有股票数（分母）：从 saa_stocks 统计 listing_time <= period 的股票数
```

### 4.2 特殊情况处理

| 情况 | 返回值 | 颜色 | 说明 |
|------|--------|------|------|
| 无数据（分母=0 或 数据表无记录） | -1 | 灰色 | 不适用 |
| 完整度 100% | 1.0 | 深绿 | 完整 |
| 完整度 0% | 0.0 | 红色 | 完全缺失 |
| 完整度 50% | 0.5 | 黄绿 | 部分缺失 |

### 4.3 数据类型分类

| 类型 | 分类 | 处理方式 |
|------|------|----------|
| trade_days | 非股票级别 | 单独逻辑，检查是否存在交易日数据 |
| stock_info | 非时间序列 | 恒定 1.0 或 -1 |
| quote | 非周期性（最新） | 只显示最新交易日的完整度 |
| historical_quote, balance_sheet, income, cash_flow, main_business, capital, dividend | 股票级别周期性 | 使用核心公式 |

## 5. 接口设计

### 5.1 完整度计算器类

```python
# backend/saa_collector/completeness.py

class CompletenessCalculator:
    """数据完整度计算器"""
    
    # 数据类型配置
    DATA_TYPE_CONFIG = {
        'trade_days': {
            'table': 'saa_trade_days',
            'date_column': 'date',
            'data_frequency': 'daily',
            'stock_level': False,  # 非股票级别
        },
        'historical_quote': {
            'table': 'saa_prices',
            'date_column': 'date',
            'data_frequency': 'daily',
            'stock_level': True,
        },
        'balance_sheet': {
            'table': 'saa_raw_balance_sheet',
            'date_column': 'date',
            'data_frequency': 'quarterly',
            'stock_level': True,
        },
        # ... 其他数据类型
    }
    
    def __init__(self, frequency: str, stock_codes: list = None, date_end: date = None):
        """
        初始化计算器
        
        Args:
            frequency: 显示频率 (daily/weekly/monthly/quarterly/yearly)
            stock_codes: 股票范围，None 表示全部股票
            date_end: 截止日期，用于筛选上市股票
        """
        pass
    
    def calculate(self, data_type: str, periods: list) -> dict:
        """
        计算指定数据类型的完整度
        
        Args:
            data_type: 数据类型
            periods: 周期列表
            
        Returns:
            {
                'periods': [...],
                'values': [...],  # -1 表示不适用，0-1 表示完整度
            }
        """
        pass
    
    def calculate_all(self, data_types: list, periods: list) -> dict:
        """
        批量计算多个数据类型的完整度
        
        Returns:
            {
                'periods': [...],
                'matrix': {data_type: [values...]}
            }
        """
        pass
```

### 5.2 使用示例

```python
# 仪表盘使用
calculator = CompletenessCalculator(frequency='monthly')
result = calculator.calculate_all(
    data_types=['historical_quote', 'balance_sheet', 'income'],
    periods=['2020-01', '2020-02', ...]
)

# 完整度报告使用
calculator = CompletenessCalculator(
    frequency=report.frequency,
    stock_codes=report.stock_codes,  # 可能是部分股票
    date_end=report.date_end
)
result = calculator.calculate_all(
    data_types=['historical_quote', 'balance_sheet'],
    periods=generate_periods(report.date_start, report.date_end, report.frequency)
)
```

## 6. 实现细节

### 6.1 计算每个 period 的应有股票数

```python
def _get_stocks_count_by_period(self, periods: list) -> dict:
    """
    计算每个 period 应有的股票数（分母）
    
    Returns:
        {'2020-01': 3000, '2020-02': 3010, ...}
    """
    with connection.cursor() as cursor:
        # 查询所有股票的上市日期
        if self.stock_codes:
            cursor.execute("""
                SELECT listing_time FROM saa_stocks
                WHERE symbol IN %s AND listing_time IS NOT NULL
            """, [self.stock_codes])
        else:
            cursor.execute("""
                SELECT listing_time FROM saa_stocks
                WHERE listing_time IS NOT NULL
            """)
        
        listing_dates = [row[0] for row in cursor.fetchall()]
    
    result = {}
    for period in periods:
        period_start = self._get_period_start_date(period)
        count = sum(1 for d in listing_dates if d <= period_start)
        result[period] = count
    
    return result
```

### 6.2 计算每个 period 的有数据股票数

```python
def _get_data_count_by_period(self, table: str, date_column: str, periods: list) -> dict:
    """
    计算每个 period 有数据的股票数（分子）
    
    Returns:
        {'2020-01': 2900, '2020-02': 2950, ...}
    """
    start_date, end_date = self._get_period_range(periods[0], periods[-1])
    date_format = self._get_date_format(self.frequency)
    
    stock_filter = ""
    params = [date_format, start_date, end_date, date_format]
    if self.stock_codes:
        stock_filter = "AND symbol IN %s"
        params.insert(3, self.stock_codes)
    
    with connection.cursor() as cursor:
        cursor.execute(f"""
            SELECT DATE_FORMAT({date_column}, %s) as period, COUNT(DISTINCT symbol) as cnt
            FROM {table}
            WHERE {date_column} >= %s AND {date_column} <= %s
            {stock_filter}
            GROUP BY DATE_FORMAT({date_column}, %s)
        """, params)
        
        return {row[0]: row[1] for row in cursor.fetchall()}
```

### 6.3 合并计算完整度

```python
def _calculate_completeness(self, stocks_by_period: dict, data_by_period: dict, periods: list) -> list:
    """
    计算完整度
    """
    result = []
    for period in periods:
        denominator = stocks_by_period.get(period, 0)
        numerator = data_by_period.get(period, 0)
        
        if denominator == 0 or numerator == 0:
            result.append(-1)  # 不适用
        else:
            completeness = round(numerator / denominator, 2)
            result.append(min(1.0, max(0.0, completeness)))
    
    return result
```

## 7. 实现计划

### Phase 1: 创建计算模块
1. 创建 `backend/saa_collector/completeness.py`
2. 实现 `CompletenessCalculator` 类
3. 添加单元测试

### Phase 2: 重构仪表盘热力图
1. 修改 `DataCompletenessHeatmapView` 使用 `CompletenessCalculator`
2. 删除重复的辅助方法
3. 验证功能正常

### Phase 3: 重构完整度报告热力图
1. 修改 `DataIntegrityReportHeatmapView` 使用 `CompletenessCalculator`
2. 删除重复的辅助方法
3. 验证功能正常

### Phase 4: 清理和优化
1. 删除不再使用的代码
2. 添加文档注释
3. 性能优化（如果需要）

## 8. 特殊处理

### 8.1 trade_days（交易日）
- 非股票级别数据
- 单独逻辑：检查数据库中是否存在该 period 的交易日数据
- 完整度逻辑：如果存在数据则为 1.0，否则为 -1（不适用）

### 8.2 quote（最新行情）
- 非周期性数据，只有最新交易日的数据有意义
- 特殊逻辑：
  1. 获取最新交易日
  2. 只在该 period 显示完整度
  3. 其他 periods 显示 -1（不适用）
  4. 完整度 = 有数据的股票数 / 总股票数

### 8.3 stock_info（股票基本信息）
- 非时间序列数据
- 恒定完整度：1.0（如果有数据）或 -1（不适用）

## 9. 配色方案

### 9.1 统一配色规则

仪表盘和完整度报告热力图使用统一的配色方案，采用分段颜色而非连续渐变：

| 完整度范围 | 颜色代码 | 颜色名称 | 说明 |
|------------|----------|----------|------|
| -1（不适用） | `#f5f5f5` | 灰色 | 该 period 无数据或不应有数据 |
| 0 - 0.25 | `#fecaca` | 浅红 | 完整度很低，大量缺失 |
| 0.25 - 0.5 | `#fed7aa` | 浅橙 | 完整度较低 |
| 0.5 - 0.75 | `#fef08a` | 浅黄 | 完整度中等 |
| 0.75 - 0.9 | `#bbf7d0` | 浅绿 | 完整度较高 |
| 0.9 - 1.0 | `#86efac` | 绿色 | 完整度很高 |

### 9.2 实现方式

#### 前端 JavaScript 函数

```javascript
const getColorByValue = (value: number): string => {
  if (value === -1) return '#f5f5f5'  // 不适用
  if (value < 0.25) return '#fecaca'  // 浅红
  if (value < 0.5) return '#fed7aa'   // 浅橙
  if (value < 0.75) return '#fef08a'  // 浅黄
  if (value < 0.9) return '#bbf7d0'   // 浅绿
  return '#86efac'                     // 绿色
}
```

#### ECharts 配置

使用 `custom` series 配合 `renderItem` 实现自定义颜色，而非使用 `visualMap` 的连续渐变：

```javascript
series: [
  {
    type: 'custom',
    renderItem: (params, api) => {
      const value = api.value(2)
      return {
        type: 'rect',
        shape: { /* ... */ },
        style: {
          fill: getColorByValue(value),
          stroke: '#fff',
          lineWidth: 1
        }
      }
    },
    data: chartData
  }
]
```

### 9.3 Tooltip 格式化

```javascript
tooltip: {
  formatter: (params) => {
    const value = params.data[2]
    if (value === -1) {
      return `${period}<br/>${dataType}: 不适用`
    }
    const percentage = Math.round(value * 100)
    return `${period}<br/>${dataType}: ${percentage}% 完整`
  }
}
```

### 9.4 行完整度汇总颜色

右侧汇总列使用不同的颜色规则（用于显示整体完整度）：

| 完整度范围 | 颜色代码 | 颜色名称 |
|------------|----------|----------|
| < 0.5 | `#f56c6c` | 红色 |
| 0.5 - 0.75 | `#e6a23c` | 橙色 |
| 0.75 - 0.9 | `#409eff` | 蓝色 |
| >= 0.9 | `#67c23a` | 绿色 |

```javascript
const getCompletenessColor = (completeness: number): string => {
  if (completeness < 0.5) return '#f56c6c'
  if (completeness < 0.75) return '#e6a23c'
  if (completeness < 0.9) return '#409eff'
  return '#67c23a'
}
```
