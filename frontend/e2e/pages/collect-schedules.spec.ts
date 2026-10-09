import { test, expect } from '@playwright/test';

test('collect-schedules page should explain cron expressions', async ({ page }) => {
  await page.route('**/api/data-types/', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        data_types: [
          { key: 'valuation', label: '估值数据' },
        ],
        groups: [],
      }),
    })
  })

  await page.route('**/api/collect-schedules/', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: [
          {
            id: 3,
            name: '估值数据采集',
            data_type: 'valuation',
            symbols: [],
            params: {},
            cron_expression: '5 0 7 5 *',
            status: 'ENABLED',
            next_trigger_at: '2026-05-07T00:05:00+08:00',
          },
        ],
      }),
    })
  })

  await page.goto('/admin/collector/collect-schedules')

  await expect(page.getByRole('columnheader', { name: '说明' })).toBeVisible()
  await expect(page.getByText('5 0 7 5 *')).toBeVisible()
  await expect(page.getByText('每年 5月7日 00:05', { exact: true })).toBeVisible()
})

test('collect-schedules page should display schedules from API', async ({ page }) => {
  await page.route('**/api/data-types/', route => route.fulfill({ json: { data_types: [{ key: 'historical_quote', label: '历史行情' }], groups: [] } }))
  await page.route('**/api/collect-schedules/', route => route.fulfill({ json: { success: true, data: [{
    id: 1, name: 'Tick', data_type: 'historical_quote', symbols: [], params: {},
    cron_expression: '0 0 1 * *', status: 'ENABLED',
  }] } }))
  await page.goto('/admin/collector/collect-schedules')
  await expect(page.locator('.el-table__body').getByText('Tick', { exact: true })).toBeVisible()
})

test('collect-schedules page should refresh after creating a schedule', async ({ page }) => {
  let schedulesCallCount = 0

  await page.route('**/api/data-types/', async route => {
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

  await page.route('**/api/collect-schedules/', async route => {
    if (route.request().method() === 'GET') {
      schedulesCallCount += 1
      const schedules = schedulesCallCount === 1
        ? [
            {
              id: 1,
              name: '旧日程',
              data_type: 'trade_days',
              symbols: [],
              params: {},
              cron_expression: '0 9 * * 1-5',
              status: 'ENABLED',
              next_trigger_at: '2026-06-01T09:00:00+08:00',
            },
          ]
        : [
            {
              id: 1,
              name: '旧日程',
              data_type: 'trade_days',
              symbols: [],
              params: {},
              cron_expression: '0 9 * * 1-5',
              status: 'ENABLED',
              next_trigger_at: '2026-06-01T09:00:00+08:00',
            },
            {
              id: 2,
              name: '新建日程',
              data_type: 'trade_days',
              symbols: [],
              params: { start_date: 'today', end_date: 'today' },
              cron_expression: '0 10 * * 1',
              status: 'ENABLED',
              next_trigger_at: '2026-06-08T10:00:00+08:00',
            },
          ]

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          data: schedules,
        }),
      })
      return
    }

    if (route.request().method() === 'POST') {
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          data: {
            id: 2,
            name: '新建日程',
            data_type: 'trade_days',
            symbols: [],
            params: { start_date: 'today', end_date: 'today' },
            cron_expression: '0 10 * * 1',
            status: 'ENABLED',
            next_trigger_at: '2026-06-08T10:00:00+08:00',
          },
        }),
      })
    }
  })

  await page.goto('/admin/collector/collect-schedules')
  await expect(page.getByText('旧日程')).toBeVisible()
  await expect(page.getByText('新建日程')).toHaveCount(0)

  await page.getByRole('button', { name: '新建' }).click()
  await expect(page).toHaveURL(/\/collect-schedules\/new$/)

  await page.getByLabel('日程名称').fill('新建日程')
  await page.getByText('请选择数据类型').click()
  await page.locator('.el-select-dropdown__item').filter({ hasText: '交易日' }).click()
  await page.getByLabel('Cron表达式').fill('0 10 * * 1')
  await page.getByRole('button', { name: '创建' }).click()

  await expect(page).toHaveURL(/\/collect-schedules$/)
  await expect(page.getByText('新建日程')).toBeVisible()
  await expect(page.locator('.el-table__body tbody tr')).toHaveCount(2)
})

