# SAA Collector Django + Vue 集成设计

## 1. 项目概述

将 saa-collector 从 cement CLI 架构改造为 Django + Vue 前后端分离架构，保留现有采集能力，增加 Web 管理界面。

### 目标功能
1. **数据完整性检查** - 按时间、股票、报表类型检查数据缺失情况
2. **定制抓取范围** - 手动触发采集任务，选择股票范围、时间范围、数据类型

### 技术决策
- **Django + APScheduler 集成** - Django 启动时同时启动 apscheduler
- **前后端分离** - Vue 独立 build，Django 提供 API
- **认证方式** - DRF SessionAuthentication + TokenAuthentication + DevTokenMiddleware

---

## 2. 目录结构

```
saa-collector/
├── backend/                         # 后端 (Django)
│   ├── saa_collector/               # 现有代码挪入
│   │   ├── services/                # 数据采集服务 (保留)
│   │   │   ├── abstract/            # 抽象接口
│   │   │   ├── impl/                # 实现 (akshare/tushare/cninfo)
│   │   │   ├── common/              # 公共服务
│   │   │   └── factory/             # 服务工厂
│   │   ├── jobs/                    # 定时任务 (保留)
│   │   ├── utils/                   # 工具类 (保留)
│   │   ├── third_party/             # 第三方 API 客户端 (保留)
│   │   ├── controllers/             # Cement 控制器 (保留，CLI 仍可用)
│   │   ├── core/                    # 核心模块 (保留)
│   │   ├── templates/               # 模板 (保留)
│   │   ├── config/                  # 配置 (保留)
│   │   ├── ext/                     # 扩展 (保留)
│   │   ├── plugins/                 # 插件 (保留)
│   │   ├── definitions.py           # 定义 (保留)
│   │   ├── scheduler.py             # 调度器 (修改：集成到 Django)
│   │   └── main.py                  # CLI 入口 (保留)
│   │
│   ├── collector/                   # Django App (新建)
│   │   ├── __init__.py
│   │   ├── apps.py
│   │   ├── models.py                # 采集任务模型
│   │   ├── views.py                 # API 视图
│   │   ├── serializers.py           # DRF 序列化器
│   │   ├── urls.py                  # URL 路由
│   │   └── tasks.py                 # 异步任务封装
│   │
│   ├── config/                      # Django 项目配置 (新建)
│   │   ├── __init__.py
│   │   ├── settings/
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── development.py
│   │   │   └── production.py
│   │   ├── urls.py
│   │   ├── wsgi.py
│   │   └── asgi.py
│   │
│   ├── manage.py
│   ├── requirements.txt
│   ├── entrypoint.py
│   └── Dockerfile
│
├── frontend/                        # 前端 (Vue 3)
│   ├── src/
│   │   ├── views/                   # 页面组件
│   │   │   ├── DashboardView.vue    # 仪表盘
│   │   │   ├── DataCheckView.vue    # 数据完整性检查
│   │   │   ├── CollectTaskView.vue  # 采集任务管理
│   │   │   ├── StockListView.vue    # 股票列表
│   │   │   └── LoginView.vue        # 登录页
│   │   ├── components/              # 通用组件
│   │   │   ├── StockSelector.vue    # 股票选择器
│   │   │   ├── DateRangePicker.vue  # 日期范围选择
│   │   │   ├── DataTypeSelector.vue # 数据类型选择器
│   │   │   └── TaskStatusBadge.vue  # 任务状态徽章
│   │   ├── utils/
│   │   │   ├── api.ts               # API 封装
│   │   │   ├── auth.ts              # 认证工具
│   │   │   └── types.ts             # TypeScript 类型定义
│   │   ├── router/
│   │   │   └── index.ts
│   │   ├── assets/
│   │   ├── App.vue
│   │   └── main.ts
│   ├── public/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── .env.development
│   ├── Dockerfile
│   └── nginx.conf
│
├── docker-compose.yml
└── Makefile
```

---

## 3. API 设计

### 3.1 认证 API

```
POST /api/auth/login/           # 登录
POST /api/auth/logout/          # 登出
GET  /api/auth/user/            # 当前用户信息
```

### 3.2 数据状态 API

```
GET  /api/data-status/          
# 获取各数据类型的状态概览
# Response: {
#   "stock_info": { "count": 5000, "latest_update": "2026-03-08" },
#   "quote": { "count": 1000000, "latest_date": "2026-03-07" },
#   ...
# }

GET  /api/data-completeness/    
# 按维度检查完整性
# Params: data_type, symbols, start_date, end_date
# Response: {
#   "summary": { "total": 1000, "missing": 50, "rate": 0.95 },
#   "by_stock": [...],
#   "by_date": [...],
#   "missing_details": [...]
# }
```

