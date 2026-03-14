import { Page, Locator } from '@playwright/test'

export async function waitForPageLoad(page: Page) {
  await page.waitForLoadState('networkidle')
}

export async function checkNoConsoleErrors(page: Page): Promise<string[]> {
  const errors: string[] = []
  page.on('console', msg => {
    if (msg.type() === 'error') {
      errors.push(msg.text())
    }
  })
  return errors
}

export async function checkNoPageErrors(page: Page): Promise<string[]> {
  const errors: string[] = []
  page.on('pageerror', error => {
    errors.push(error.message)
  })
  return errors
}

export async function takeScreenshot(page: Page, name: string) {
  await page.screenshot({ 
    path: `test-results/screenshots/${name}.png`,
    fullPage: true 
  })
}

export async function waitForElement(page: Page, selector: string, timeout = 10000) {
  await page.waitForSelector(selector, { timeout, state: 'visible' })
}

export async function isElementVisible(locator: Locator): Promise<boolean> {
  try {
    return await locator.isVisible()
  } catch {
    return false
  }
}

export async function getElementCount(locator: Locator): Promise<number> {
  return await locator.count()
}

export async function sleep(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms))
}
