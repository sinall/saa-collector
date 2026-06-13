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

test('collect-plan edit should submit job date config when saving', async ({ page }) => {
  let patchBody: any = null

  await page.route(/.*\/admin\/collector\/api\/data-types\/?(\?.*)?$/, async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        data_types: [
          {
            key: 'quote',
            label: '最新行情',
            visibility: { collect_plan: true },
          },
        ],
        groups: [],
      }),
    })
  })

  await page.route(/.*\/admin\/collector\/api\/collect-plans\/1308\/?$/, async route => {
    if (route.request().method() === 'PATCH') {
      patchBody = route.request().postDataJSON()
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          data: {
            id: 1308,
            name: patchBody.name,
            status: 'PENDING',
            status_display: '待执行',
            source: 'MANUAL',
            source_display: '即时采集',
            execution_mode: patchBody.execution_mode,
            execution_mode_display: '并行',
            created_at: '2026-06-01 10:00:00',
            jobs_count: 1,
            jobs: [
              {
                id: 901,
                data_type: 'quote',
                data_type_display: '最新行情',
              config: {
                symbols: ['000001'],
                end_date_mode: 'FIXED',
                params: {
                  start_date: patchBody.jobs[0].start_date,
                  end_date: patchBody.jobs[0].end_date,
                },
                },
                status: 'PENDING',
                status_display: '待执行',
              },
            ],
          },
        }),
      })
      return
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: {
          id: 1308,
          name: '计划 1308',
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
              id: 901,
              data_type: 'quote',
              data_type_display: '最新行情',
              config: {
                symbols: ['000001'],
                params: {
                  start_date: '2024-01-01',
                  end_date: '2024-12-31',
                },
              },
              status: 'PENDING',
              status_display: '待执行',
            },
          ],
        },
      }),
    })
  })

  await page.goto('/admin/collector/collect-plans/1308/edit')
  await waitForPageLoad(page)
  await page.getByRole('button', { name: '保存' }).click()

  await expect.poll(() => patchBody).not.toBeNull()
  expect(patchBody.jobs).toEqual([
    {
      id: 901,
      data_type: 'quote',
      data_frequency: 'daily',
      skip_existing: false,
      stock_scope: 'ALL',
      stock_list_code: null,
      end_date_mode: 'FIXED',
      symbols: ['000001'],
      start_date: '2024-01-01',
      end_date: '2024-12-31',
    },
  ])
})

test('collect-plan edit should preserve index stock scope when saving', async ({ page }) => {
  let patchBody: any = null

  await page.route(/.*\/admin\/collector\/api\/data-types\/?(\?.*)?$/, async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        data_types: [
          {
            key: 'quote',
            label: '最新行情',
            visibility: { collect_plan: true },
          },
        ],
        groups: [],
      }),
    })
  })

  await page.route(/.*\/admin\/collector\/api\/collect-plans\/1308\/?$/, async route => {
    if (route.request().method() === 'PATCH') {
      patchBody = route.request().postDataJSON()
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          data: {
            id: 1308,
            name: patchBody.name,
            status: 'PENDING',
            status_display: '待执行',
            source: 'MANUAL',
            source_display: '即时采集',
            execution_mode: patchBody.execution_mode,
            execution_mode_display: '并行',
            created_at: '2026-06-01 10:00:00',
            jobs_count: 1,
            jobs: [
              {
                id: 901,
                data_type: 'quote',
                data_type_display: '最新行情',
                config: {
                  symbols: [],
                  stock_scope: patchBody.jobs[0].stock_scope,
                  stock_list_code: patchBody.jobs[0].stock_list_code,
                  end_date_mode: patchBody.jobs[0].end_date_mode,
                  params: {
                    start_date: patchBody.jobs[0].start_date,
                    end_date: patchBody.jobs[0].end_date,
                  },
                },
                status: 'PENDING',
                status_display: '待执行',
              },
            ],
          },
        }),
      })
      return
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: {
          id: 1308,
          name: '计划 1308',
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
              id: 901,
              data_type: 'quote',
              data_type_display: '最新行情',
              config: {
                symbols: [],
                stock_scope: 'INDEX',
                stock_list_code: '000906',
                end_date_mode: 'FIXED',
                params: {
                  start_date: '2024-01-01',
                  end_date: '2024-12-31',
                },
              },
              status: 'PENDING',
              status_display: '待执行',
            },
          ],
        },
      }),
    })
  })

  await page.goto('/admin/collector/collect-plans/1308/edit')
  await waitForPageLoad(page)

  await expect(page.getByRole('radio', { name: '中证800' })).toBeChecked()
  await expect(
    page.locator('.job-item .el-form-item').filter({ hasText: '指数代码' }).locator('.el-select__selection')
  ).toContainText('中证800 (000906)')

  await page.getByRole('button', { name: '保存' }).click()

  await expect.poll(() => patchBody).not.toBeNull()
  expect(patchBody.jobs).toEqual([
    {
      id: 901,
      data_type: 'quote',
      data_frequency: 'daily',
      skip_existing: false,
      end_date_mode: 'FIXED',
      stock_scope: 'INDEX',
      stock_list_code: '000906',
      symbols: [],
      start_date: '2024-01-01',
      end_date: '2024-12-31',
    },
  ])
})