### 3.3 采集任务 API

```
POST /api/collect/stock-info/      
# 采集股票基本信息
# Body: { "symbols": ["000001"] }  # 可选，为空则全量

POST /api/collect/quotes/          
# 采集最新行情
# Body: { "symbols": ["000001"] }

POST /api/collect/historical-quotes/  
# 采集历史行情
# Body: { "symbols": ["000001"], "start_date": "2025-01-01", "end_date": "2026-03-08" }

POST /api/collect/statements/      
# 采集财务报表
# Body: { 
#   "symbols": ["000001"], 
#   "start_date": "2025-01-01",
#   "report_types": ["balance_sheet", "income", "cash_flow", "dividend"]
# }

POST /api/collect/capital/         
# 采集股本变动
# Body: { "symbols": ["000001"], "start_date": "2025-01-01" }

POST /api/collect/valuation/       
# 采集估值数据
# Body: { "symbols": ["000001"] }

POST /api/collect/main-business/   
# 采集主营业务
# Body: { "symbols": ["000001"], "start_date": "2025-01-01" }

GET  /api/collect/jobs/            
# 获取采集任务列表
# Params: status, data_type, page, page_size

GET  /api/collect/jobs/{id}/       
# 获取单个任务详情
```

### 3.4 股票信息 API

```
GET  /api/stocks/                  
# 股票列表
# Params: keyword, page, page_size
# Response: {
#   "data": [...],
#   "pagination": { "page": 1, "page_size": 20, "total": 5000 }
# }

GET  /api/stocks/{symbol}/         
# 股票详情
# Response: { "symbol": "000001", "name": "平安银行", ... }
```

---

## 4. 数据类型定义

| data_type | 中文名 | 说明 | 对应 Job/Service |
|-----------|--------|------|------------------|
| stock_info | 股票基本信息 | 股票代码、名称、行业等 | StockInfoCollectJob |
| quote | 最新行情 | 当日行情数据 | LatestPriceCollectJob |
| historical_quote | 历史行情 | 历史日K线 | HistoricalPriceCollectJob |
| balance_sheet | 资产负债表 | 季度财报 | StatementService.collect_balance_sheet |
| income | 利润表 | 季度财报 | StatementService.collect_income |
| cash_flow | 现金流量表 | 季度财报 | StatementService.collect_cash_flow |
| dividend | 分红数据 | 分红送转 | StatementService.collect_dividend |
| main_business | 主营业务 | 主营业务构成 | MainBusinessCollectJob |
| capital | 股本变动 | 股本变更历史 | CapitalCollectJob |
| valuation | 估值数据 | PE/PB等估值指标 | ValuationCollectJob |

---

## 5. Django 模型设计

### CollectJob (采集任务)

```python
class CollectJob(models.Model):
    STATUS_CHOICES = [
        ('PENDING', '待执行'),
        ('RUNNING', '执行中'),
        ('SUCCESS', '成功'),
        ('FAILED', '失败'),
    ]
    
    id = models.BigAutoField(primary_key=True)
    data_type = models.CharField(max_length=50)  # 数据类型
    symbols = models.JSONField(default=list)     # 股票列表
    params = models.JSONField(default=dict)      # 其他参数
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    message = models.TextField(null=True, blank=True)  # 错误信息或统计
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'collector_collect_job'
        ordering = ['-created_at']
```

---

## 6. 前端页面设计

### 6.1 仪表盘 (DashboardView)

**布局**
- 顶部：4 个统计卡片（股票总数、行情数据量、财报数据量、今日采集任务）
- 中部：最近采集任务列表（状态、类型、时间、操作）
- 底部：各数据类型数据量趋势图（可选）

### 6.2 数据完整性检查 (DataCheckView)

**左侧筛选面板**
- 数据类型选择器（单选）
- 股票选择器（支持搜索、全选、指数成分股）
- 时间范围选择器

**右侧结果展示**
- 完整性统计表格（按股票/按日期）
- 缺失详情列表
- 一键补采按钮

### 6.3 采集任务管理 (CollectTaskView)

**配置区域**
- 数据类型选择器（多选）
- 股票选择器（支持搜索、指数成分股）
- 时间范围选择（部分类型需要）
- 高级选项（折叠）

**操作区域**
- 立即执行按钮
- 执行进度显示

