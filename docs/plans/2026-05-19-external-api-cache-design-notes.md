# External API Cache Design Notes

## 背景

当前长时间采集的主要耗时来自 Tushare 等外部 API。即使已经支持 `financial_statements` 按 `remaining_symbols` 续跑，重试失败 symbol 或重新执行计划时，仍可能重复请求相同的外部接口。

后续可以在系统内增加外部 API 响应缓存：同一 API、同一参数、缓存仍有效时，直接读取本地缓存结果，避免真实请求外部服务。

## 目标

- 降低 Tushare 等外部 API 重复请求耗时。
- 降低外部 API 限流影响。
- 支持失败重试、任务续跑、开发调试时复用已有响应。
- 缓存作为采集层优化，不改变最终业务表结构。

## 关键设计点

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
- canonical params：排序后的参数 JSON，例如 `{"fields":"...", "start_date":null, "ts_code":"000001.SZ"}`
- client/schema version：当字段解析逻辑变化时可整体失效

可生成：

```text
sha256(provider + api_name + canonical_json(params) + version)
```

注意 `fields` 参数必须参与 key，否则不同字段集合会错误命中。

### API 调用字符串化

Tushare、Akshare 这类外部数据源本质上都是“调用某个 API 名称 + 一组参数”。缓存 key 的核心是把一次调用 canonicalize 成稳定字符串，保证语义相同的调用得到同一个 key，语义不同的调用一定得到不同 key。

建议先构造一个逻辑调用对象：

```json
{
  "provider": "tushare",
  "api": "balancesheet",
  "params": {
    "fields": "ts_code,end_date,total_assets",
    "start_date": null,
    "ts_code": "000001.SZ"
  },
  "version": "v1"
}
```

然后做规范化：

- 参数按 key 排序，避免 `ts_code=...&fields=...` 和 `fields=...&ts_code=...` 生成不同 key。
- 去掉不影响返回结果的运行时参数，例如 logger、timeout、retry、rate_limit、request_id。
- 保留所有会影响返回结果的参数，例如 `fields`、`ts_code`、`start_date`、`end_date`、`trade_date`、`period`、`type`。
- `None`、空字符串、空列表要有明确规则。建议保留 `None`，但把空字符串统一成 `None`，避免同义调用拆成两个缓存。
- list/tuple 参数要排序还是保序，需要按 API 语义决定。股票列表如果只是集合，排序；字段列表如果返回列顺序有意义，保留原顺序。
- 日期、datetime 统一格式化为字符串，例如 `YYYYMMDD` 或 `YYYY-MM-DD`，同一个 API 内必须一致。
- 数字、布尔值使用 JSON 原生类型，不要混用 `"1"` 和 `1`。

最终序列化时使用稳定 JSON：

```python
canonical = json.dumps(call, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
cache_key = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
```

例如：

```text
tushare.query("balancesheet", ts_code="000001.SZ", fields="ts_code,end_date", start_date=None)
```

可以规范化为：

```json
{"api":"balancesheet","params":{"fields":"ts_code,end_date","start_date":null,"ts_code":"000001.SZ"},"provider":"tushare","version":"v1"}
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

缓存内容建议保存外部 API 返回的原始 records，而不是 pandas DataFrame：

- JSON records 可跨版本读取。
- 避免 pickle 带来的兼容和安全问题。
- 命中后再转换为 DataFrame 或直接进入当前 `to_dict('records')` 后的处理流程。

需要记录：

- `provider`
- `api_name`
- `cache_key`
- `params_json`
- `response_json`
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
          -> miss/expired: call real API
          -> save response
          -> return records/DataFrame-compatible result
```

这样 balance sheet、income、cashflow、dividend 等都能复用同一缓存逻辑。

## 风险与约束

- 缓存不能默认用于强实时数据。
- 缓存命中必须可观测，日志至少区分 `cache hit` / `cache miss` / `cache expired`。
- 需要提供开关，例如 `EXTERNAL_API_CACHE_ENABLED=false`，避免排查数据问题时被缓存干扰。
- 需要支持强制绕过缓存，例如 collect job 参数或环境变量。
- 缓存命中的是外部 API 原始响应，不代表最终业务表已经写入成功；续跑逻辑仍然要以 job 进度和业务表写入为准。

## 待决策

- 首版是否只支持 Tushare。
- SQLite cache 文件路径和 compose volume 挂载位置。
- 默认 TTL 配置放在环境变量、`saa_collector.yml`，还是按 data type 写入常量配置。
- 是否需要前端暴露“绕过缓存”选项，或仅保留为后端配置。
