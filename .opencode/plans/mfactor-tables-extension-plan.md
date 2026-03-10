# SAA Collector 表扩展计划

## 目标

为 saa-collector 项目新增7个表的采集和维护能力：
- `saa_securities` - 证券信息
- `saa_prices_ex` - 扩展价格数据
- `industries` - 行业分类
- `saa_index_quotes` - 指数行情
- `saa_index_weights` - 指数成分权重
- `saa_industry_stocks` - 行业-股票关系
- `saa_extras` - 额外数据

## 现有架构

```
backend/saa_collector/
├── abstract/          # 抽象接口定义
├── services/
│   ├── abstract/      # 服务抽象类
│   ├── impl/          # 服务实现
│   │   ├── akshare/   # AkShare数据源
│   │   ├── tushare/   # Tushare数据源
│   │   └── cninfo/    # CNINFO数据源
│   └── factory/       # 服务工厂
├── jobs/              # 定时任务
├── views.py           # API视图
├── urls.py            # URL路由
├── models.py          # Django模型
└── scheduler.py       # 调度器
```

### 数据流

```
Job → Service → AkShare/Tushare/CNINFO → DB Table
        ↑
    ServiceFactory
```

## 新表设计（待确认）

### 1. saa_securities - 证券信息
**推测用途**: 扩展的证券基础信息，可能包含股票、债券、基金等

**AkShare候选API**:
- `ak.stock_zh_a_spot_em()` - A股实时行情（含基础信息）
- `ak.stock_info_a_code_name()` - A股代码和名称

**待确认**: 字段结构

### 2. saa_prices_ex - 扩展价格数据
**推测用途**: 比saa_prices更详细的价格数据（如成交量、换手率等）

**AkShare候选API**:
- `ak.stock_zh_a_hist()` - 日线行情（可获取更多字段）
- `ak.stock_zh_a_spot_em()` - 实时行情

**待确认**: 字段结构

### 3. industries - 行业分类
**推测用途**: 行业分类主表

**AkShare候选API**:
- `ak.stock_board_industry_name_em()` - 行业板块名称
- `ak.stock_board_industry_cons_em()` - 行业成分股

**待确认**: 字段结构

### 4. saa_index_quotes - 指数行情
**推测用途**: 各类指数的行情数据

**AkShare候选API**:
- `ak.index_zh_a_hist()` - A股指数历史行情
- `ak.stock_zh_index_spot_sina()` - 指数实时行情

**待确认**: 字段结构

### 5. saa_index_weights - 指数成分权重
**推测用途**: 指数成分股及其权重

**AkShare候选API**:
- `ak.index_stock_cons_weight_csindex()` - 中证指数成分权重
- `ak.index_stock_cons()` - 指数成分股

**待确认**: 字段结构

### 6. saa_industry_stocks - 行业-股票关系
**推测用途**: 股票与行业的映射关系

**AkShare候选API**:
- `ak.stock_individual_info_em()` - 个股信息（含行业）
- `ak.stock_board_industry_cons_em()` - 行业成分股

**待确认**: 字段结构

### 7. saa_extras - 额外数据
**推测用途**: 其他扩展数据（具体待确认）

**待确认**: 用途和字段结构

## 实施计划

### Phase 1: 基础设施准备

#### 1.1 更新 Model
**文件**: `backend/saa_collector/models.py`

为每个新表添加DATA_TYPE选项（如果需要通过CollectJob管理）。

#### 1.2 更新 ServiceFactory
**文件**: 
- `backend/saa_collector/services/factory/service_factory.py`
- `backend/saa_collector/services/impl/akshare/service_factory.py`
- `backend/saa_collector/services/impl/tushare/service_factory.py`
- `backend/saa_collector/services/impl/cninfo/service_factory.py`
- `backend/saa_collector/services/factory/compound_service_factory.py`

新增工厂方法:
```python
def create_security_service(self):
    pass

def create_industry_service(self):
    pass

def create_index_service(self):
    pass

def create_extra_service(self):
    pass
```

### Phase 2: 抽象接口定义

#### 2.1 新增抽象服务接口
**目录**: `backend/saa_collector/services/abstract/`

新建文件:
- `security_service.py` - 证券信息服务接口
- `industry_service.py` - 行业服务接口
- `index_service.py` - 指数服务接口
- `extra_service.py` - 额外数据服务接口