**任务列表**
- 任务历史表格
- 状态筛选
- 详情查看

### 6.4 股票列表 (StockListView)

**功能**
- 股票搜索
- 分页表格展示
- 点击查看详情/相关数据

---

## 7. 技术栈详情

### 7.1 后端

```
# backend/requirements.txt
Django>=4.2
djangorestframework>=3.14
django-cors-headers>=4.3
django-extensions>=3.2
whitenoise>=6.6
mysqlclient>=2.2
APScheduler>=3.10

# 现有依赖
cement>=3.0.10
PyYAML>=6.0
colorlog>=6.8
akshare>=1.18.0
tushare>=1.3.6
pandas>=2.1
requests>=2.28
```

### 7.2 前端

```json
{
  "dependencies": {
    "vue": "^3.5",
    "vue-router": "^4.6",
    "element-plus": "^2.13",
    "@element-plus/icons-vue": "^2.3",
    "axios": "^1.6",
    "ag-grid-vue3": "^35.1",
    "ag-grid-community": "^35.1",
    "chart.js": "^4.5",
    "vue-chartjs": "^5.3"
  },
  "devDependencies": {
    "typescript": "~5.9",
    "vite": "^5.4",
    "@vitejs/plugin-vue": "^5.1",
    "vue-tsc": "^2.1"
  }
}
```

---

## 8. 配置示例

### 8.1 Django Settings (base.py)

```python
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django_extensions',
    'rest_framework',
    'rest_framework.authtoken',
    'corsheaders',
    'collector',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'collector.middlewares.DevTokenMiddleware',  # 开发环境认证
]

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20
}
```

### 8.2 Vite Config

```typescript
export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      }
    }
  }
})
```

---

## 9. 实施步骤

### Phase 1: 后端基础架构 (预计 2-3 小时)

1. **创建目录结构**
   - 创建 backend/ 目录
   - 移动现有 saa_collector/ 到 backend/saa_collector/
   
2. **初始化 Django 项目**
   - 创建 config/ 配置目录
   - 创建 collector/ app
   - 配置 settings (数据库、认证、日志)
   
3. **集成 APScheduler**
   - 在 Django 启动时初始化 scheduler
   - 保留现有定时任务配置

### Phase 2: 后端 API 开发 (预计 3-4 小时)

1. **认证模块**
   - 实现 Token 认证
   - 实现 DevTokenMiddleware
   
2. **数据状态 API**
   - 实现 data-status 接口
   - 实现 data-completeness 接口
   
3. **采集任务 API**
   - 实现 CollectJob 模型
   - 实现各类型采集接口
   - 实现异步任务执行
   
4. **股票信息 API**
   - 实现股票列表接口
   - 实现股票详情接口

### Phase 3: 前端开发 (预计 4-5 小时)

1. **项目初始化**
   - 创建 Vue 3 + Vite 项目
   - 配置 Element Plus、路由、axios
   
2. **基础组件**
   - StockSelector 组件
   - DateRangePicker 组件
   - DataTypeSelector 组件
   
3. **页面开发**
   - 登录页面
   - 仪表盘页面
   - 数据完整性检查页面
   - 采集任务管理页面
   - 股票列表页面

### Phase 4: 集成与部署 (预计 1-2 小时)

1. **前后端联调**
   - 配置 vite 代理
   - 测试各功能模块
   
2. **部署配置**
   - 编写 docker-compose.yml
   - 编写 Dockerfile
   - 更新 Makefile

---

## 10. 风险与注意事项

1. **数据库兼容** - 现有数据表不需要迁移，Django 使用相同的 MySQL 数据库
2. **CLI 保留** - cement CLI 功能保留，可继续使用命令行采集
3. **调度器集成** - APScheduler 需要在 Django 启动时正确初始化
4. **并发安全** - 采集任务执行时需要考虑并发控制，避免重复执行

---

## 11. 后续扩展

1. **指数成分股** - 支持选择指数（沪深300、中证500等）批量采集
2. **采集日志** - 详细的采集日志查看
3. **数据导出** - 支持导出数据到 Excel/CSV
4. **告警通知** - 数据缺失或采集失败时发送通知

---

## 12. Dockerfile 配置

### 12.1 backend/Dockerfile

```dockerfile
FROM python:3.10-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

# 安装系统依赖
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        default-libmysqlclient-dev \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install gunicorn

# 复制应用代码
COPY . .

# 收集静态文件
RUN python manage.py collectstatic --noinput

EXPOSE 8000

# 入口脚本
COPY entrypoint.py .
ENTRYPOINT ["python", "entrypoint.py"]
```

