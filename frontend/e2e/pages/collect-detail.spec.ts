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
