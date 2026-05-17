# Collection Progress ETA Design

## 背景

采集任务现在希望在多 symbol 任务中输出完成进度和 ETA，例如：

```text
[11/5995] Finished collecting balance sheet for 000012; elapsed=00:09:10, avg=00:00:03/symbol, remaining=42:10:00, eta=2026-05-18 03:43:53
```

当前最直接的算法是按已完成 symbol 的平均耗时估算剩余时间：

```text
remaining = elapsed / completed_symbols * remaining_symbols
```

这个算法足够简单，也能逐步吸收网络波动、Tushare 限流、数据库写入变慢等运行时因素。根据当前代码梳理，Tushare 里的主要采集路径也确实大多是 symbol 循环，而不是显式的 symbol/date 双重循环。因此首版 ETA 不应该设计成复杂的日期级调度模型。

需要补充考虑的是：同一个 data_type 下，不同 symbol 的历史跨度可能不同。老股票记录多，新股记录少；如果 symbols 排序后新股集中在后面，纯 symbol 等权 ETA 可能偏保守。这个问题可以用一个可选的粗粒度 `symbol_weight` 策略处理，而不是把 API、SQL、日期点都拆成独立步骤。

## 原始日志样例与问题来源

本设计来自 `saa-collector-worker` 采集单支股票财务报表时的一段实际日志。下面保留关键片段，便于后续理解为什么要调整进度日志和 DataFrame warning：

```text
[2026-05-16 09:33:00,854: INFO/ForkPoolWorker-1] [11/5995] Producing statement for 000012
[2026-05-16 09:33:00,855: INFO/ForkPoolWorker-1] Start to produce statement for 000012
[2026-05-16 09:33:00,857: INFO/ForkPoolWorker-1] Start to collect statement for 000012
[2026-05-16 09:33:00,859: INFO/ForkPoolWorker-1] [1/1] Querying balancesheet for symbol 000012
[2026-05-16 09:33:00,989: INFO/ForkPoolWorker-1] End up calling pro.query(balancesheet, ..., ...) with 100 records return
[2026-05-16 09:33:01,019: WARNING/ForkPoolWorker-1] /app/saa_collector/services/impl/tushare/statement_service.py:144: UserWarning: DataFrame columns are not unique, some columns will be omitted.
  raw_records = df.to_dict('records')
[2026-05-16 09:33:03,561: INFO/ForkPoolWorker-1] Prepared 71 saa_raw_balance_sheet records for symbol 000012
[2026-05-16 09:33:03,955: INFO/ForkPoolWorker-1] Saved final 71 saa_raw_balance_sheet records
[2026-05-16 09:33:03,959: INFO/ForkPoolWorker-1] [1/1] Querying income for symbol 000012
[2026-05-16 09:33:06,980: INFO/ForkPoolWorker-1] End up calling pro.query(income, ..., ...) with 130 records return
[2026-05-16 09:33:07,941: INFO/ForkPoolWorker-1] Prepared 113 saa_raw_income_statement records for symbol 000012
[2026-05-16 09:33:08,509: INFO/ForkPoolWorker-1] Saved final 113 saa_raw_income_statement records
[2026-05-16 09:33:08,512: INFO/ForkPoolWorker-1] [1/1] Querying cashflow for symbol 000012
[2026-05-16 09:33:13,044: INFO/ForkPoolWorker-1] End up calling pro.query(cashflow, ..., ...) with 97 records return
[2026-05-16 09:33:15,038: INFO/ForkPoolWorker-1] Prepared 82 saa_raw_cash_flow_statement records for symbol 000012
[2026-05-16 09:33:15,473: INFO/ForkPoolWorker-1] Saved final 82 saa_raw_cash_flow_statement records
[2026-05-16 09:33:15,475: INFO/ForkPoolWorker-1] [1/1] Querying dividend for symbol 000012
[2026-05-16 09:33:18,981: INFO/ForkPoolWorker-1] End up calling pro.query(dividend, ..., ...) with 53 records return
[2026-05-16 09:33:18,993: INFO/ForkPoolWorker-1] Prepared 0 saa_dividends records for symbol 000012
[2026-05-16 09:33:19,155: INFO/ForkPoolWorker-1] Saved final 30 saa_dividends records
[2026-05-16 09:33:19,156: INFO/ForkPoolWorker-1] End up collecting statement for 000012
[2026-05-16 09:33:19,156: INFO/ForkPoolWorker-1] Start to process statement for 000012
[2026-05-16 09:33:53,112: INFO/ForkPoolWorker-1] End up refresh-financial-report-cache for 000012
[2026-05-16 09:33:53,373: INFO/ForkPoolWorker-1] End up refresh-ttm-report-cache for 000012
[2026-05-16 09:33:53,376: INFO/ForkPoolWorker-1] End up processing statement for 000012
[2026-05-16 09:33:53,377: INFO/ForkPoolWorker-1] End up producing statement for 000012
```

