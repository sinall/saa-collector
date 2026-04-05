import { test, expect } from '@playwright/test'
import { waitForPageLoad } from '../utils/helpers'

test.describe('Instant Collect Feature', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/collect-plans')
    await waitForPageLoad(page)
  })

  test('should create instant collect plan successfully', async ({ page }) => {
    await page.click('button:has-text("即时采集")')

    await expect(page.locator('.el-dialog')).toBeVisible()
    await expect(page.locator('.el-dialog .el-dialog__title')).toContainText('即时采集')

    await page.click('.el-dialog .el-select')
    await page.click('.el-select-dropdown__item:has-text("最新行情")')

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
})
