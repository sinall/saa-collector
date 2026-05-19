import { test, expect } from '@playwright/test'
import { waitForPageLoad, sleep } from '../utils/helpers'

test.describe('Collect Schedule Detail Page', () => {
  test('should load schedule detail without errors', async ({ page }) => {
    const errors: string[] = []
    const failedRequests: string[] = []
    
    // 监听 JavaScript 错误
    page.on('pageerror', error => errors.push(error.message))
    
    // 监听控制台错误
    page.on('console', msg => {
      if (msg.type() === 'error') {
        errors.push(msg.text())
      }
    })
    
    // 监听网络请求失败
    page.on('requestfailed', request => {
      failedRequests.push(`${request.method()} ${request.url()}`)
    })
    
    await page.goto('/collect-schedules/1')
    await waitForPageLoad(page)
    await sleep(1000)
    
    // 应该没有 JavaScript 错误
    expect(errors).toHaveLength(0)
    
    // 应该没有失败的请求
    expect(failedRequests).toHaveLength(0)
  })

  test('should display schedule detail container', async ({ page }) => {
    await page.goto('/collect-schedules/1')
    await waitForPageLoad(page)
    
    const container = page.locator('.collect-schedule-detail')
    await expect(container).toBeVisible()
  })

  test('should show schedule information', async ({ page }) => {
    await page.goto('/collect-schedules/1')
    await waitForPageLoad(page)
    await sleep(500)
    
    // 应该显示描述信息或表格
    const content = page.locator('.el-descriptions, .el-card')
    await expect(content.first()).toBeVisible()
  })
})

test.describe('Collect Plan Edit Page - Browser Navigation', () => {
  test('should not make wrong API call when navigating back from collect-plan-edit to integrity-reports', async ({ page }) => {
    const failedRequests: string[] = []
    const consoleErrors: string[] = []
    
    page.on('requestfailed', request => {
      failedRequests.push(`${request.method()} ${request.url()}`)
    })
    
    page.on('console', msg => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text())
      }
    })
    
    page.on('response', response => {
      if (response.status() === 404) {
        failedRequests.push(`404: ${response.url()}`)
      }
    })
    
    await page.goto('/integrity-reports/1')
    await waitForPageLoad(page)
    await sleep(1000)
    
    await page.goto('/collect-plans/1/edit')
    await waitForPageLoad(page)
    await sleep(1000)
    
    await page.goBack()
    await waitForPageLoad(page)
    await sleep(1000)
    
    const wrongApiCalls = failedRequests.filter(r => 
      r.includes('/api/collect-plans/1/') || r.includes('404')
    )
    expect(wrongApiCalls).toHaveLength(0)
    
    const wrongConsoleErrors = consoleErrors.filter(e => 
      e.includes('404') || e.includes('Not Found')
    )
    expect(wrongConsoleErrors).toHaveLength(0)
  })
})

test.describe('Collect Plan Detail Page', () => {
  test('should reload plan detail when navigating to another plan id', async ({ page }) => {
    await page.route('**/api/data-types/', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ data_types: [], groups: [] }),
      })
    })

    await page.route('**/api/collect-plans/*/', async route => {
      const match = route.request().url().match(/\/collect-plans\/(\d+)\//)
      const id = Number(match?.[1])

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          data: {
            id,
            name: `采集计划 ${id}`,
            status: 'PENDING',
            status_display: '待执行',
            execution_mode: 'SEQUENTIAL',
            execution_mode_display: '顺序执行',
            jobs_count: 1,
            created_at: '2026-05-20 10:00:00',
            started_at: null,
            completed_at: null,
            jobs: [
              {
                id,
                data_type: 'tick',
                data_type_display: `任务 ${id}`,
                config: { symbols: [] },
                status: 'PENDING',
                status_display: '待执行',
                start_time: null,
                end_time: null,
                message: '',
              },
            ],
          },
        }),
      })
    })

    await page.goto('/admin/collector/collect-plans/1249')
    await expect(page.locator('.collect-plan-detail')).toContainText('采集计划 1249')

    await page.evaluate(() => {
      window.history.pushState({}, '', '/admin/collector/collect-plans/1250')
      window.dispatchEvent(new PopStateEvent('popstate'))
    })

    await expect(page.locator('.collect-plan-detail')).toContainText('采集计划 1250')
    await expect(page.locator('.collect-plan-detail')).not.toContainText('采集计划 1249')
  })

  test('should load plan detail without errors', async ({ page }) => {
    const errors: string[] = []
    const failedRequests: string[] = []
    
    page.on('pageerror', error => errors.push(error.message))
    page.on('console', msg => {
      if (msg.type() === 'error') {
        errors.push(msg.text())
      }
    })
    page.on('requestfailed', request => {
      failedRequests.push(`${request.method()} ${request.url()}`)
    })
    
    await page.goto('/collect-plans/1')
    await waitForPageLoad(page)
    await sleep(1000)
    
    expect(errors).toHaveLength(0)
    expect(failedRequests).toHaveLength(0)
  })

  test('should display plan detail container', async ({ page }) => {
    await page.goto('/collect-plans/1')
    await waitForPageLoad(page)
    
    const container = page.locator('.collect-plan-detail')
    await expect(container).toBeVisible()
  })
})