这段日志暴露出两个直接问题：

- 外层已经有 `[11/5995] Producing statement for 000012`，但单支股票内部复用通用查询循环时又输出 `[1/1] Querying ...`。这个 `[1/1]` 不代表整体任务进度，容易误导。
- `df.to_dict('records')` 前 DataFrame 存在重复列，pandas 会提示 `DataFrame columns are not unique, some columns will be omitted`，可能导致字段被静默丢弃。

同时，这段日志也说明 `financial_statements` 的单个 symbol 并不是只有采集动作：三张表、分红保存完成后，还会立即刷新 financial report cache 和 TTM cache。因此外层 symbol completion 日志应放在 collect 和 process/cache 都完成之后。

## 目标

- 所有多 symbol 任务都能在每个 symbol 完成时输出统一进度和 ETA。
- 默认策略保持简单：每个 symbol 权重为 1。
- 对财报、分红、股本、主营业务这类历史跨度影响明显的任务，可选使用粗粒度 symbol 权重。
- collector 调用方式尽量轻，常用场景只传 `logger`、`symbols` 和可选 `profile`。
- 估算逻辑失败时自动降级为等权策略，不影响采集结果。

## 非目标

- 不追求精确到分钟的 ETA。
- 不在采集前调用外部 API 预估实际记录数。
- 不拆分具体 API、SQL、DB batch 成本。
- 不改变现有采集顺序，symbols 仍保持排序。
- 不为当前代码中不存在的显式 symbol/date 双重循环提前设计复杂调度。

## 设计决策记录

讨论过程中曾考虑过更细粒度的估算模型：

```text
work_unit = 1 symbol x 1 data_type x 1 date_point
```

其中 `date_point` 表示一个数据日期或报告期日期，例如季度财报的季度末、年度分红的年度日期、月线行情的月份。这个模型的优点是能表达“同一支股票因为上市时间不同，历史数据跨度不同，所以工作量不同”。它也能在未来扩展到真正的 symbol/date 双重循环任务。

还讨论过把每个 symbol 内部的多个步骤也纳入估算，例如：

```text
api_call_1 + api_call_2 + db_write_1 + db_write_2
```

这类模型理论上更细，但当前不作为首版方案，原因如下。

首先，当前 Tushare 实现里真正的显式 symbol/date 双重循环并不明显。更多代码是：

```text
for symbol in symbols:
    API(symbol, start_date/end_date) -> returns many historical records
    transform/filter
    batch DB save
```

也就是说，日期点影响返回记录量和 DB 写入量，但不是现有代码的自然进度边界。如果为了 ETA 强行引入日期级进度，需要 collector 在更多位置回调进度，侵入性会明显增加。

其次，不同 API、不同 SQL、不同 batch 的耗时差异很大。简单拆成“几次 API + 几次 DB 写入”容易变成不上不下的模型：比 symbol 等权复杂很多，但准确性未必更好。网络波动、Tushare 限流、数据库瞬时负载这些因素，反而更适合由运行时平均耗时逐步吸收。

第三，当前最稳定、最容易观测的进度边界是 symbol 完成。用户看日志时也更关心“第几支股票完成了、预计整体什么时候完成”，而不是某支股票内部的某个日期点或某次 API 是否完成。

因此当前决策是：

- 首版以 symbol completion 作为唯一进度边界。
- 默认每个 symbol 权重为 1。
- 对历史跨度影响明显的 data_type，只在 Estimator 内部用 `listing_time/start_date/end_date/data_frequency` 计算粗粒度 `symbol_weight`。
- 不在 collector 主流程中暴露 date point、API step、DB step。

如果未来出现明确的 symbol/date 双重循环，或者某个任务本身已经有稳定的分段进度回调，再新增更细的 Estimator。届时可以复用上面的 work unit 思路，但不把它作为当前 Tushare 首版的默认设计。

