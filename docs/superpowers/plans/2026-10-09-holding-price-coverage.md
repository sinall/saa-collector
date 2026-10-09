# 持有期行情与复权覆盖 Implementation Plan

> **For agentic workers:** 按 superpowers:executing-plans 在当前 main 上执行；用户已要求不开分支。本计划由当前 agent 顺序实施。

**Goal:** 复用既有任务补齐指定股票月末行情和复权，并支持指数移出后的持有期覆盖。

**Architecture:** 共用指数历史范围解析器，新增 index_lookback_months（默认0，0～36）配置。仅历史行情和复权任务允许开启窗口；完整度服务对这两类数据使用相同范围和精确月末交易日。指定股票复权查询拆分为交易日查询，避免一次请求跨多年全市场数据。

**Tech Stack:** Django、DRF、Vue3、SQLite隔离测试。

## Global Constraints

- 不更改既有默认指数范围，不扩大财务/因子采集范围。
- 不创建 mfactor run、不重训教师、不更改冻结研究文件。
- 本轮产出代码、测试、离线补采请求和日程配置；生产执行必须有明确配置、核验和恢复说明。
- 不填充未知价格或复权因子；缺失仍须明确报告。

### Task 1: 指数持有期范围

Files: `backend/saa_collector/services/common/index_scope_utils.py`、`services/collect_plan_executor.py`、`date_expressions.py`、`serializers.py`、`views.py`、新增 `tests/test_holding_price_coverage.py`。

- [x] 写测试：6月覆盖3月末原成员、排除未来7月成员，0窗口兼容旧范围；负数、非整数、超36及不适用类型拒绝。
- [x] 用 `PYENV_VERSION=collector-env pyenv exec python manage.py test saa_collector.tests.test_holding_price_coverage --settings=config.settings.test` 确认新增行为失败。
- [x] 增加 `resolve_index_holding_payloads_by_dates(cursor,index_code,target_dates,lookback_months)`；各目标月回看含当前月和前N个月快照，调用既有as-of解析器，合并成员。
- [x] 任务读取params窗口，仅两种行情任务调用持有期解析器；即时创建和编辑保留配置；窗口默认0。
- [x] 同命令验证，并回归既有指数任务测试。

### Task 2: 复权查询及精确完整度

Files: `services/impl/tushare/quote_service.py`、`services/completeness_service.py`、`views.py`、`tests/test_quote_service.py`、新增测试。

- [x] 测试日期区间复权逐交易日调用、不漏区间首尾、非交易日不请求；月末缺复权仍不完整，移出成员计入分母；非行情数据保持旧范围。
- [x] 确认失败后实现日期拆分，通过交易日表解析；已有trade_date路径保持不变。
- [x] 完整度窗口模式仅支持monthly/index，查询精确月末日期和非空数据，不用当月任意一条替代；缓存键包括窗口。
- [x] 跑新增测试和复权、完整度、热力图、日程回归。

### Task 3: UI与补采交付

Files: `frontend/src/views/CollectPlansView.vue`、`CollectPlanEditView.vue`、`utils/api.ts`、`scripts/build_holding_price_repair.py`、`docs/operations/holding-price-coverage.md`。

- [x] 计划创建/编辑仅指数行情显示回看月数，其他任务提交0；支持回读、修改。
- [x] 离线CSV→既有计划请求JSON，按类型合并股票与最早/最晚日期，任务内部逐月末查询，只读输入，不连接数据库或API。测试去重及183/206两类不同缺口。
- [x] 生成当前缺口请求供审阅；记录补采配置、月末复权日程、验收及恢复方案。
- [x] `npm run type-check`、适用UI验证及 `git diff --check`；不自动提交/推送/部署。

## 验证与交付状态

- 后端相关82项测试、离线请求生成2项测试通过；仅SQLite测试库/模拟数据源。
- Chromium即时计划与日程10项页面测试通过，TypeScript类型检查与git diff --check通过。
- 独立审查反馈的复权空结果、参数丢失、窗口省略清零、类型切换扩大范围均已补验证修复。
- 冻结清单离线重算与请求完全一致：2任务，覆盖183行情缺口键、206复权缺口键，含中间月份重采。
- 本地实现于main完成；生产执行按操作文档核验并记录，离线请求自身不执行补采。

## 用户评审后的合并调整

用户明确允许中间日期重采，要求减少任务记录。合并为行情111股票/128月、复权130股票/129月两个任务，显式`data_frequency=monthly`；executor内部逐月查询，不额外创建任务记录。保留原日频区间路径和零窗口行为。恢复范围同步扩大到这两个任务涉及的股票月末，不能仅备份206个缺口键。
