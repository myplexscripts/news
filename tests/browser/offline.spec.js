import { test, expect } from '@playwright/test';
test.use({ serviceWorkers: 'allow' });
test('the app reopens offline with its local font, icons and previously opened article', async ({ page, context, browserName }) => {
  test.skip(browserName !== 'chromium', 'Playwright supports service worker offline tests on Chromium only. Verify iOS offline reopening on a real device.');
  await page.goto('./');
  await expect(page.locator('.news-card').first()).toBeVisible();
  await page.evaluate(async () => {
    await navigator.serviceWorker.ready;
    if (!navigator.serviceWorker.controller) await new Promise(resolve => navigator.serviceWorker.addEventListener('controllerchange', resolve, { once: true }));
  });
  const card = page.locator('.editorial-carousel-slide:not([inert]) .news-card-link');
  await card.click();
  await expect(page.locator('.editorial-story h1')).toBeVisible();
  const heading = await page.locator('.editorial-story h1').innerText();
  // Cache the article's document shell as well as its data on a normal reload.
  await page.reload();
  await expect(page.locator('.editorial-story h1')).toHaveText(heading);
  await context.setOffline(true);
  await page.reload();
  await expect(page.locator('.editorial-story h1')).toHaveText(heading);
  await expect(page.getByRole('status')).toContainText('offline');
  await expect.poll(() => page.evaluate(() => document.fonts.check('16px Inter'))).toBe(true);
});