### 12.2 backend/entrypoint.py

```python
#!/usr/bin/env python3
import os
import sys
import subprocess

def main():
    service = os.getenv("SERVICE", "gunicorn")

    if service == "runserver":
        # Django 开发服务器
        cmd = [
            "python", "manage.py", "runserver",
            f"0.0.0.0:{os.getenv('PORT', '8000')}"
        ]
    elif service == "scheduler":
        # 只启动调度器（无 Django Web 服务）
        from saa_collector.scheduler import Scheduler
        Scheduler().start()
    else:
        # 默认 gunicorn 生产模式
        cmd = [
            "gunicorn",
            "--bind", f"0.0.0.0:{os.getenv('PORT', '8000')}",
            "--workers", os.getenv("GUNICORN_WORKERS", "1"),
            "--threads", os.getenv("GUNICORN_THREADS", "4"),
            "--access-logfile", "-",
            "--error-logfile", "-",
            "config.wsgi:application",
        ]

    print(f"Starting: {' '.join(cmd)}")
    sys.exit(subprocess.run(cmd).returncode)

if __name__ == "__main__":
    main()
```

### 12.3 frontend/Dockerfile

```dockerfile
# 构建阶段
FROM node:20-alpine AS builder
WORKDIR /app

# 复制依赖文件
COPY package.json .npmrc* ./

# 安装依赖
RUN npm install --prefer-offline --no-audit

# 复制源代码
COPY . .

# 构建应用
RUN npm run build

# 生产阶段
FROM nginx:alpine

# 复制构建产物
COPY --from=builder /app/dist /usr/share/nginx/html

# 复制 nginx 配置
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
```

### 12.4 frontend/nginx.conf

```nginx
server {
    listen 80;
    server_name localhost;
    
    root /usr/share/nginx/html;
    index index.html;

    # 静态资源缓存
    location /assets {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # API 代理到后端
    location /api {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # SPA 路由支持
    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

### 12.5 docker-compose.yml (根目录)

```yaml
version: '3.8'

services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - DATABASE_HOST=${DATABASE_HOST:-db}
      - DATABASE_NAME=${DATABASE_NAME:-saa_collector}
      - DATABASE_USER=${DATABASE_USER:-root}
      - DATABASE_PASSWORD=${DATABASE_PASSWORD:-password}
      - SECRET_KEY=${SECRET_KEY:-your-secret-key}
      - DEBUG=${DEBUG:-False}
      - SERVICE=gunicorn
    volumes:
      - ./backend:/app
    depends_on:
      - db

  frontend:
    build: ./frontend
    ports:
      - "80:80"
    depends_on:
      - backend

  scheduler:
    build: ./backend
    environment:
      - DATABASE_HOST=${DATABASE_HOST:-db}
      - DATABASE_NAME=${DATABASE_NAME:-saa_collector}
      - DATABASE_USER=${DATABASE_USER:-root}
      - DATABASE_PASSWORD=${DATABASE_PASSWORD:-password}
      - SECRET_KEY=${SECRET_KEY:-your-secret-key}
      - SERVICE=scheduler
    volumes:
      - ./backend:/app
    depends_on:
      - db

  db:
    image: mysql:8.0
    environment:
      - MYSQL_ROOT_PASSWORD=${DATABASE_PASSWORD:-password}
      - MYSQL_DATABASE=${DATABASE_NAME:-saa_collector}
    volumes:
      - mysql_data:/var/lib/mysql
    ports:
      - "3306:3306"

volumes:
  mysql_data:
```

### 12.6 开发环境配置

开发时使用 vite 代理，无需 nginx：

```yaml
# docker-compose.dev.yml
version: '3.8'

services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - DATABASE_HOST=db
      - DATABASE_NAME=saa_collector
      - DATABASE_USER=root
      - DATABASE_PASSWORD=password
      - SECRET_KEY=dev-secret-key
      - DEBUG=True
      - SERVICE=runserver
      - DEV_MODE_TOKEN=dev-token-for-ai-collab
    volumes:
      - ./backend:/app
    depends_on:
      - db

  db:
    image: mysql:8.0
    environment:
      - MYSQL_ROOT_PASSWORD=password
      - MYSQL_DATABASE=saa_collector
    volumes:
      - mysql_data:/var/lib/mysql
    ports:
      - "3306:3306"

volumes:
  mysql_data:
```

前端开发服务器独立运行：
```bash
cd frontend
npm run dev  # vite 代理 /api 到 localhost:8000
```
