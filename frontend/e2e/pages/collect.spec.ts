import { test, expect } from '@playwright/test'
import { waitForPageLoad } from '../utils/helpers'

test.describe('Collect Plans Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/collect-plans')
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

test.describe('Collect Schedules Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/collect-schedules')
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

test('collect-plans page should refresh after returning from a plan detail', async ({ page }) => {
  let plansCallCount = 0

  await page.route(/.*\/admin\/collector\/api\/data-types\/?(\?.*)?$/, async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        data_types: [
          { key: 'trade_days', label: '交易日', need_date: true },
        ],
        groups: [],
      }),
    })
  })

  await page.route(/.*\/admin\/collector\/api\/collect-plans(?:\/.*)?(\?.*)?$/, async route => {
    const url = route.request().url()
    if (url.includes('/api/collect-plans/1/')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          data: {
            id: 1,
            name: '旧计划',
            status: 'PENDING',
            status_display: '待执行',
            source: 'MANUAL',
            source_display: '即时采集',
            execution_mode: 'PARALLEL',
            execution_mode_display: '并行',
            created_at: '2026-06-01 10:00:00',
            jobs_count: 1,
            jobs: [
              {
                id: 11,
                data_type: 'trade_days',
                data_type_display: '交易日',
                symbols: [],
                params: {},
                status: 'SUCCESS',
                status_display: '成功',
              },
            ],
          },
        }),
      })
      return
    }

    if (route.request().method() === 'GET') {
      plansCallCount += 1
      const plans = plansCallCount === 1
        ? [
            {
              id: 1,
              name: '旧计划',
              status: 'PENDING',
              status_display: '待执行',
              source: 'MANUAL',
              source_display: '即时采集',
              execution_mode: 'PARALLEL',
              execution_mode_display: '并行',
              created_at: '2026-06-01 10:00:00',
              jobs_count: 1,
              jobs: [
                {
                  id: 11,
                  data_type: 'trade_days',
                  data_type_display: '交易日',
                  symbols: [],
                  params: {},
                  status: 'SUCCESS',
                  status_display: '成功',
                },
              ],
            },
          ]
        : [
            {
              id: 1,
              name: '旧计划',
              status: 'PENDING',
              status_display: '待执行',
              source: 'MANUAL',
              source_display: '即时采集',
              execution_mode: 'PARALLEL',
              execution_mode_display: '并行',
              created_at: '2026-06-01 10:00:00',
              jobs_count: 1,
              jobs: [
                {
                  id: 11,
                  data_type: 'trade_days',
                  data_type_display: '交易日',
                  symbols: [],
                  params: {},
                  status: 'SUCCESS',
                  status_display: '成功',
                },
              ],
            },
            {
              id: 2,
              name: '新计划',
              status: 'PENDING',
              status_display: '待执行',
              source: 'MANUAL',
              source_display: '即时采集',
              execution_mode: 'PARALLEL',
              execution_mode_display: '并行',
              created_at: '2026-06-01 11:00:00',
              jobs_count: 1,
              jobs: [
                {
                  id: 12,
                  data_type: 'trade_days',
                  data_type_display: '交易日',
                  symbols: [],
                  params: {},
                  status: 'SUCCESS',
                  status_display: '成功',
                },
              ],
            },
          ]

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          count: plans.length,
          results: plans,
        }),
      })
    }
  })

  await page.goto('/admin/collector/collect-plans')
  await waitForPageLoad(page)
  await expect(page.getByText('旧计划')).toBeVisible()
  await expect(page.getByText('新计划')).toHaveCount(0)

  await page.getByRole('button', { name: '查看' }).first().click()
  await expect(page).toHaveURL(/\/collect-plans\/1$/)
  await expect(page.locator('.collect-plan-detail')).toContainText('旧计划')

  await page.getByRole('button', { name: '返回' }).click()
  await expect(page).toHaveURL(/\/collect-plans$/)
  await expect(page.getByText('新计划')).toBeVisible()
  await expect(page.locator('.el-table__body tbody tr')).toHaveCount(2)
})