## 当前 Tushare 循环形态

当前生产重点先看 Tushare。实际代码里，多数任务是外层 symbol 循环，单个 symbol 内部一次或少数几次 API 拉取一段历史数据，然后 transform/filter，最后按 batch 写 DB。

| data_type | Tushare 入口 | 实际循环 | ETA 首版建议 |
| --- | --- | --- | --- |
| `stock_info` | `StockInfoServiceImpl.collect(symbols)` | symbol 循环；每个 symbol 查 `stock_basic`，再尝试 `stock_company` | 等权 symbol |
| `quote` | `QuoteServiceImpl.collect(symbols)` | 一次 `daily(trade_date=today)` 拉全市场，再 filter symbols | 不按 symbol ETA，或按 1 个 job |
| `historical_quote` | `QuoteServiceImpl.collect_historical(...)` | 当前 Tushare 实现不是清晰的 symbol/date 双重循环 | 暂不纳入首批 |
| `financial_statements` | `StatementServiceImpl.produce(symbols, start_date)` | symbol 循环；每个 symbol 采三张表 + dividend，再立即 process/cache | 可选历史跨度权重 |
| `balance_sheet` | `collect_balance_sheet(symbols, start_date)` | symbol 循环；每 symbol 一次 `balancesheet` 拉整段历史 | 可选历史跨度权重 |
| `income` | `collect_income(symbols, start_date)` | symbol 循环；每 symbol 一次 `income` 拉整段历史 | 可选历史跨度权重 |
| `cash_flow` | `collect_cash_flow(symbols, start_date)` | symbol 循环；每 symbol 一次 `cashflow` 拉整段历史 | 可选历史跨度权重 |
| `dividend` | `collect_dividend(symbols, start_date)` | symbol 循环；每 symbol 一次 `dividend` 拉整段历史 | 可选历史跨度权重 |
| `main_business` | `collect_main_business(symbols, start_date)` | symbol 循环；每 symbol 查询产品和地区两类历史主营业务 | 可选历史跨度权重 |
| `capital` | `CapitalServiceImpl.collect(symbols, start_date)` | symbol 循环；每 symbol 查询股本相关历史 | 可选历史跨度权重 |
| `trade_days` | `CalendarServiceImpl.collect(start_date, end_date)` | 非 symbol 任务 | 暂不纳入 symbol ETA |

`StatementServiceImpl.produce()` 需要特别说明：它不是等所有股票采集完后再统一 process，而是每个 symbol 采集完成后马上刷新 financial report cache 和 TTM cache。因此进度日志放在每个 symbol 全部采集和处理完成之后更准确。

## 核心设计

### ProgressLogger

`ProgressLogger` 只负责计时、累计完成量和输出日志，不理解 Tushare、财报、行情、API 或数据库。

常用入口建议设计成 symbol 专用工厂，隐藏默认参数：

```python
progress = ProgressLogger.for_symbols(
    logger,
    symbols,
)
```

默认值：

- `unit='symbol'`
- `profile='default'`
- `estimator=EqualWorkEstimator`
- `start_date=None`
- `end_date=None`
- 不需要 listing time 时不查 DB

历史跨度敏感的任务只多传一个 `profile`，以及该 profile 需要的少量上下文：

```python
progress = ProgressLogger.for_symbols(
    logger,
    symbols,
    profile='balance_sheet',
    start_date=start_date,
)
```

不建议把 `unit`、`context`、`workload_profile` 都暴露给普通调用方。`unit` 对多 symbol 任务基本恒定；`context` 字典容易让每个调用点写出不同风格；`workload_profile` 名字偏长，文档和代码里可以简化为 `profile`。

每个 symbol 完成后调用：

```python
progress.finished('Finished collecting balance sheet', symbol)
```

对于按 batch 保存的直接采集任务，`finished()` 应尽量在对应 batch save 之后调用。这样 ETA 能把 DB 写入耗时也吸收到运行时平均值里。组合任务如 `financial_statements` 则在单个 symbol 的 collect 和 process/cache 都完成后再推进外层进度。

失败时调用：

```python
progress.failed('Failed collecting balance sheet', symbol)
```

默认情况下：

```text
weight(symbol) = 1
```

ETA 计算：

```text
completed_weight += weight(symbol)
remaining_weight = total_weight - completed_weight
seconds_per_weight = elapsed / completed_weight
remaining_seconds = seconds_per_weight * remaining_weight
```

