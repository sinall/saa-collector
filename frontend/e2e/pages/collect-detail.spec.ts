import { test, expect } from '@playwright/test'
import { waitForPageLoad, sleep } from '../utils/helpers'

test.describe('Collect Schedule Detail Page', () => {
  test('should load schedule detail without errors', async ({ page }) => {
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

    await page.goto('/collect-schedules/1')
    await waitForPageLoad(page)
    await sleep(1000)

    expect(errors).toHaveLength(0)
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

    const content = page.locator('.el-descriptions, .el-card')
    await expect(content.first()).toBeVisible()
  })

  test('should show schedule actions on detail page', async ({ page }) => {
    await page.route('**/api/data-types/', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          data_types: [
            { key: 'historical_quote', label: '历史行情' },
          ],
          groups: [],
        }),
      })
    })

    await page.route('**/api/collect-schedules/1/', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          data: {
            id: 1,
            name: '历史行情采集',
            data_type: 'historical_quote',
            data_type_display: '历史行情',
            symbols: [],
            params: { date_start: 'T-30d', date_end: 'T-1td' },
            cron_expression: '0 18 * * 1-5',
            status: 'ENABLED',
            last_triggered_at: null,
            next_trigger_at: '2026-05-26T10:00:00+08:00',
            created_at: '2026-05-25T10:00:00+08:00',
            updated_at: '2026-05-25T10:00:00+08:00',
          },
        }),
      })
    })

    await page.goto('/admin/collector/collect-schedules/1')
    await waitForPageLoad(page)

    await expect(page.getByRole('button', { name: '执行' })).toBeVisible()
    await expect(page.getByRole('button', { name: '编辑' })).toBeVisible()
    await expect(page.getByRole('button', { name: '删除' })).toBeVisible()
    await expect(page.locator('.header-actions .el-switch')).toBeVisible()
  })
  test('should reload schedule detail when navigating to another schedule id', async ({ page }) => {
    await page.route('**/api/data-types/', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ data_types: [], groups: [] }),
      })
    })

    await page.route('**/api/collect-schedules/*/', async route => {
      const match = route.request().url().match(/\/collect-schedules\/(\d+)\//)
      const id = Number(match?.[1])
      const schedules = {
        3: {
          id: 3,
          name: '估值数据采集',
          data_type: 'valuation',
          data_type_display: '估值数据',
          symbols: [],
          params: {},
          cron_expression: '5 0 7 5 *',
          status: 'ENABLED',
          last_triggered_at: null,
          next_trigger_at: '2026-05-07T00:05:00+08:00',
          created_at: '2026-05-25T10:00:00+08:00',
          updated_at: '2026-05-25T10:00:00+08:00',
        },
        9: {
          id: 9,
          name: '历史行情采集',
          data_type: 'historical_quote',
          data_type_display: '历史行情',
          symbols: [],
          params: { date_start: 'T-30d', date_end: 'T-1td' },
          cron_expression: '0 18 * * 1-5',
          status: 'ENABLED',
          last_triggered_at: null,
          next_trigger_at: '2026-05-26T18:00:00+08:00',
          created_at: '2026-05-25T10:00:00+08:00',
          updated_at: '2026-05-25T10:00:00+08:00',
        },
      } as const

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          data: schedules[id as keyof typeof schedules],
        }),
      })
    })

    await page.goto('/admin/collector/collect-schedules/3')
    await expect(page.locator('.collect-schedule-detail')).toContainText('估值数据采集')

    await page.evaluate(() => {
      window.history.pushState({}, '', '/admin/collector/collect-schedules/9')
      window.dispatchEvent(new PopStateEvent('popstate'))
    })

    await expect(page.locator('.collect-schedule-detail')).toContainText('历史行情采集')
    await expect(page.locator('.collect-schedule-detail')).not.toContainText('估值数据采集')
  })
})

test.describe('Collect Schedule Edit Page', () => {
  test('should reload schedule detail when navigating to another schedule edit id', async ({ page }) => {
    await page.route('**/api/data-types/', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          data_types: [
            { key: 'historical_quote', label: '历史行情' },
            { key: 'financial_statements', label: '财务报表' },
          ],
          groups: [],
        }),
      })
    })

    await page.route('**/api/collect-schedules/*/', async route => {
      const match = route.request().url().match(/\/collect-schedules\/(\d+)\//)
      const id = Number(match?.[1])

      const schedules = {
        8: {
          id: 8,
          name: '财务报表采集(5月)',
          data_type: 'financial_statements',
          symbols: [],
          params: { date_start: 'today', date_end: 'today' },
          cron_expression: '0 9 * * 1-5',
          status: 'ENABLED',
        },
        9: {
          id: 9,
          name: '历史行情采集',
          data_type: 'historical_quote',
          symbols: [],
          params: { date_start: 'today', date_end: 'today' },
          cron_expression: '0 18 * * 1-5',
          status: 'ENABLED',
        },
      } as const

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          data: schedules[id as keyof typeof schedules],
        }),
      })
    })

    await page.goto('/admin/collector/collect-schedules/8/edit')
    await expect(page.getByPlaceholder('请输入日程名称')).toHaveValue('财务报表采集(5月)')

    await page.evaluate(() => {
      window.history.pushState({}, '', '/admin/collector/collect-schedules/9/edit')
      window.dispatchEvent(new PopStateEvent('popstate'))
    })

    await expect(page.getByPlaceholder('请输入日程名称')).toHaveValue('历史行情采集')
  })

  test('should return to schedule detail after saving an existing schedule', async ({ page }) => {
    await page.route('**/api/data-types/', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          data_types: [
            { key: 'historical_quote', label: '历史行情' },
          ],
          groups: [],
        }),
      })
    })

    await page.route('**/api/collect-schedules/9/', async route => {
      const method = route.request().method()
      const responseBody = {
        success: true,
        data: {
          id: 9,
          name: '历史行情采集',
          data_type: 'historical_quote',
          data_type_display: '历史行情',
          symbols: [],
          params: { date_start: 'T-2', date_end: 'T-1td' },
          cron_expression: '0 18 * * 1-5',
          status: 'ENABLED',
          last_triggered_at: null,
          next_trigger_at: '2026-05-26T10:00:00+08:00',
          created_at: '2026-05-25T10:00:00+08:00',
          updated_at: '2026-05-25T10:00:00+08:00',
        },
      }

      if (method === 'PUT') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(responseBody),
        })
        return
      }

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(responseBody),
      })
    })

    await page.goto('/admin/collector/collect-schedules/9/edit')
    await waitForPageLoad(page)

    await page.getByPlaceholder('请输入日程名称').fill('历史行情采集')
    await page.getByRole('button', { name: '保存' }).click()

    await expect(page).toHaveURL(/\/collect-schedules\/9$/)
    await expect(page.locator('.collect-schedule-detail')).toBeVisible()
    await expect(page.getByRole('cell', { name: '历史行情采集' })).toBeVisible()
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
