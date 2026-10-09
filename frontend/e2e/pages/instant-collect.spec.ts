import { test, expect } from '@playwright/test'
import { waitForPageLoad } from '../utils/helpers'

test.describe('Instant Collect Feature', () => {
  test.beforeEach(async ({ page }) => {
    await page.route(/.*\/admin\/collector\/api\/data-types\/?(\?.*)?$/, async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          data_types: [
            { key: 'quote', label: '最新行情', visibility: { collect_plan: true } },
            { key: 'historical_quote', label: '历史行情', visibility: { collect_plan: true } },
            { key: 'extras', label: '股票状态', visibility: { collect_plan: true } },
          ],
          groups: [],
        }),
      })
    })

    await page.route(/.*\/admin\/collector\/api\/collect-plans(?:\/.*)?(\?.*)?$/, async route => {
      if (route.request().method() === 'POST') {
        const body = route.request().postDataJSON()
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            success: true,
            data: {
              id: 999,
              name: body.name || '即时采集',
              status: 'PENDING',
              status_display: '待执行',
              source: 'MANUAL',
              source_display: '即时采集',
              execution_mode: 'PARALLEL',
              execution_mode_display: '并行',
              created_at: '2026-06-01 10:00:00',
              jobs_count: body.jobs?.length || 0,
              jobs: body.jobs || [],
            },
          }),
        })
        return
      }

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          count: 0,
          results: [],
        }),
      })
    })

    await page.goto('/admin/collector/collect-plans')
    await waitForPageLoad(page)
  })

  test('should create instant collect plan successfully', async ({ page }) => {
    await page.click('button:has-text("即时采集")')

    await expect(page.locator('.el-dialog')).toBeVisible()
    await expect(page.locator('.el-dialog .el-dialog__title')).toContainText('即时采集')
    await page.locator('.el-dialog .el-select__wrapper').click()
    await expect(page.locator('.el-select-dropdown')).toBeVisible()
    await page.locator('.el-select-dropdown').getByText('最新行情', { exact: true }).click()
    await expect(page.locator('.el-dialog')).toContainText('全市场')
    await expect(page.locator('.el-dialog')).toContainText('中证800')

    await page.click('.el-dialog button:has-text("创建并执行")')

    await expect(page.locator('.el-message--success')).toBeVisible()
    await expect(page.locator('.el-message--success')).toContainText('创建成功')

    await expect(page.locator('.el-dialog')).not.toBeVisible()
  })

  test('should show validation error when data type not selected', async ({ page }) => {
    await page.click('button:has-text("即时采集")')

    await page.click('.el-dialog button:has-text("创建并执行")')

    await expect(page.locator('.el-message--warning')).toBeVisible()
    await expect(page.locator('.el-message--warning')).toContainText('请选择数据类型')
  })

  test('should create instant collect plan with execution-day end date by default', async ({ page }) => {
    let createBody: any = null
    await page.route(/.*\/admin\/collector\/api\/collect-plans\/?$/, async route => {
      if (route.request().method() === 'POST') {
        createBody = route.request().postDataJSON()
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            success: true,
            data: {
              id: 999,
              name: createBody.name,
              status: 'PENDING',
              status_display: '待执行',
              source: 'MANUAL',
              source_display: '即时采集',
              execution_mode: 'PARALLEL',
              execution_mode_display: '并行',
              created_at: '2026-06-01 10:00:00',
              jobs_count: 1,
              jobs: [],
            },
          }),
        })
        return
      }

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          count: 0,
          results: [],
        }),
      })
    })

    await page.click('button:has-text("即时采集")')
    await expect(page.locator('.el-dialog')).toContainText('执行当天')

    await page.locator('.el-dialog .el-select__wrapper').click()
    await expect(page.locator('.el-select-dropdown')).toBeVisible()
    await page.locator('.el-select-dropdown').getByText('最新行情', { exact: true }).click()
    await page.click('.el-dialog button:has-text("创建并执行")')

    await expect.poll(() => createBody).not.toBeNull()
    expect(createBody.jobs[0].end_date_mode).toBe('EXECUTION_DAY')
    expect(createBody.jobs[0].end_date).toBeNull()
  })
})

test('index historical quotes expose and submit the holding window', async ({ page }) => {
  await page.route('**/api/**', async route => {
    const url = route.request().url()
    if (url.includes('data-types')) {
      await route.fulfill({ json: { data_types: [{ key: 'historical_quote', label: '历史行情', visibility: { collect_plan: true } }], groups: [] } })
    } else if (url.includes('collect-plans') && route.request().method() === 'POST') {
      await route.fulfill({ json: { success: true, data: { id: 999 } } })
    } else {
      await route.fulfill({ json: { count: 0, results: [], success: true, data: [] } })
    }
  })
  await page.goto('/admin/collector/collect-plans')
  await page.getByRole('button', { name: '即时采集' }).click()
  const dialog = page.locator('.el-dialog')
  await dialog.locator('.el-select__wrapper').first().click()
  await page.locator('.el-select-dropdown:visible').getByText('历史行情', { exact: true }).click()
  await dialog.getByText('中证800', { exact: true }).click()
  const windowInput = dialog.locator('.el-form-item', { hasText: '回看月数' }).getByRole('spinbutton')
  await expect(windowInput).toBeVisible()
  await windowInput.fill('3')
  const requestPromise = page.waitForRequest(request => request.method() === 'POST' && request.url().endsWith('/collect-plans/'))
  await dialog.getByRole('button', { name: '创建并执行' }).click()
  expect((await requestPromise).postDataJSON().jobs[0].index_lookback_months).toBe(3)
})