日志不需要暴露具体策略，只显示进度、耗时和 ETA：

```text
[11/5995] Finished collecting balance sheet for 000012; elapsed=00:09:10, avg=00:00:03/symbol, remaining=42:10:00, eta=2026-05-18 03:43:53
```

如果启用了加权策略，`avg` 仍可显示为 `/symbol`，避免把日志变复杂。内部权重只是用于估算 remaining。

### Estimator

Estimator 是可插拔策略，负责估算每个 symbol 的权重。collector 不直接计算权重，也不直接选择具体算法类。

```python
class CollectionWorkEstimator:
    def weight(self, symbol):
        return 1
```

调用方只声明 profile：

```python
progress = ProgressLogger.for_symbols(
    self._logger,
    symbols,
    profile='financial_statements',
    start_date=start_date,
    end_date=end_date,
)
```

`ProgressLogger` 内部把关键字参数整理成 context，再通过工厂创建 Estimator：

```python
estimator = create_collection_estimator(
    profile=profile,
    items=items,
    context=context,
)
```

Estimator 创建失败、参数缺失、权重异常时，统一降级为 `EqualWorkEstimator`。

## 策略

### EqualWorkEstimator

默认策略：

```text
weight(symbol) = 1
```

适合：

- `stock_info`
- symbol 之间工作量差异不明显的任务
- 暂时没有确认执行形态的任务
- 所有估算失败后的兜底场景

### HistoricalSpanEstimator

历史跨度策略只做粗粒度权重，不拆 API/DB 细节：

```text
effective_start = max(start_date or listing_time, listing_time)
effective_end = end_date or today
period_count = count_periods(effective_start, effective_end, data_frequency)
weight(symbol) = max(period_count * factor, 1)
```

这里的 period 是估算用的时间跨度，不要求代码真的按日期循环。季度数据按季度数，年度数据按年数，月度数据按月数。实际耗时中的 API、transform、filter、DB batch、网络限流都作为黑盒，由运行时平均耗时逐步吸收。

`data_frequency` 优先来自 `backend/saa_collector/constants.py` 的 `DATA_TYPE_CONFIG[data_type]['data_frequency']`：

- `quarterly`: 按季度数估算
- `yearly`: 按年数估算
- `monthly`: 按月数估算
- `daily`: 首批谨慎使用，除非确认该任务确实按 symbol 拉历史日数据
- `None`: 固定为 1

初版推荐 profile：

```python
WORKLOAD_PROFILES = {
    'default': {
        'estimator': EqualWorkEstimator,
    },
    'stock_info': {
        'estimator': EqualWorkEstimator,
    },
    'financial_statements': {
        'estimator': HistoricalSpanEstimator,
        'data_type': 'financial_statements',
        'factor': 4,
    },
    'balance_sheet': {
        'estimator': HistoricalSpanEstimator,
        'data_type': 'balance_sheet',
    },
    'income': {
        'estimator': HistoricalSpanEstimator,
        'data_type': 'income',
    },
    'cash_flow': {
        'estimator': HistoricalSpanEstimator,
        'data_type': 'cash_flow',
    },
    'dividend': {
        'estimator': HistoricalSpanEstimator,
        'data_type': 'dividend',
    },
    'capital': {
        'estimator': HistoricalSpanEstimator,
        'data_type': 'capital',
    },
    'main_business': {
        'estimator': HistoricalSpanEstimator,
        'data_type': 'main_business',
        'factor': 2,
    },
}
```

`factor` 只是粗略反映同一 symbol 内的资源数量。例如 `financial_statements` 当前会采 balance sheet、income、cash flow、dividend；`main_business` 当前查询产品和地区两类。后续如果真实日志显示这个近似不合适，只调整 Estimator/profile，不改 collector 主流程。

## 上市时间

历史跨度策略需要 listing time。优先从本地数据库一次性查询：

```sql
SELECT symbol, listing_time
FROM saa_stocks
WHERE symbol IN (...)
```

要求：

- 只查一次，不能每个 symbol 单独查 DB。
- `weight(symbol)` 只能读内存中的 `listing_times` map，禁止在这里发 SQL。
- 查询失败时降级为等权策略。
- 单个 symbol 缺失 `listing_time` 时，该 symbol 权重取 1 或使用保守 fallback。
- `listing_time` 晚于 `end_date` 时，权重仍取 1，避免总权重为 0。

