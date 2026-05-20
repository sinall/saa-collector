# External API Cache Design Notes

> 未来增强设计笔记。外部 API 缓存尚未实现；当前已生效的是 Tushare 全局限流和 API/限流耗时日志。当前规范见 `../../openspec/specs/collector-external-api/spec.md`。

## 背景

当前长时间采集的主要耗时来自 Tushare 等外部 API。即使已经支持 `financial_statements` 按 `remaining_symbols` 续跑，重试失败 symbol 或重新执行计划时，仍可能重复请求相同的外部接口。

后续可以在系统内增加外部 API 响应缓存：同一 API、同一参数、缓存仍有效时，直接读取本地缓存结果，避免真实请求外部服务。

## 目标

- 降低 Tushare 等外部 API 重复请求耗时。
- 降低外部 API 限流影响。
- 支持失败重试、任务续跑、开发调试时复用已有响应。
- 缓存作为采集层优化，不改变最终业务表结构。

## 与 DB preflight skip 的关系

针对 `财务报表采集(5月)` 这类 schedule，如果每次触发都按全市场全量采集，主要浪费不只是外部 API 请求本身，还包括限流等待、DataFrame 转换、DB upsert、cache refresh 和长任务运行时间。这里有两个方向：

1. **API call cache**：保持采集结构不变，在 `TushareApiClient` 层复用同一 API + 参数的历史响应。
2. **DB preflight skip**：采集前先检查本地业务表，若某个 symbol 对应数据已经满足要求，则跳过该 symbol 的 API call、转换和写库。

推荐顺序是 **DB preflight skip 优先，API call cache 作为补充**。

原因：

- API cache 只能避免重复外部请求；缓存 miss、过期、文件丢失或参数变化时仍会走完整全量流程。
- DB preflight skip 直接减少待处理 symbol 数，能同时减少 API 调用、限流等待、转换、写库和后续 cache refresh。
- 对定时任务而言，“本地业务表已经满足本次采集目标”比“外部 API 响应在缓存里”更接近最终业务正确性。

因此外部 API cache 不应替代业务表级的跳过逻辑。更合理的执行顺序是：

```text
financial_statements schedule
  -> build symbols
  -> DB preflight coverage scan
       -> complete enough: skip symbol
       -> missing/stale: collect symbol
            -> optional API cache lookup
            -> Tushare call on miss
            -> save business tables
            -> refresh report caches
```

### DB preflight skip 的判定边界

不能简单用“表里有任意记录”作为跳过条件。财务报表存在修订、补发和分红缺失等情况，第一版应保守定义 `complete enough`：

- 只先作用于组合任务 `financial_statements`。
- 对三张核心财报表 `saa_raw_balance_sheet`、`saa_raw_income_statement`、`saa_raw_cash_flow_statement`，按 symbol 检查最近应覆盖报告期是否存在数据。
- `saa_dividends` 不宜作为强制完整条件，因为很多股票某些年份本来没有分红；第一版可只在有明确报告期/日期要求时检查。
- 如果任一核心表缺最近应覆盖报告期，则该 symbol 仍进入采集。
- 跳过时必须打日志，例如 `Skip financial statements for 002803: local data complete`，并计入最终进度。

### 待决策：补齐缺失还是强制刷新修订

`财务报表采集(5月)` 的业务语义需要先明确：

| 语义 | 行为 |
| --- | --- |
| 补齐缺失数据 | 优先 DB preflight skip；本地满足覆盖条件的 symbol 不再请求 API |
| 强制刷新最新修订 | 不能简单跳过；应刷新最近 N 个报告期，或使用较短 TTL 的 API cache |
| 两者兼顾 | schedule/job 参数中显式区分，例如 `skip_existing=true`、`refresh_recent_periods=4` 或 `force_refresh=false` |

在语义未确认前，不建议直接让所有财报 schedule 默认跳过历史数据。建议先把 `财务报表采集(5月)` 定义为“补齐缺失 + 可配置刷新最近 N 期”，再实现 DB preflight skip。

## 关键设计点

### 0. 先量化 API 调用与限流等待

缓存上线前需要先能回答两个问题：

- 真实外部 API 调用本身花了多久。
- 因速率限制主动 sleep 花了多久。

`TushareApiClient` 的日志应区分：

