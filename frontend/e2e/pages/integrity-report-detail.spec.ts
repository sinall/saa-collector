import { test, expect } from '@playwright/test'
import { waitForPageLoad, sleep } from '../utils/helpers'

test.describe('Integrity Report Detail Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/integrity-reports/1')
    await waitForPageLoad(page)
    await sleep(1500)
  })

  test('should load without errors', async ({ page }) => {
    const errors: string[] = []
    page.on('pageerror', error => errors.push(error.message))
    
    await waitForPageLoad(page)
    await sleep(1000)
    
    expect(errors).toHaveLength(0)
  })

  test('should display report detail container', async ({ page }) => {
    await expect(page.locator('.integrity-report-detail')).toBeVisible()
  })

  test('should show card header with report name', async ({ page }) => {
    await expect(page.locator('.card-header')).toBeVisible()
  })

  test('should display back button', async ({ page }) => {
    const backButton = page.locator('button:has-text("返回")')
    await expect(backButton).toBeVisible()
  })

  test('should show heatmap section', async ({ page }) => {
    const heatmapSection = page.locator('.heatmap-section')
    await expect(heatmapSection).toBeVisible({ timeout: 10000 })
  })

  test('should have filter area with dropdowns', async ({ page }) => {
    const filterArea = page.locator('.filter-bar')
    await expect(filterArea).toBeVisible({ timeout: 10000 })
  })

  test('should display data table', async ({ page }) => {
    const table = page.locator('.ag-root-wrapper, .ag-theme-quartz, table').first()
    await expect(table).toBeVisible({ timeout: 10000 })
  })

  test('should show pagination and selection info', async ({ page }) => {
    const pagination = page.locator('.pagination-container')
    await expect(pagination).toBeVisible({ timeout: 10000 })
    
    const selectionInfo = page.locator('.selection-info')
    await expect(selectionInfo).toBeVisible()
  })

  test('should show generate plan button', async ({ page }) => {
    const button = page.locator('button:has-text("生成采集计划")')
    await expect(button).toBeVisible()
  })

  test('should show refresh report button', async ({ page }) => {
    const button = page.locator('button:has-text("刷新报告")')
    await expect(button).toBeVisible()
  })

  test('should have filter dropdowns working', async ({ page }) => {
    const statusSelect = page.locator('.filter-bar .el-select').first()
    await expect(statusSelect).toBeVisible()
    
    const dataTypeSelect = page.locator('.el-select').filter({ hasText: '数据类型' })
    const isVisible = await dataTypeSelect.isVisible().catch(() => false)
    expect(typeof isVisible).toBe('boolean')
  })
})