### Phase 3: AkShare实现

#### 3.1 新增服务实现
**目录**: `backend/saa_collector/services/impl/akshare/`

新建文件:
- `security_service.py` - 证券信息采集实现
- `industry_service.py` - 行业数据采集实现
- `index_service.py` - 指数数据采集实现
- `extra_service.py` - 额外数据采集实现

### Phase 4: 定时任务

#### 4.1 新增采集任务
**目录**: `backend/saa_collector/jobs/`

新建文件:
- `security_collect_job.py`
- `industry_collect_job.py`
- `index_collect_job.py`
- `extra_collect_job.py`

#### 4.2 更新调度器
**文件**: `backend/saa_collector/scheduler.py`

添加新任务的定时调度。

### Phase 5: API端点

#### 5.1 新增视图
**文件**: `backend/saa_collector/views.py`

新增视图类:
- `CollectSecuritiesView` - 证券信息采集
- `CollectIndustriesView` - 行业数据采集
- `CollectIndexQuotesView` - 指数行情采集
- `CollectIndexWeightsView` - 指数权重采集
- `CollectIndustryStocksView` - 行业-股票关系采集
- `CollectExtrasView` - 额外数据采集

#### 5.2 更新URL路由
**文件**: `backend/saa_collector/urls.py`

新增路由:
```python
path('collect/securities/', ...),
path('collect/industries/', ...),
path('collect/index-quotes/', ...),
path('collect/index-weights/', ...),
path('collect/industry-stocks/', ...),
path('collect/extras/', ...),
```

#### 5.3 更新数据状态视图
**文件**: `backend/saa_collector/views.py`

在 `DataStatusView` 中添加新表的状态监控。

### Phase 6: 配置

#### 6.1 更新表映射
**文件**: `backend/saa_collector/services/impl/akshare/basic_stock_service.py`

在 `resource_table_mapping` 中添加新表映射。

## 文件清单

### 新建文件
```
backend/saa_collector/services/abstract/
├── security_service.py      # 证券服务接口
├── industry_service.py      # 行业服务接口
├── index_service.py         # 指数服务接口
└── extra_service.py         # 额外数据服务接口

backend/saa_collector/services/impl/akshare/
├── security_service.py      # AkShare证券实现
├── industry_service.py      # AkShare行业实现
├── index_service.py         # AkShare指数实现
└── extra_service.py         # AkShare额外数据实现

backend/saa_collector/jobs/
├── security_collect_job.py  # 证券采集任务
├── industry_collect_job.py  # 行业采集任务
├── index_collect_job.py     # 指数采集任务
└── extra_collect_job.py     # 额外数据采集任务
```

### 修改文件
```
backend/saa_collector/models.py                    # 添加DATA_TYPE
backend/saa_collector/views.py                     # 添加视图和表映射
backend/saa_collector/urls.py                      # 添加URL路由
backend/saa_collector/scheduler.py                 # 添加定时任务
backend/saa_collector/services/factory/service_factory.py          # 添加工厂方法
backend/saa_collector/services/impl/akshare/service_factory.py     # 实现工厂方法
backend/saa_collector/services/factory/compound_service_factory.py # 实现组合工厂
```

## 待补充信息

### 必需信息
1. **表结构**: 每个表的CREATE TABLE语句或字段定义
2. **数据源确认**: 每个表对应的具体AkShare API
3. **采集频率**: 每个表的定时采集策略

### 可选信息
1. 数据转换规则（字段映射）
2. 数据验证规则
3. 错误处理策略

## 时间估算

| 阶段 | 工作量 | 说明 |
|------|--------|------|
| Phase 1 | 1小时 | 基础设施 |
| Phase 2 | 1小时 | 抽象接口 |
| Phase 3 | 4-8小时 | AkShare实现（每个表1小时） |
| Phase 4 | 1小时 | 定时任务 |
| Phase 5 | 2小时 | API端点 |
| Phase 6 | 1小时 | 配置更新 |
| **总计** | **10-14小时** | |

## 风险

1. **表结构不明确**: 需要先确认表结构才能设计字段映射
2. **AkShare API限制**: 部分数据可能需要付费或有限流
3. **数据量**: 某些表数据量大，需要分批处理

## 下一步

1. 提供各表的CREATE TABLE语句
2. 确认每个表对应的数据来源
3. 确认采集频率要求