- `api_elapsed_seconds`：真实 `pro.query(...)` 调用耗时。
- `rate_limit_wait_seconds`：本次调用前因限流累计等待的时间。
- `limiter=local|global`：使用进程内限流还是 Redis 全局限流。
- `lock_wait_seconds`：Redis 全局限流中等待锁的时间。

这样缓存上线后可以直接对比：

- cache hit 节省了多少真实 API 调用耗时。
- cache hit 是否也绕过了原本会产生的限流等待。
- 大任务总耗时中，外部 API、主动限流、数据转换、DB 写入各占多少。

### 1. 缓存时间

缓存 TTL 应按数据类型区分，而不是全局固定：

| 数据类型 | 建议 TTL | 原因 |
| --- | --- | --- |
| 历史财报、历史分红、股本历史 | 7-30 天或更长 | 历史数据变化频率低，重跑时复用价值高 |
| 股票基础信息 | 1-7 天 | 公司资料可能变化，但不需要分钟级刷新 |
| 最新行情、估值、实时类数据 | 短 TTL 或不缓存 | 时效性强，缓存容易引入旧数据 |
| 开发/调试模式 | 可配置更长 TTL | 便于重复测试同一批请求 |

缓存记录至少需要 `created_at` 和可选 `expires_at`。命中时先判断是否过期；过期后重新请求外部 API 并覆盖缓存。

### 2. Evict 机制

首版可以先不做复杂后台 evict，只做懒清理：

- 命中时发现过期：删除或覆盖该缓存。
- 写入新缓存前：可按配置执行简单清理，例如删除 `expires_at < now()` 的记录。
- 提供管理命令：`cleanup_external_api_cache`，用于手动或 cron 清理。

后续如果缓存量变大，再考虑：

- 按最大条数清理最旧记录。
- 按最大磁盘占用清理。
- 针对某个 API / data_type 手动清空。

### 3. MySQL 还是 SQLite

#### MySQL

优点：

- 多容器、多 worker 天然共享缓存。
- 可用 Django ORM 管理模型和迁移。
- 备份、查询、排查比较统一。

缺点：

- 占用 RDS 空间。
- 大量 API 响应可能增加数据库 IO 和存储成本。
- 缓存属于可再生数据，放进主业务库会增加维护负担。

#### SQLite

优点：

- 本地文件即可，不占用 RDS 空间。
- 缓存是可再生数据，丢失也不影响业务正确性。
- 对单 worker 或同一容器内重试很轻量。

缺点：

- 多容器共享需要挂载同一个 volume，否则 worker 间缓存不互通。
- SQLite 写锁需要注意，多个 worker 并发写同一文件可能出现等待。
- 容器重建时如果没有持久化 volume，缓存会丢失。

#### 初步倾向

如果目标主要是降低生产 RDS 占用和让缓存保持“可丢弃”，首版倾向 SQLite + 持久化 volume：

```text
/var/cache/saa-collector/external-api-cache.sqlite3
```

生产 compose 需要为 worker/backend 挂载同一路径。若后续要多个 worker 高并发共享缓存，再评估迁移到 MySQL 或 Redis。

## 缓存键

缓存键需要稳定且可复现，建议包含：

- provider：例如 `tushare`
- api name：例如 `balancesheet`
- semantic params：排序后的业务参数 JSON，例如 `{"start_date":null, "ts_code":"000001.SZ"}`
- raw response schema version：当外部原始响应结构或缓存格式变化时可整体失效

可生成：

```text
sha256(provider + api_name + canonical_json(params) + version)
```

注意：**`fields` 不应参与 cache key**。本缓存的目标是保存外部 API 的完整 raw response，而不是保存某次业务调用裁剪后的字段集合。这样后续代码重构、补解析字段或修复 transform 逻辑时，可以复用旧 raw response 重新生成业务表数据。

这也带来一个约束：写入 cache 时必须尽量保存完整 raw response，或保存该 API 的 canonical full-fields 响应。不能让第一次只请求少数字段的调用污染同一个 cache entry，否则后续多解析字段时仍然拿不到新字段。

### API 调用字符串化

Tushare、Akshare 这类外部数据源本质上都是“调用某个 API 名称 + 一组参数”。缓存 key 的核心是把一次调用 canonicalize 成稳定字符串，保证语义相同的调用得到同一个 key，语义不同的调用一定得到不同 key。

建议先构造一个逻辑调用对象：

```json
{
  "provider": "tushare",
  "api": "balancesheet",
  "params": {
    "start_date": null,
    "ts_code": "000001.SZ"
  },
  "version": "v1"
}
```