test('editing a holding-price schedule preserves index scope and window', async ({ page }) => {
  await page.route('**/api/**', async route => {
    if (route.request().url().includes('data-types')) {
      await route.fulfill({ json: { data_types: [{ key: 'price_adjust_factor', label: '复权因子', need_date: true }], groups: [] } })
    } else if (route.request().url().includes('collect-schedules/77/')) {
      await route.fulfill({ json: { success: true, data: { id: 77, name: '持有期复权', data_type: 'price_adjust_factor', symbols: [], cron_expression: '0 0 1 * *', status: 'ENABLED', params: { start_date: 'T-2', end_date: 'T', stock_scope: 'INDEX', stock_list_code: '000906', index_lookback_months: 3, skip_existing: true, api_cache_enabled: false } } } })
    } else {
      await route.fulfill({ json: { success: true, data: [] } })
    }
  })
  await page.goto('/admin/collector/collect-schedules/77/edit')
  const windowInput = page.locator('.el-form-item', { hasText: '回看月数' }).getByRole('spinbutton')
  await expect(windowInput).toHaveValue('3')
  const pending = page.waitForRequest(request => request.method() === 'PUT' && request.url().includes('collect-schedules/77/'))
  await page.getByRole('button', { name: '保存', exact: true }).click()
  const payload = (await pending).postDataJSON()
  expect(payload.params.stock_scope).toBe('INDEX')
  expect(payload.params.index_lookback_months).toBe(3)
  expect(payload.params.api_cache_enabled).toBe(false)
})

test('editing a nondated schedule preserves cache and skip options', async ({ page }) => {
  await page.route('**/api/**', async route => {
    if (route.request().url().includes('data-types')) {
      await route.fulfill({ json: { data_types: [{ key: 'stock_info', label: '股票基本信息', need_date: false }], groups: [] } })
    } else if (route.request().url().includes('collect-schedules/78/')) {
      await route.fulfill({ json: { success: true, data: { id: 78, name: '股票', data_type: 'stock_info', symbols: [], cron_expression: '0 0 1 * *', status: 'ENABLED', params: { skip_existing: true, api_cache_enabled: false } } } })
    } else {
      await route.fulfill({ json: { success: true, data: [] } })
    }
  })
  await page.goto('/admin/collector/collect-schedules/78/edit')
  await expect(page.getByPlaceholder('请输入日程名称')).toHaveValue('股票')
  const pending = page.waitForRequest(request => request.method() === 'PUT' && request.url().includes('collect-schedules/78/'))
  await page.getByRole('button', { name: '保存', exact: true }).click()
  const params = (await pending).postDataJSON().params
  expect(params.api_cache_enabled).toBe(false)
  expect(params.skip_existing).toBe(true)
})

test('switching an index price schedule to financial data keeps index scope', async ({ page }) => {
  await page.route('**/api/**', async route => {
    if (route.request().url().includes('data-types')) {
      await route.fulfill({ json: { data_types: [
        { key: 'price_adjust_factor', label: '复权因子', need_date: true },
        { key: 'balance_sheet', label: '资产负债表', need_date: true },
      ], groups: [] } })
    } else if (route.request().url().includes('collect-schedules/79/')) {
      await route.fulfill({ json: { success: true, data: { id: 79, name: '指数日程', data_type: 'price_adjust_factor', symbols: [], cron_expression: '0 0 1 * *', status: 'ENABLED', params: { stock_scope: 'INDEX', stock_list_code: '000906', index_lookback_months: 3 } } } })
    } else {
      await route.fulfill({ json: { success: true, data: [] } })
    }
  })
  await page.goto('/admin/collector/collect-schedules/79/edit')
  await expect(page.getByPlaceholder('请输入日程名称')).toHaveValue('指数日程')
  await page.locator('.el-form-item', { hasText: '数据类型' }).locator('.el-select__wrapper').click()
  await page.locator('.el-select-dropdown:visible').getByText('资产负债表', { exact: true }).click()
  const pending = page.waitForRequest(request => request.method() === 'PUT' && request.url().includes('collect-schedules/79/'))
  await page.getByRole('button', { name: '保存', exact: true }).click()
  const params = (await pending).postDataJSON().params
  expect(params.stock_scope).toBe('INDEX')
  expect(params.stock_list_code).toBe('000906')
  expect(params.index_lookback_months).toBe(0)
})
