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
