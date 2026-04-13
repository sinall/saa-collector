# SAA Collector 部署架构

## 架构总览

```
Internet
    │
    ▼
┌─────────────────────────┐
│   Nginx (Host)          │
│   saa.conf              │
│                         │
│   /admin/collector/api/ ────► Backend (Docker) :8004
│   /admin/collector/static/─► Backend (Docker) :8004
│   /admin/collector/     ────► Frontend (Docker) :8003
└─────────────────────────┘

┌─────────────────────────────────────────────┐
│   Docker Compose (Production)               │
│                                             │
│   saa-collector-frontend  :80 → :8003      │
│   saa-collector-backend   :8000 → :8004     │
│   saa-collector-scheduler (no port)         │
└─────────────────────────────────────────────┘
```

## 端口映射

| 服务 | 容器端口 | 宿主机端口 | 说明 |
|------|---------|-----------|------|
| Frontend (Nginx) | 80 | 8003 | Vue 3 SPA 静态文件 |
| Backend (Gunicorn) | 8000 | 8004 | Django REST API |
| Scheduler | - | - | 定时任务，无 HTTP 端口 |

## Nginx 路由规则

宿主机 Nginx (`/etc/nginx/conf.d/saa.conf`) 负责将外部请求分发到对应的 Docker 服务。

### 路由表

| 外部路径 | 目标 | 说明 |
|---------|------|------|
| `/admin/collector/api/*` | `http://127.0.0.1:8004/api/*` | API 请求 → Backend |
| `/admin/collector/static/*` | `http://127.0.0.1:8004/admin/collector/static/*` | Django 静态资源 (CSS/JS/admin) |
| `/admin/collector/*` | `http://127.0.0.1:8003/*` | 前端页面 → Frontend |

### 路径重写规则

- **API 路径**：`/admin/collector/api/xxx` → `/api/xxx`（Nginx strip 前缀）
- **静态资源**：`/admin/collector/static/xxx` → `/admin/collector/static/xxx`（透传，Django 的 `STATIC_URL` + `FORCE_SCRIPT_NAME` 处理）
- **前端页面**：`/admin/collector/xxx` → `/xxx`（Nginx strip `/admin/collector` 前缀）

## Frontend 部署

### 容器镜像

```yaml
saa-collector-frontend:
  image: crpi-lj3q4y8fz3cwi92h.cn-hangzhou.personal.cr.aliyuncs.com/sinall/saa-collector-frontend:latest
  container_name: saa-collector-frontend
  ports:
    - "8003:80"
  restart: unless-stopped
```

### 构建流程 (Dockerfile)

1. **Stage 1 (builder)**：`node:20-alpine` → `npm install` → `npm run build`
2. **Stage 2 (serve)**：`nginx:alpine` → 将 `dist/` 复制到 `/usr/share/nginx/html`

### Vite 构建配置

- `base: '/admin/collector/'` — 所有资源引用路径带此前缀
- 开发代理：`/admin/collector/api` → rewrite → `http://localhost:8000/api`

### 容器内 Nginx 配置

```nginx
server {
    listen 80;
    root /usr/share/nginx/html;

    # 静态资源缓存
    location /assets {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # API 代理 (仅 Docker 内部网络使用，生产环境由宿主机 Nginx 处理)
    location /api {
        proxy_pass http://saa-collector-backend:8000;
    }

    # SPA fallback
    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

## Backend 部署

### 构建流程 (Dockerfile)

1. `python:3.10-slim` 基础镜像
2. 安装 `gcc`、`default-libmysqlclient-dev`、`pkg-config`
3. `pip install -r requirements.txt` + `gunicorn`
4. `python manage.py collectstatic --noinput`
5. 入口：`entrypoint.py`

### 入口脚本 (entrypoint.py)

根据 `SERVICE` 环境变量决定运行模式：

| SERVICE 值 | 行为 |
|------------|------|
| `gunicorn` (默认) | `gunicorn --bind 0.0.0.0:8000 --workers 1 --threads 4` |
| `runserver` | `python manage.py runserver 0.0.0.0:8000` |
| `scheduler` | 启动 `saa_collector.scheduler.Scheduler` |

### Django Settings

使用多环境配置：
- **Base**: `config/settings/base.py` — 共享配置
- **Development**: `config/settings/development.py` — `DEBUG=True`
- **Production**: `config/settings/production.py` — `DEBUG=False`

通过 `DJANGO_SETTINGS_MODULE` 环境变量选择。

### URL 结构

```
/api/         → Django REST Framework API
/admin/       → Django Admin
/health/      → Health Check
/static/      → Django 静态文件 (collectstatic)
```

### 关键 Django 配置

| 配置项 | 值 | 说明 |
|-------|---|------|
| `STATIC_URL` | `/static/` | Django 静态文件 URL 前缀 |
| `STATIC_ROOT` | `BASE_DIR / 'staticfiles'` | collectstatic 输出目录 |
| `STATICFILES_STORAGE` | `whitenoise.storage.CompressedStaticFilesStorage` | WhiteNoise 压缩 |
| `DATABASE ENGINE` | `mysql.connector.django` | MySQL 连接器 |
| `CORS_ALLOW_ALL_ORIGINS` | `True` | 允许所有跨域 |
| `DATA_SOURCE` | `tushare` (默认) | 数据源选择 |

## 开发环境 vs 生产环境

### 开发环境

| 项目 | 开发 | 生产 |
|------|------|------|
| Frontend | Vite dev server (`:3000`) | Docker Nginx (`:8003`) |
| Backend | `runserver` (`:8000`) | Gunicorn (`:8004`) |
| 数据库 | Aliyun RDS | Aliyun RDS |
| 入口 | `backend/start.sh` (pyenv) | `docker-compose` |
| Auth Token | `DEV_MODE_TOKEN` | Session/Token |
| DEBUG | `True` | `False` |

### 开发环境启动

```bash
# Backend
cd backend && ./start.sh
# 使用 pyenv + collector-env, 自动加载 .envs/development.env

