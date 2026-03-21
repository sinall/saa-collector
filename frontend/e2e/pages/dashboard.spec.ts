import { test, expect } from '@playwright/test'
import { waitForPageLoad } from '../utils/helpers'

test.describe('Dashboard Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
  })

  test('should load dashboard without errors', async ({ page }) => {
    const errors: string[] = []
    page.on('pageerror', error => errors.push(error.message))
    
    await waitForPageLoad(page)
    
    expect(errors).toHaveLength(0)
  })

  test('should have correct page title', async ({ page }) => {
    await expect(page).toHaveTitle(/SAA Collector/)
  })

  test('should display main content', async ({ page }) => {
    await waitForPageLoad(page)
    const body = page.locator('body')
    await expect(body).toBeVisible()
  })

  test('should display dashboard content', async ({ page }) => {
    await waitForPageLoad(page)
    const app = page.locator('#app')
    await expect(app).toBeVisible()
  })

  test('should display all expected data types in stats cards', async ({ page }) => {
    await waitForPageLoad(page)
    await page.waitForSelector('.stats-card', { timeout: 10000 })
    
    const expectedDataTypes = [
      '交易日',
      '股票基本信息',
      '最新行情',
      '历史行情',
      '资产负债表',
      '利润表',
      '现金流量表',
      '分红数据',
      '主营业务',
      '股本变动',
      '板块估值',
      '行业估值',
    ]
    
    for (const typeName of expectedDataTypes) {
      const card = page.locator('.stat-card', { hasText: typeName })
      await expect(card, `Should display ${typeName} card`).toBeVisible()
    }
  })

  test('should display completeness progress bar for valuation_board', async ({ page }) => {
    await waitForPageLoad(page)
    await page.waitForSelector('.stats-card', { timeout: 10000 })
    
    const valuationCard = page.locator('.stat-card', { hasText: '板块估值' })
    await expect(valuationCard).toBeVisible()
    
    const completenessBar = valuationCard.locator('.stat-completeness')
    await expect(completenessBar, '板块估值 should have completeness progress bar').toBeVisible()
  })

  test('should have consistent card heights in stats row', async ({ page }) => {
    await waitForPageLoad(page)
    await page.waitForSelector('.stats-card', { timeout: 10000 })
    
    const cards = await page.locator('.stat-card').all()
    expect(cards.length, 'Should have at least 10 stat cards').toBeGreaterThanOrEqual(10)
    
    const heights: number[] = []
    for (const card of cards) {
      const box = await card.boundingBox()
      if (box) {
        heights.push(box.height)
      }
    }
    
    if (heights.length > 0) {
      const avgHeight = heights.reduce((a, b) => a + b, 0) / heights.length
      for (let i = 0; i < heights.length; i++) {
        expect(
          Math.abs(heights[i] - avgHeight),
          `Card ${i} height ${heights[i]} should be close to average ${avgHeight}`
        ).toBeLessThan(20)
      }
    }
  })
})