test('collect-plan edit should save execution-day end date mode', async ({ page }) => {
  let patchBody: any = null

  await page.route(/.*\/admin\/collector\/api\/data-types\/?(\?.*)?$/, async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        data_types: [
          {
            key: 'quote',
            label: '最新行情',
            visibility: { collect_plan: true },
          },
        ],
        groups: [],
      }),
    })
  })

  await page.route(/.*\/admin\/collector\/api\/collect-plans\/1308\/?$/, async route => {
    if (route.request().method() === 'PATCH') {
      patchBody = route.request().postDataJSON()
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          data: {
            id: 1308,
            name: patchBody.name,
            status: 'PENDING',
            status_display: '待执行',
            source: 'MANUAL',
            source_display: '即时采集',
            execution_mode: patchBody.execution_mode,
            execution_mode_display: '并行',
            created_at: '2026-06-01 10:00:00',
            jobs_count: 1,
            jobs: [
              {
                id: 901,
                data_type: 'quote',
                data_type_display: '最新行情',
                config: {
                  symbols: ['000001'],
                  params: {
                    start_date: patchBody.jobs[0].start_date,
                    end_date: null,
                    end_date_mode: patchBody.jobs[0].end_date_mode,
                  },
                },
                status: 'PENDING',
                status_display: '待执行',
              },
            ],
          },
        }),
      })
      return
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: {
          id: 1308,
          name: '计划 1308',
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
              id: 901,
              data_type: 'quote',
              data_type_display: '最新行情',
              config: {
                symbols: ['000001'],
                params: {
                  start_date: '2024-01-01',
                  end_date: null,
                  end_date_mode: 'EXECUTION_DAY',
                },
              },
              status: 'PENDING',
              status_display: '待执行',
            },
          ],
        },
      }),
    })
  })

  await page.goto('/admin/collector/collect-plans/1308/edit')
  await waitForPageLoad(page)
  await page.getByRole('button', { name: '保存' }).click()

  await expect.poll(() => patchBody).not.toBeNull()
  expect(patchBody.jobs).toEqual([
    {
      id: 901,
      data_type: 'quote',
      stock_scope: 'ALL',
      stock_list_code: null,
      end_date_mode: 'EXECUTION_DAY',
      symbols: ['000001'],
      start_date: '2024-01-01',
      end_date: null,
      data_frequency: 'daily',
      skip_existing: false,
    },
  ])
})

test('collect-plan detail should refresh after saving edited job dates', async ({ page }) => {
  let detailGetCount = 0
  let savedDates = {
    start_date: '2024-01-01',
    end_date: '2024-12-31',
  }

  const planResponse = (dates = savedDates) => ({
    success: true,
    data: {
      id: 1308,
      name: '计划 1308',
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
          id: 901,
          data_type: 'quote',
          data_type_display: '最新行情',
          config: {
            symbols: ['000001'],
            params: dates,
          },
          status: 'PENDING',
          status_display: '待执行',
        },
      ],
    },
  })

  await page.route(/.*\/admin\/collector\/api\/data-types\/?(\?.*)?$/, async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        data_types: [
          {
            key: 'quote',
            label: '最新行情',
            visibility: { collect_plan: true },
          },
        ],
        groups: [],
      }),
    })
  })

  await page.route(/.*\/admin\/collector\/api\/collect-plans\/1308\/?$/, async route => {
    if (route.request().method() === 'PATCH') {
      const body = route.request().postDataJSON()
      savedDates = {
        start_date: body.jobs[0].start_date,
        end_date: body.jobs[0].end_date,
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(planResponse()),
      })
      return
    }

    detailGetCount += 1
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(planResponse()),
    })
  })

  await page.goto('/admin/collector/collect-plans/1308')
  await waitForPageLoad(page)
  await expect(page.locator('.collect-plan-detail')).toContainText('2024-01-01')
  await expect(page.locator('.collect-plan-detail')).toContainText('2024-12-31')

  await page.getByRole('button', { name: '编辑' }).click()
  await expect(page).toHaveURL(/\/collect-plans\/1308\/edit$/)

  const dateInputs = page.locator('.collect-plan-edit .el-date-editor input')
  await dateInputs.nth(0).fill('2025-01-01')
  await dateInputs.nth(1).fill('2025-12-31')
  await page.getByRole('button', { name: '保存' }).click()

  await expect(page).toHaveURL(/\/collect-plans\/1308$/)
  await expect(page.locator('.collect-plan-detail')).toContainText('2025-01-01')
  await expect(page.locator('.collect-plan-detail')).toContainText('2025-12-31')
  expect(detailGetCount).toBeGreaterThanOrEqual(3)
})
