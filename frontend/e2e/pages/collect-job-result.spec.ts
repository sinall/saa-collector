import { test, expect } from '@playwright/test'

test('job details load structured conflicts on demand', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('token', 'isolated-test'))
  let detailRequests = 0
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    let payload: unknown = { success: true, data: [] }
    if (path.endsWith('/data-types/')) payload = { data_types: [], groups: [] }
    if (path.endsWith('/collect-plans/7/')) payload = { success: true, data: { id: 7, name: '测试计划', status: 'FAILED', jobs: [
      { id: 7, data_type_display: '财报', status: 'FAILED', status_display: '失败', message: '完成99只，失败1只' },
    ] } }
    if (path.endsWith('/collect/jobs/7/')) {
      detailRequests++
      payload = { success: true, data: { id: 7, message: '完成99只，失败1只', result: {
        schema_version: 1, truncated: true, issues: [{ code: 'STATEMENT_VERSION_CONFLICT',
          symbol: '600036', report_date: '2012-12-31', disclosure_date: '2014-03-29',
          occurrences: 2, differences: { ass_invest_income: { candidates: [
            { value: '31000000.00', report_type: '1' }, { value: '64000000.00', report_type: '4' },
          ] } } }],
      } } }
    }
    await route.fulfill({ json: payload })
  })
  await page.goto('/admin/collector/collect-plans/7')
  await expect(page.getByText('完成99只，失败1只')).toBeVisible()
  expect(detailRequests).toBe(0)
  await page.getByRole('button', { name: '查看执行结果' }).click()
  await expect(page.getByText('600036')).toBeVisible()
  await expect(page.getByText('部分问题明细未保存')).toBeVisible()
  await page.getByText('600036').click()
  await expect(page.getByText('31000000.00', { exact: false })).toBeVisible()
  expect(detailRequests).toBe(1)
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).toBeHidden()
  await page.route('**/api/collect/jobs/7/', route => route.fulfill({
    json: { success: true, data: { id: 7, message: '旧任务消息', result: {} } },
  }))
  await page.getByRole('button', { name: '查看执行结果' }).click()
  await expect(page.getByText('旧任务消息')).toBeVisible()
  await expect(page.getByText('暂无问题明细')).toBeVisible()
  await expect(page.getByText('600036')).toHaveCount(0)
})
