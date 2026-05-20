# E2E 测试指南

> 当前测试规范见 `../openspec/specs/collector-testing/spec.md`。本文保留 Playwright 操作指南和本地调试细节。

本项目使用 **Playwright** 进行端到端测试，用于验证页面展示是否合理、是否有错误。

## 快速开始

### 首次设置

```bash
# 进入前端目录
cd frontend

# 安装依赖
npm install

# 安装 Playwright 浏览器
npx playwright install
```

### 运行测试

#### 1. UI 模式（推荐用于本地开发）

```bash
cd frontend
npm run test:e2e:ui
```

**优点**：
- 可视化测试执行
- 时间旅行调试
- 实时查看 DOM 快照
- 逐步执行测试
- 适合调试和开发

#### 2. 命令行模式

```bash
# 运行所有测试
cd frontend
npm run test:e2e

# 只运行 Chromium 浏览器测试（更快）
npm run test:e2e:chromium
```

#### 3. 调试模式

```bash
cd frontend
npm run test:e2e:debug
```

**功能**：
- 自动暂停在每个操作
- 逐步执行
- 查看页面状态
- 适合调试失败测试

#### 4. 查看测试报告

```bash
cd frontend
npm run test:e2e:report
```

测试运行后会自动生成 HTML 报告。

## package.json 命令

当前 `frontend/package.json` 提供以下测试脚本：

| 命令 | 说明 |
| --- | --- |
| `npm run test:e2e` | 运行全部 Playwright 测试 |
| `npm run test:e2e:chromium` | 只运行 Chromium 项目 |
| `npm run test:e2e:ui` | 打开 Playwright UI |
| `npm run test:e2e:debug` | 调试模式 |
| `npm run test:e2e:report` | 查看 HTML 报告 |

## 测试覆盖范围

### 已测试页面

- ✅ **Dashboard** (`/`)
  - 页面加载
  - 无错误
  - 导航显示

- ✅ **完整性报告列表** (`/integrity-reports`)
  - 页面加载
  - 筛选面板
  - 报告列表显示
  - 创建报告流程
  - 查看详情

- ✅ **完整性报告详情** (`/integrity-reports/:id`)
  - 页面加载
  - 统计卡片
  - 数据表格
  - 快速筛选
  - 分页功能
  - 生成计划按钮

- ✅ **数据浏览-股票** (`/data-browse/stock`)
  - 页面加载
  - 无错误

- ✅ **数据浏览-类型** (`/data-browse/type`)
  - 页面加载
  - 无错误

- ✅ **采集计划** (`/collect-plans`)
  - 页面加载
  - 无错误
  - 服务端筛选和分页
  - 详情页轮询不显示整页加载蒙层
  - 详情页之间路由切换重新加载

- ✅ **采集调度** (`/collect-schedules`)
  - 页面加载
  - 无错误
  - 手动触发后跳转到后端返回的计划详情

- ✅ **即时采集**
  - 创建采集计划
  - 可选立即执行

## 测试重点

当前阶段测试重点：

1. **页面能否正常加载** - 确保所有页面都能成功渲染
2. **组件是否正确渲染** - 验证关键元素可见
3. **是否有 JavaScript 错误** - 捕获页面错误
4. **Mock 数据是否正确显示** - 验证数据展示
5. **UI 布局是否合理** - 检查基本布局

## 测试结构

```
frontend/
├── e2e/
│   ├── pages/              # 页面测试文件
│   │   ├── dashboard.spec.ts
│   │   ├── integrity-reports.spec.ts
│   │   ├── integrity-report-detail.spec.ts
│   │   ├── data-browse.spec.ts
│   │   ├── collect.spec.ts
│   │   ├── collect-detail.spec.ts
│   │   ├── collect-schedules.spec.ts
│   │   └── instant-collect.spec.ts
│   ├── utils/              # 工具函数
│   │   └── helpers.ts
│   └── global-setup.ts     # 全局设置
├── playwright.config.ts    # Playwright 配置
└── test-results/           # 测试结果（截图、录像等）
    └── screenshots/
```

## 添加新测试

### 1. 创建测试文件

在 `frontend/e2e/pages/` 创建新文件，例如 `new-page.spec.ts`：

