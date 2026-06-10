# SAA Collector 部署架构

> 当前运维参考。生产 Docker Compose、Nginx 配置、内存限制和 env_file 路径以父工作区 `saa-conf/ansible/roles/nginx/files/` 为准；本文件只记录 collector 自身需要理解的路由、镜像和认证行为。当前规范见 `../openspec/specs/collector-deployment-auth/spec.md`。

## 架构总览

```
Internet
    │
    ▼
┌─────────────────────────────────────────────┐
│   nginx container (saa-conf managed)        │
│   /etc/nginx/conf.d/saa.conf                │
│                                             │
│   /admin/collector/api/    ─► backend:8000  │
│   /admin/collector/static/ ─► backend:8000  │
│   /admin/collector/        ─► frontend:80   │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│   Docker Compose (Production)               │
│                                             │
│   saa-collector-frontend  :80               │
│   saa-collector-backend   :8000             │
│   saa-collector-worker                       │
│   saa-collector-scheduler                   │
│   saa-collector-beat                        │
│   network: saa-net                          │
└─────────────────────────────────────────────┘
```

## 生产服务

| 服务 | 端口 | SERVICE | 说明 |
|------|------|---------|------|
| `saa-collector-frontend` | 80 | - | Vue 3 SPA 静态文件 |
| `saa-collector-backend` | 8000 | `gunicorn` | Django REST API |
| `saa-collector-worker` | - | `celery-worker` | collector 队列业务采集 |
| `saa-collector-scheduler` | - | `celery-worker` | scheduler 队列扫描到期日程 |
| `saa-collector-beat` | - | `celery-beat` | 周期性唤醒 scheduler 扫描 |

生产环境这些服务不直接暴露宿主机业务端口，统一接入 `saa-net`，由 nginx 容器通过服务名反代。

## Nginx 路由规则

生产 Nginx 配置由 `saa-conf` 部署到 nginx 容器内的 `/etc/nginx/conf.d/saa.conf`，负责将外部请求分发到对应的 Docker 服务。

### 路由表

| 外部路径 | 目标 | 说明 |
|---------|------|------|
| `/admin/collector/api/*` | `http://saa-collector-backend:8000/api/*` | API 请求 → Backend |
| `/admin/collector/static/*` | `http://saa-collector-backend:8000/admin/collector/static/*` | Django 静态资源 (CSS/JS/admin) |
| `/admin/collector/*` | `http://saa-collector-frontend:80/*` | 前端页面 → Frontend |

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
  networks:
    - saa-net
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

    # API 代理 (仅 Docker 内部网络使用，生产环境由 saa-conf 管理的 nginx 处理)
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
| `celery-worker` | 启动 Celery worker，队列由 `COLLECTOR_CELERY_QUEUE` 指定 |
| `celery-beat` | 启动 Celery beat |

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
| Frontend | Vite dev server (`:3000`) | Docker Nginx (`saa-collector-frontend:80`) |
| Backend | `runserver` (`:8000`) | Gunicorn (`saa-collector-backend:8000`) |
| 数据库 | Aliyun RDS | Aliyun RDS |
| 入口 | `backend/start.sh` (pyenv) | `docker-compose` |
| Auth Token | `DEV_MODE_TOKEN` | UCenter + DRF Token |
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
    → nginx: proxy_pass http://saa-collector-frontend:80/
    → Frontend Container Nginx: try_files → /index.html
    → 返回 Vue SPA
```

### 生产环境 - API 请求

```
Browser: GET /admin/collector/api/data-types/
    → nginx: proxy_pass http://saa-collector-backend:8000/api/data-types/
    → Backend Gunicorn: Django URL /api/data-types/
    → 返回 JSON
```

### 生产环境 - 前端静态资源

```
Browser: GET /admin/collector/assets/index-abc123.js
    → nginx: proxy_pass http://saa-collector-frontend:80/assets/index-abc123.js
    → Frontend Container Nginx: 返回 /usr/share/nginx/html/assets/index-abc123.js
```

### 生产环境 - Django 静态资源 (Admin 等)

```
Browser: GET /admin/collector/static/admin/css/base.css
    → nginx: proxy_pass http://saa-collector-backend:8000/admin/collector/static/admin/css/base.css
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

### UCenter 认证环境变量

| 变量 | 必需 | 默认值 | 说明 |
|------|------|-------|------|
| `UC_API` | 是 | `''` | UCenter 服务端 URL，如 `https://www.iguuu.com/discuz/uc_server` |
| `UC_KEY` | 是 | `''` | UCenter 通信密钥，需与 UCenter 后台一致 |
| `UC_APPID` | 是 | `''` | UCenter 后台分配的应用 ID |
| `UC_ADMIN_USERS` | 是 | `''` | 允许登录的管理员用户名，逗号分隔，如 `admin,zhangsan` |

不配置 `UC_API` 时，开发环境回退到 `admin/admin` 兜底登录。

## 镜像仓库

- **Frontend**: `crpi-lj3q4y8fz3cwi92h.cn-hangzhou.personal.cr.aliyuncs.com/sinall/saa-collector-frontend:latest`
- **Backend/Worker/Scheduler/Beat**: `crpi-lj3q4y8fz3cwi92h.cn-hangzhou.personal.cr.aliyuncs.com/sinall/saa-collector-backend:latest`