查询可以封装在 Estimator 工厂或统一 repository/helper 里，collector 不需要知道 listing time 怎么来。普通 collector 调用点不应该为了 ETA 传 `db_config`。如果底层确实需要连接配置，也应由 Estimator 工厂从已有应用上下文取得，或作为低层 override 使用。

## 工厂

默认约定：

```text
profile = data_type
```

特殊执行形态再额外定义 profile。首批不为 Akshare、Cninfo、quote、historical_quote 提前设计复杂 profile。

示例：

```python
def create_collection_estimator(profile, items, context=None):
    context = context or {}
    profile_config = WORKLOAD_PROFILES.get(profile) or WORKLOAD_PROFILES['default']
    estimator_class = profile_config['estimator']

    if estimator_class is EqualWorkEstimator:
        return EqualWorkEstimator()

    try:
        listing_times = context.get('listing_times')
        if listing_times is None:
            listing_times = load_listing_times(items)

        return estimator_class(
            items=items,
            listing_times=listing_times,
            start_date=context.get('start_date'),
            end_date=context.get('end_date'),
            data_type=profile_config.get('data_type'),
            factor=profile_config.get('factor', 1),
        )
    except Exception:
        return EqualWorkEstimator()
```

外部 API 可以分两层：

```python
class ProgressLogger:
    @classmethod
    def for_symbols(cls, logger, symbols, profile='default', **context):
        return cls(
            logger=logger,
            items=symbols,
            unit='symbol',
            profile=profile,
            context=context,
        )
```

低层构造函数保留 `unit/profile/context`，但普通 collector 不直接使用。

## 接入步骤

第一阶段只做通用能力：

- `ProgressLogger` 支持 completion 日志里的 elapsed、remaining、eta。
- 默认等权，每个 symbol 完成时输出进度。
- 提供 `ProgressLogger.for_symbols(logger, symbols, profile='default', **context)`，不要求调用方传 `unit` 或手写 `context` 字典。
- 保持现有调用方兼容，不要求所有 collector 立刻传 profile。

第二阶段接入 Tushare 中明确是 symbol 循环的任务：

- `financial_statements`
- `balance_sheet`
- `income`
- `cash_flow`
- `dividend`
- `capital`
- `main_business`
- `stock_info`

第三阶段根据真实日志再调权重：

- 如果加权收益不明显，保留等权。
- 如果财报 ETA 仍偏差大，只调整 `HistoricalSpanEstimator` 或 profile factor。
- 如果未来出现明确的 symbol/date 双重循环，再增加新的 Estimator，不把当前设计提前复杂化。

## 调用示例

collector 只声明采集类型和上下文：

```python
def collect_balance_sheet(self, symbols, start_date=None):
    symbols = self.build_symbols(symbols)
    progress = ProgressLogger.for_symbols(
        self._logger,
        symbols,
        profile='balance_sheet',
        start_date=start_date,
    )

    for symbol in symbols:
        try:
            raw_records = self.query_record(
                'balancesheet',
                symbol,
                fields=self.build_fields('saa_raw_balance_sheet'),
                start_date=self.build_date_param(start_date),
            )
            records = self.transform_records(raw_records, 'saa_raw_balance_sheet')
            # Existing batch save logic stays unchanged.
            progress.finished('Finished collecting balance sheet', symbol)
        except Exception:
            self._logger.exception('Failed to collect balance sheet for %s', symbol)
            progress.failed('Failed collecting balance sheet', symbol)
```

`financial_statements` 的 completion 点应该放在每个 symbol 的 collect 和 process/cache 都完成之后：

```python
def collect_financial_statements(self, symbols, start_date=None):
    progress = ProgressLogger.for_symbols(
        self._logger,
        symbols,
        profile='financial_statements',
        start_date=start_date,
    )

    for symbol in symbols:
        self._collect_one(symbol, start_date)
        self._process_one(symbol)
        progress.finished('Finished collecting financial statements', symbol)
```

## 推荐结论

采用“ProgressLogger + Estimator”的轻量方案。

首版以 symbol completion 为唯一进度点，默认每个 symbol 等权。对历史跨度影响明显的 Tushare 任务，再通过 `HistoricalSpanEstimator` 按 `listing_time/start_date/end_date/data_frequency` 粗略加权。不要拆 API、SQL、DB batch，也不要为当前代码里并不明显的双重循环设计复杂模型。