```typescript
import { test, expect } from '@playwright/test'
import { waitForPageLoad } from '../utils/helpers'

test.describe('New Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/new-page')
    await waitForPageLoad(page)
  })

  test('should load without errors', async ({ page }) => {
    const errors: string[] = []
    page.on('pageerror', error => errors.push(error.message))
    
    await waitForPageLoad(page)
    
    expect(errors).toHaveLength(0)
  })

  test('should display main content', async ({ page }) => {
    const mainElement = page.locator('.main-content')
    await expect(mainElement).toBeVisible()
  })
})
```

### 2. 使用工具函数

```typescript
import { 
  waitForPageLoad, 
  checkNoPageErrors,
  takeScreenshot 
} from '../utils/helpers'

// 等待页面加载
await waitForPageLoad(page)

// 检查页面错误
const errors = await checkNoPageErrors(page)

// 截图
await takeScreenshot(page, 'test-name')
```

### 3. 常用断言

```typescript
// 元素可见
await expect(locator).toBeVisible()

// 文本内容
await expect(locator).toHaveText('Expected Text')

// 数量
expect(await locator.count()).toBeGreaterThan(0)

// URL
expect(page.url()).toMatch(/pattern/)
```

## 调试技巧

### 1. 使用 page.pause()

```typescript
test('debug test', async ({ page }) => {
  await page.goto('/')
  await page.pause() // 暂停执行，打开调试器
  await page.click('button')
})
```

### 2. 查看页面状态

```typescript
// 截图
await page.screenshot({ path: 'debug.png' })

// 打印 HTML
console.log(await page.content())

// 查看元素
console.log(await locator.textContent())
```

### 3. 慢速执行

```typescript
// 在 playwright.config.ts 中
use: {
  launchOptions: {
    slowMo: 1000, // 每个操作延迟 1 秒
  }
}
```

## 配置说明

### playwright.config.ts

```typescript
export default defineConfig({
  testDir: './e2e',              // 测试目录
  fullyParallel: true,           // 并行执行
  retries: 0,                    // 失败重试次数（本地开发）
  workers: undefined,            // 并发进程数（默认自动）
  reporter: [['html'], ['list']], // 报告格式
  
  use: {
    baseURL: 'http://localhost:3001',  // 基础 URL
    trace: 'on-first-retry',           // 失败时记录追踪
    screenshot: 'only-on-failure',     // 失败时截图
    video: 'retain-on-failure',        // 失败时录像
  },

  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
    { name: 'webkit', use: { ...devices['Desktop Safari'] } },
  ],

  webServer: {
    command: 'npm run dev',           // 自动启动开发服务器
    url: 'http://localhost:3001',
    reuseExistingServer: true,        // 复用已运行的服务器
  },
})
```

## 常见问题

### Q: 测试失败时如何调试？

**A:** 使用以下方法：
1. 运行 `npm run test:e2e:debug` 进入调试模式
2. 运行 `npm run test:e2e:ui` 使用 UI 模式
3. 查看生成的截图和录像
4. 查看 HTML 测试报告

### Q: 如何只运行特定测试？

**A:** 使用 `test.only()` 或命令行过滤：

```typescript
test.only('this test only', async ({ page }) => {
  // ...
})
```

```bash
npx playwright test -g "test name pattern"
```

### Q: 测试很慢怎么办？

**A:** 
1. 只运行 Chromium: `npm run test:e2e:chromium`
2. 禁用 WebKit 和 Firefox（修改 playwright.config.ts）
3. 使用 `--workers=1` 串行执行

### Q: 如何处理动态内容？

**A:** 使用智能等待：

```typescript
// 等待元素出现
await page.waitForSelector('.element')

// 等待网络空闲
await page.waitForLoadState('networkidle')

// 等待特定请求
await page.waitForResponse('**/api/data')
```

## 最佳实践

1. **使用有意义的测试名称** - 描述测试意图
2. **每个测试独立** - 不依赖其他测试
3. **使用 beforeEach** - 统一设置前置条件
4. **避免硬编码等待** - 使用智能等待
5. **保持测试简单** - 一个测试验证一个功能
6. **定期运行测试** - 确保代码质量

## 参考资源

- [Playwright 官方文档](https://playwright.dev/)
- [Playwright API 参考](https://playwright.dev/docs/api/class-page)
- [最佳实践](https://playwright.dev/docs/best-practices)
