# UCenter 登录集成计划

> 日期: 2026-04-13
> 目标: 集成 Discuz X5.0 UCenter 2.0 实现管理员登录认证

## 背景

SAA Collector 部署到生产环境后，所有 API 要求 `IsAuthenticated`，但前端没有登录功能。
本应用仅供管理员使用，普通用户不允许访问。

## 设计决策

- **认证源**: UCenter 2.0 (Discuz X5.0) — 用户名/密码由 UCenter 验证
- **权限控制**: 管理员白名单 (`UC_ADMIN_USERS` 环境变量)，不在白名单的用户即使密码正确也拒绝
- **Token 机制**: DRF Token (已有 `rest_framework.authtoken`)
- **用户同步**: 首次登录时自动创建本地 Django User，不存密码
- **开发环境**: 保持现有 `DEV_MODE_TOKEN` 机制不变

## 架构

```
浏览器                    Backend (Django)                UCenter Server
  │                           │                               │
  │  POST /api/login/         │                               │
  │  {username, password}     │                               │
  │──────────────────────────►│                               │
  │                           │  HTTP POST                    │
  │                           │  uc_user_login(user, pwd)     │
  │                           │──────────────────────────────►│
  │                           │                               │
  │                           │  <uid, username, email>       │
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

## 实施步骤

### Step 1: UCenter Client 模块

新建 `backend/saa_collector/ucenter_client/` 目录:

```
ucenter_client/
├── __init__.py       # 导出 UCenterClient
├── authcode.py       # AuthCode 加密/解密 (移植自 PHP uc_authcode)
├── client.py         # UCenterClient 类 — HTTP 通信
└── config.py         # 配置常量 (UC_API, UC_KEY, UC_APPID)
```

#### 1.1 authcode.py — AuthCode 算法

UCenter 使用自研的 `authcode()` 可逆加密算法，密钥为 `UC_KEY`。

核心逻辑:
1. `key = md5(UC_KEY)`
2. `keya = md5(key[:16])`, `keyb = md5(key[16:])`
3. 加密时生成 4 字节随机 `keyc`，解密时从密文前 4 字节取
4. `cryptkey = keya + md5(keya + keyc)` — 64 字节加密密钥
5. RC4 流加密 (256 字节 S-Box 初始化 + swap)
6. 加密结果 = `keyc + base64(result).strip('=')`
7. 解密时验证 expiry + md5 校验

参考: `ghoulr/ucenter` (Python 2)，需移植为 Python 3 + `bytes` 处理

#### 1.2 client.py — UCenterClient

只需实现两个 API 调用:

| 方法 | UCenter API | 说明 |
|------|-----------|------|
| `login(username, password)` | `m=user&a=login` | 验证用户名密码 |
| `get_user(username, isuid=0)` | `m=user&a=get_user` | 获取用户信息 |

请求流程:
```
1. 拼接参数: username=xxx&password=xxx&isuid=0&checkques=0
2. 追加: &agent={md5(User-Agent)}&time={timestamp}
3. AuthCode 加密 (UC_KEY)
4. URL encode
5. POST 到 {UC_API}/index.php
   body: m=user&a=login&inajax=2&release=xxx&input={加密数据}&appid={APPID}
6. 解析 XML 响应
```

`login()` 返回值:
```
[0] >0: uid (成功), -1: 用户不存在, -2: 密码错
[1] username
[2] password (md5)
[3] email
[4] duplicate
```

#### 1.3 config.py

```python
import os

UC_API = os.getenv('UC_API', '')
UC_KEY = os.getenv('UC_KEY', '')
UC_APPID = os.getenv('UC_APPID', '')
UC_IP = os.getenv('UC_IP', '')
UC_CHARSET = os.getenv('UC_CHARSET', 'utf-8')

UC_ADMIN_USERS = [u.strip() for u in os.getenv('UC_ADMIN_USERS', '').split(',') if u.strip()]
```

### Step 2: Backend Login API

#### 2.1 LoginView (`backend/saa_collector/views.py`)

```python
class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get('username', '')
        password = request.data.get('password', '')

        # 1. UCenter 验证
        client = UCenterClient()
        result = client.login(username, password)

        if not result or result.get('uid', 0) <= 0:
            return Response({'error': '用户名或密码错误'}, status=401)

        # 2. 管理员白名单检查
        if username not in settings.UC_ADMIN_USERS:
            return Response({'error': '无权访问此系统'}, status=403)

        # 3. 创建/获取本地用户
        user, _ = User.objects.get_or_create(
            username=username,
            defaults={'email': result.get('email', '')}
        )

        # 4. 签发 Token
        token, _ = Token.objects.get_or_create(user=user)

        return Response({
            'token': token.key,
            'username': user.username,
        })