## 注意事项

1. **路径前缀**：前端通过 `vite.config.ts` 的 `base: '/admin/collector/'` 确保所有资源引用带有正确前缀
2. **静态文件**：Django 使用 WhiteNoise 中间件直接服务静态文件，无需额外静态文件服务器
3. **数据库**：使用阿里云 RDS MySQL，开发环境直连远程数据库
4. **缓存**：生产 nginx 对 `/admin/collector/static/` 设置 1 年缓存 + gzip 压缩

## 认证系统 (UCenter 集成)

### 架构

```
浏览器                    Backend (Django)                UCenter Server
  │                           │                               │
  │  POST /api/login/         │                               │
  │  {username, password}     │                               │
  │──────────────────────────►│                               │
  │                           │  HTTP POST (AuthCode 加密)     │
  │                           │  uc_user_login(user, pwd)     │
  │                           │──────────────────────────────►│
  │                           │                               │
  │                           │  {uid, username, email}       │
  │                           │◄──────────────────────────────│
  │                           │                               │
  │                           │  uid > 0 ?                    │
  │                           │  username in UC_ADMIN_USERS ? │
  │                           │                               │
  │  {token, username}        │                               │
  │◄──────────────────────────│                               │
  │                           │                               │
  │  后续请求                  │                               │
  │  Authorization: Token xxx │                               │
  │──────────────────────────►│  DRF Token 认证 ✓             │
```

### 认证流程

1. 用户在登录页提交用户名/密码
2. Backend 调用 UCenter API (`uc_user_login`) 验证凭据
3. 验证通过后检查用户名是否在 `UC_ADMIN_USERS` 白名单中
4. 白名单内用户自动创建/获取本地 Django User，签发 DRF Token
5. 前端存储 Token，后续请求通过 `Authorization: Token xxx` 认证

### 依赖

UCenter 客户端作为独立包维护：[sinall/ucenter-python](https://github.com/sinall/ucenter-python)

```txt
# requirements.txt
ucenter-python @ git+https://github.com/sinall/ucenter-python.git@v0.1.0
```

### 开发环境

不配置 `UC_API` 时自动回退到开发模式：用户名 `admin`，密码 `admin`。

## 生产环境部署清单

### 1. Backend 环境变量

添加到 docker-compose 或 .env：

```yaml
environment:
  - UC_API=https://www.iguuu.com/discuz/uc_server
  - UC_KEY=你的通信密钥
  - UC_APPID=21
  - UC_ADMIN_USERS=admin,sinall
```

### 2. 数据库初始化

UCenter 集成登录需要两张表：`auth_user`（本地影子用户）和 `authtoken_token`（DRF Token）。

方式一：migrate 自动建表（推荐）

```bash
docker exec saa-collector-backend python manage.py migrate
```

方式二：手动执行 SQL

```sql
-- 1. 本地用户表（UCenter 验证通过后创建影子记录）
CREATE TABLE IF NOT EXISTS auth_user (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    password VARCHAR(128) NOT NULL,
    last_login DATETIME(6) NULL,
    is_superuser TINYINT(1) NOT NULL DEFAULT 0,
    username VARCHAR(150) NOT NULL UNIQUE,
    first_name VARCHAR(150) NOT NULL DEFAULT '',
    last_name VARCHAR(150) NOT NULL DEFAULT '',
    email VARCHAR(254) NOT NULL DEFAULT '',
    is_staff TINYINT(1) NOT NULL DEFAULT 0,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    date_joined DATETIME(6) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2. DRF Token 表（外键依赖 auth_user，必须后建）
CREATE TABLE IF NOT EXISTS authtoken_token (
    `key` VARCHAR(40) NOT NULL PRIMARY KEY,
    created DATETIME(6) NOT NULL,
    user_id BIGINT NOT NULL UNIQUE,
    FOREIGN KEY (user_id) REFERENCES auth_user (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 3. SQL Schema Migrations

Collector 维护的 MySQL 变更通过 `python manage.py migrate_sql` 执行。

- 迁移文件优先放在 `backend/sql/migrations/*.sql`
- 兼容旧约定的根目录 `backend/upgrade_*.sql` 也会被扫描
- 文件按路径排序后依次执行
- 迁移容器使用同一份镜像和数据库配置，保证发布时的行为和应用版本一致

本地或容器内手工执行：

```bash
cd backend
python manage.py migrate_sql
```

### 4. UCenter 后台配置

1. 登录 UCenter 管理后台：`https://www.iguuu.com/discuz/uc_server`
2. 应用管理 → 添加应用
3. 填写：
   - 应用类型：自定义
   - 应用名称：SAA Collector
   - 应用 URL：`https://www.iguuu.com/admin/collector/`
   - 通信密钥：与 `UC_KEY` 一致
4. 确认通信成功

### 4. 重新构建并部署

```bash
# 生产配置变更通过 saa-conf/ansible 部署。
# 镜像更新后，在 Portainer 或 Ansible 流程中 recreate 对应 collector 容器。
```

### 5. 验证

- 访问 `https://www.iguuu.com/admin/collector/` → 应自动跳转到登录页
- 用 UCenter 管理员账号登录 → 应成功进入系统
- 用普通 Discuz 用户登录 → 应显示「无权访问此系统」
