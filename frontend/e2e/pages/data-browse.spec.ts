import { test, expect } from '@playwright/test'
import { waitForPageLoad } from '../utils/helpers'

test.describe('Data Browse Stock Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/data-browse/stock')
    await waitForPageLoad(page)
  })

  test('should load without errors', async ({ page }) => {
    const errors: string[] = []
    page.on('pageerror', error => errors.push(error.message))
    
    await waitForPageLoad(page)
    
    expect(errors).toHaveLength(0)
  })

  test('should display main content', async ({ page }) => {
    const body = page.locator('body')
    await expect(body).toBeVisible()
  })
})

test.describe('Data Browse Type Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/data-browse/type')
    await waitForPageLoad(page)
  })

  test('should load without errors', async ({ page }) => {
    const errors: string[] = []
    page.on('pageerror', error => errors.push(error.message))
    
    await waitForPageLoad(page)
    
    expect(errors).toHaveLength(0)
  })

  test('should display main content', async ({ page }) => {
    const body = page.locator('body')
    await expect(body).toBeVisible()
  })
})

test('data browse index quotes should query saa_index_quotes table', async ({ page }) => {
  const indexQuoteRequests: string[] = []

  await page.route(/.*\/admin\/collector\/api\/data-types\/?(\?.*)?$/, async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        data_types: [
          {
            key: 'index_quotes',
            label: '指数行情',
            table: 'saa_index_quotes',
            group: 'market',
            visibility: { data_check: true },
            order: 1,
          },
        ],
        groups: [
          { key: 'market', label: '市场数据', order: 1 },
        ],
      }),
    })
  })

  await page.route(/.*\/admin\/collector\/api\/display-field-config\/?(\?.*)?$/, async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: {
          groups: [],
          configs: {},
        },
      }),
    })
  })

  await page.route(/.*\/admin\/collector\/api\/type-browse-data\/saa_index_quotes\/?(\?.*)?$/, async route => {
    indexQuoteRequests.push(route.request().url())

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: {
          results: [
            {
              code: '000906',
              name: '中证800',
              date: '2026-06-01',
              close_price: 5431.52,
            },
          ],
          total: 1,
        },
      }),
    })
  })

  await page.goto('/admin/collector/data-browse/index_quotes')
  await waitForPageLoad(page)

  const dateInputs = page.locator('.data-browse-type .el-date-editor input')
  await dateInputs.nth(0).fill('2026-06-01')
  await dateInputs.nth(1).fill('2026-06-01')
  await page.getByRole('button', { name: '查询' }).click()

  await expect.poll(() => indexQuoteRequests.length).toBeGreaterThanOrEqual(2)
  const queryUrl = new URL(indexQuoteRequests[indexQuoteRequests.length - 1] ?? '')
  expect(queryUrl.searchParams.get('start_date')).toBe('2026-06-01')
  expect(queryUrl.searchParams.get('end_date')).toBe('2026-06-01')
})
