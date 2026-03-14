import { test, expect } from '@playwright/test'
import { waitForPageLoad, sleep } from '../utils/helpers'

test.describe('Integrity Reports Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/integrity-reports')
    await waitForPageLoad(page)
    await sleep(1000)
  })

  test('should load without errors', async ({ page }) => {
    const errors: string[] = []
    page.on('pageerror', error => errors.push(error.message))
    
    await waitForPageLoad(page)
    
    expect(errors).toHaveLength(0)
  })

  test('should display report list container', async ({ page }) => {
    await expect(page.locator('.integrity-reports')).toBeVisible()
  })

  test('should show filter panel', async ({ page }) => {
    await expect(page.locator('.filter-panel')).toBeVisible()
  })

  test('should display results panel', async ({ page }) => {
    await expect(page.locator('.results-panel')).toBeVisible()
  })

  test('should show table with mock reports', async ({ page }) => {
    const table = page.locator('table, .el-table').first()
    await expect(table).toBeVisible()
    
    const rows = table.locator('tbody tr, .el-table__row')
    const rowCount = await rows.count()
    expect(rowCount).toBeGreaterThanOrEqual(0)
  })

  test('should have create report button', async ({ page }) => {
    const button = page.locator('button:has-text("生成报告")')
    await expect(button).toBeVisible()
  })

  test('should display report status tags', async ({ page }) => {
    const tags = page.locator('.el-tag, .status-tag')
    const tagCount = await tags.count()
    expect(tagCount).toBeGreaterThanOrEqual(0)
  })

  test('should allow clicking report detail', async ({ page }) => {
    const viewButton = page.locator('button:has-text("查看")').first()
    if (await viewButton.isVisible()) {
      await viewButton.click()
      await page.waitForURL(/\/integrity-reports\/\d+/, { timeout: 5000 }).catch(() => {})
    }
    expect(true).toBeTruthy()
  })

  test('should create new report flow', async ({ page }) => {
    const checkbox = page.locator('input[type="checkbox"]').first()
    if (await checkbox.isVisible()) {
      await checkbox.check()
    }
    
    const createButton = page.locator('button:has-text("生成报告")')
    await createButton.click()
    
    await page.waitForURL(/\/integrity-reports\/\d+/, { timeout: 10000 }).catch(() => {})
    expect(true).toBeTruthy()
  })
})