```

#### 2.2 URL 路由

```python
# saa_collector/urls.py
path('login/', views.LoginView.as_view(), name='login'),
```

#### 2.3 Settings 配置

```python
# config/settings/base.py
UC_ADMIN_USERS = [u.strip() for u in os.getenv('UC_ADMIN_USERS', '').split(',') if u.strip()]
```

### Step 3: Frontend Login 页面

#### 3.1 前端 API 函数 (`frontend/src/utils/api.ts`)

```typescript
export const login = async (username: string, password: string) => {
  const response = await api.post('/login/', { username, password })
  return response.data
}
```

#### 3.2 Login 页面 (`frontend/src/views/LoginView.vue`)

- Element Plus 表单 (username + password)
- 调用 `login()` API
- 成功后 `auth.setToken(token)` + 跳转首页
- 错误提示 (401: 用户名或密码错误, 403: 无权访问)

#### 3.3 路由守卫 (`frontend/src/router/index.ts`)

```typescript
router.beforeEach((to, from, next) => {
  if (to.path !== '/login' && !auth.isAuthenticated()) {
    next('/login')
  } else if (to.path === '/login' && auth.isAuthenticated()) {
    next('/')
  } else {
    next()
  }
})
```

添加 `/login` 路由:
```typescript
{
  path: '/login',
  name: 'login',
  component: LoginView
}
```

#### 3.4 App.vue 调整

无需改动布局，router guard 已确保未登录只能看 `/login`。
Login 页面自身不使用 `App.vue` 的侧边栏布局。

#### 3.5 401 拦截器调整

现有 401 拦截器跳转 `/login`，路径正确无需修改。
但需注意 baseURL 的问题: 现在跳转 `window.location.href = '/login'`，
生产环境应跳转 `/admin/collector/login`。

修正:
```typescript
if (error.response?.status === 401) {
  localStorage.removeItem('token')
  window.location.href = import.meta.env.BASE_URL + 'login'
}
```

### Step 4: 环境配置

#### 4.1 生产环境 Docker 环境变量

```yaml
# saa-collector-backend docker-compose
environment:
  - UC_API=https://bbs.iguuu.com/uc_server
  - UC_KEY=your-uc-communication-key
  - UC_APPID=2
  - UC_ADMIN_USERS=admin,zhangsan
```

#### 4.2 UCenter 后台配置

1. 登录 UCenter 管理后台
2. 应用管理 → 添加应用
3. 应用类型: 自定义
4. 应用名称: SAA Collector
5. 应用 URL: `https://www.iguuu.com/admin/collector/`
6. 通信密钥: 与 `UC_KEY` 一致
7. 应用 IP: (SAA Collector 服务器 IP)
8. 确认通信成功

#### 4.3 开发环境

开发环境保持不变，通过 `DEV_MODE_TOKEN` + `DevTokenAuthentication` 绕过。
Login 功能在生产环境 (`UC_API` 有值) 时启用。

## 文件变更清单

### 新建文件

| 文件 | 说明 |
|------|------|
| `backend/saa_collector/ucenter_client/__init__.py` | 模块导出 |
| `backend/saa_collector/ucenter_client/authcode.py` | AuthCode 加解密 |
| `backend/saa_collector/ucenter_client/client.py` | UCenter HTTP 客户端 |
| `backend/saa_collector/ucenter_client/config.py` | 配置 |
| `frontend/src/views/LoginView.vue` | 登录页面 |

### 修改文件

| 文件 | 改动 |
|------|------|
| `backend/saa_collector/views.py` | 新增 `LoginView` |
| `backend/saa_collector/urls.py` | 添加 `login/` 路由 |
| `backend/config/settings/base.py` | 添加 `UC_ADMIN_USERS` 配置 |
| `frontend/src/utils/api.ts` | 添加 `login()` 函数，修正 401 跳转路径 |
| `frontend/src/router/index.ts` | 添加 `/login` 路由 + beforeEach guard |

## 风险点

1. **AuthCode 移植精度**: PHP 的 `authcode()` 涉及字节级操作，Python 3 的 `bytes` vs `str` 处理需格外小心。建议用 UCenter 已知测试用例验证。
2. **Discuz X5.0 API 变化**: Discuz X3.5 开始 API 追加了 `&m=module&a=action&appid=UC_APPID` 到加密参数中。X5.0 + UCenter 2.0 可能也有变化，需实测验证。
3. **开发环境兼容**: 开发环境没有 UCenter，Login API 应优雅降级或直接由 DevToken 覆盖。

## 验证方式

1. **单元测试**: AuthCode 加密 → 解密 → 验证一致性
2. **集成测试**: 启动后端，POST `/api/login/` 验证流程
3. **E2E 测试**: Playwright 测试登录页面流程
4. **生产验证**: 部署后在 UCenter 后台确认通信成功
