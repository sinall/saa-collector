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