# Frontend
cd frontend && npm run dev
# Vite dev server on :3000, 代理 API 到 :8000
```

### 开发代理配置 (vite.config.ts)

```typescript
proxy: {
  '/api': {
    target: 'http://localhost:8000',
    changeOrigin: true,
  },
  '/admin/collector/api': {
    target: 'http://localhost:8000',
    changeOrigin: true,
    rewrite: (path) => path.replace('/admin/collector/api', '/api')
  }
}
```

## 请求流程

### 生产环境 - 前端页面请求

```
Browser: GET /admin/collector/
    → Host Nginx: proxy_pass http://127.0.0.1:8003/
    → Frontend Container Nginx: try_files → /index.html
    → 返回 Vue SPA
```

### 生产环境 - API 请求

```
Browser: GET /admin/collector/api/data-types/
    → Host Nginx: proxy_pass http://127.0.0.1:8004/api/data-types/
    → Backend Gunicorn: Django URL /api/data-types/
    → 返回 JSON
```

### 生产环境 - 前端静态资源

```
Browser: GET /admin/collector/assets/index-abc123.js
    → Host Nginx: proxy_pass http://127.0.0.1:8003/assets/index-abc123.js
    → Frontend Container Nginx: 返回 /usr/share/nginx/html/assets/index-abc123.js
```

### 生产环境 - Django 静态资源 (Admin 等)

```
Browser: GET /admin/collector/static/admin/css/base.css
    → Host Nginx: proxy_pass http://127.0.0.1:8004/admin/collector/static/admin/css/base.css
    → Backend Gunicorn: WhiteNoise 返回 staticfiles/admin/css/base.css
```

## 环境变量参考

### Backend 必需环境变量

| 变量 | 必需 | 默认值 | 说明 |
|------|------|-------|------|
| `DJANGO_SETTINGS_MODULE` | 是 | - | `config.settings.production` |
| `SECRET_KEY` | 是 | - | Django secret key |
| `DATABASE_HOST` | 是 | `localhost` | 数据库主机 |
| `DATABASE_NAME` | 是 | `saa` | 数据库名 |
| `DATABASE_USER` | 是 | `root` | 数据库用户 |
| `DATABASE_PASSWORD` | 是 | - | 数据库密码 |
| `SERVICE` | 否 | `gunicorn` | 服务模式 |
| `GUNICORN_WORKERS` | 否 | `1` | Gunicorn worker 数 |
| `GUNICORN_THREADS` | 否 | `4` | Gunicorn thread 数 |
| `DATA_SOURCE` | 否 | `tushare` | 数据源 (akshare/tushare) |
| `DEBUG` | 否 | `False` | 调试模式 |

## 镜像仓库

- **Frontend**: `crpi-lj3q4y8fz3cwi92h.cn-hangzhou.personal.cr.aliyuncs.com/sinall/saa-collector-frontend:latest`
- **Backend**: (待确认，参考 docker-compose.yml 中的 build 配置)

## 注意事项

1. **路径前缀**：前端通过 `vite.config.ts` 的 `base: '/admin/collector/'` 确保所有资源引用带有正确前缀
2. **静态文件**：Django 使用 WhiteNoise 中间件直接服务静态文件，无需额外静态文件服务器
3. **数据库**：使用阿里云 RDS MySQL，开发环境直连远程数据库
4. **缓存**：宿主机 Nginx 对 `/admin/collector/static/` 设置 1 年缓存 + gzip 压缩