然后做规范化：

- 参数按 key 排序，避免同义参数顺序生成不同 key。
- 去掉不影响返回结果的运行时参数，例如 logger、timeout、retry、rate_limit、request_id。
- 保留所有会影响业务语义的参数，例如 `ts_code`、`start_date`、`end_date`、`trade_date`、`period`、`type`。
- 排除 `fields`，因为它只表示本次业务代码想读取哪些列；cache value 应保存完整 raw response。
- `None`、空字符串、空列表要有明确规则。建议保留 `None`，但把空字符串统一成 `None`，避免同义调用拆成两个缓存。
- list/tuple 参数要排序还是保序，需要按 API 语义决定。股票列表如果只是集合，排序。
- 日期、datetime 统一格式化为字符串，例如 `YYYYMMDD` 或 `YYYY-MM-DD`，同一个 API 内必须一致。
- 数字、布尔值使用 JSON 原生类型，不要混用 `"1"` 和 `1`。

最终序列化时使用稳定 JSON：

```python
canonical = json.dumps(call, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
cache_key = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
```

例如：

```text
tushare.query("balancesheet", ts_code="000001.SZ", fields="<caller requested fields>", start_date=None)
```

可以规范化为：

```json
{"api":"balancesheet","params":{"start_date":null,"ts_code":"000001.SZ"},"provider":"tushare","version":"raw-v1"}
```

Akshare 的函数式调用也可以用同样方式表达：

```text
ak.stock_zygc_em(symbol="SZ000001")
```

规范化为：

```json
{"api":"stock_zygc_em","params":{"symbol":"SZ000001"},"provider":"akshare","version":"v1"}
```

缓存表里可以同时保存 `cache_key` 和 `canonical_call_json`。前者用于快速查询，后者用于排查“为什么命中/没命中”。

## 响应格式

缓存内容应保存外部 API 返回的完整原始 records，而不是 pandas DataFrame 或业务表 records：

- JSON records 可跨版本读取。
- 避免 pickle 带来的兼容和安全问题。
- 命中后再转换为 DataFrame 或直接进入当前 `to_dict('records')` 后的处理流程。
- 代码重构、补字段解析、transform 修复时，可以从同一份 raw response 重新生成业务表。

需要记录：

- `provider`
- `api_name`
- `cache_key`
- `params_json`
- `response_json`
- `raw_response_schema_version`
- `created_at`
- `expires_at`
- `hit_count`
- `last_hit_at`

## 集成位置

缓存应尽量放在外部 API client 层，而不是各 collector 业务逻辑里。

推荐位置：

```text
third_party/tushare_api_client.py
```

调用流程：

```text
collector -> TushareApiClient.query(api_name, **params)
          -> cache lookup
          -> miss/expired: call real API with canonical full-fields policy where possible
          -> save complete raw response
          -> return records/DataFrame-compatible result, applying caller field expectations after cache read
```

这样 balance sheet、income、cashflow、dividend 等都能复用同一缓存逻辑。

## 风险与约束

- 缓存不能默认用于强实时数据。
- 缓存命中必须可观测，日志至少区分 `cache hit` / `cache miss` / `cache expired`。
- 需要提供开关，例如 `EXTERNAL_API_CACHE_ENABLED=false`，避免排查数据问题时被缓存干扰。
- 需要支持强制绕过缓存，例如 collect job 参数或环境变量。
- 缓存命中的是外部 API 原始响应，不代表最终业务表已经写入成功；续跑逻辑仍然要以 job 进度和业务表写入为准。
- cache key 不包含 `fields` 的前提是 cache value 保存完整 raw response；如果某个 API 无法获取完整字段，必须为该 API 单独定义 canonical field set 或禁用该 API 的缓存。

## 待决策

- `财务报表采集(5月)` 的默认语义是补齐缺失，还是强制刷新最新修订。
- DB preflight skip 的完整性边界：最近 1 期、最近 N 期，还是从 `start_date` 到当前所有应有报告期。
- 是否在 schedule/job 参数中加入 `skip_existing`、`force_refresh` 或 `refresh_recent_periods`。
- 首版是否只支持 Tushare。
- SQLite cache 文件路径和 compose volume 挂载位置。
- 默认 TTL 配置放在环境变量、`saa_collector.yml`，还是按 data type 写入常量配置。
- 是否需要前端暴露“绕过缓存”选项，或仅保留为后端配置。
