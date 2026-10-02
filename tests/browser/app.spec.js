import { test, expect } from '@playwright/test';

const base = process.env.BASE_PATH || '';
function fixture(version = 0) {
  const generated = new Date(Date.now() + version * 60000).toISOString();
  return {
    generated_at: generated,
    source_health: [{ source: 'CTV News London', scope: 'local', status: 'healthy' }],
    stories: Array.from({ length: 36 }, (_, i) => ({
      id: `story-${i}`, title: `London report ${i} - CBC.CA`,
      summary: i === 0 ? 'London report 0 CBC' : `Local reporting and context for London report ${i}.`,
      source: 'CTV News London', scope: 'local', category: i % 2 ? 'Business' : 'Public Safety',
      published: new Date(Date.now() - i * 3600000).toISOString(),
      word_count: 650, url: 'https://example.com/report',
      image: i === 1 ? `${base}/social.png` : '',
      _data_file: `story-${i}.json`, cluster_representative: true,
      content_status: 'full', quality: { score: 90 }
    }))
  };
}
test.beforeEach(async ({ page }) => {
  const edition = fixture();
  await page.route('**/data/app-feed.json', route => route.fulfill({ json: edition }));
  await page.route('**/data/stories/*.json', route => {
    const id = route.request().url().split('/').pop().replace('.json', '');
    const meta = edition.stories.find(s => s.id === id);
    return route.fulfill({ json: { ...meta, content_blocks: Array.from({ length: 30 }, (_, i) => ({ type: 'paragraph', text: `Paragraph ${i}. This is reporting about London. It includes enough detail to test reading and returning to the same position without refreshing the page.` })) } });
  });
  await page.goto('./');
  await expect(page.locator('.news-card').first()).toBeVisible();
});
async function openNav(page, name) {
  const mobile = page.viewportSize().width <= 760;
  const labels = { Search: 'Search news', Sections: 'Browse sections and sources', Settings: 'Settings', Home: 'Forest City News home' };
  await (mobile ? page.getByRole('navigation', { name: 'Primary navigation' }).getByRole('link', { name, exact: true }) : page.getByRole('link', { name: labels[name], exact: true })).click();
}
async function noOverflow(page) {
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
}
test('all screens fit the viewport in both themes', async ({ page }) => {
  await noOverflow(page);
  for (const name of ['Sections', 'Search', 'Settings']) {
    await openNav(page, name);
    await expect(page.getByRole('heading', { name, exact: true })).toBeVisible();
    await noOverflow(page);
  }
  await page.getByRole('button', { name: 'Dark', exact: true }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await openNav(page, 'Home');
  await noOverflow(page);
});
test('article Back and tab return preserve position and search filters', async ({ page }) => {
  const card = page.locator('[data-story-id="story-20"] .news-card-link');
  await card.scrollIntoViewIfNeeded();
  const original = await page.evaluate(() => scrollY);
  await card.click();
  await expect(page.getByRole('heading', { name: 'London report 20', exact: true })).toBeVisible();
  await page.goBack();
  await expect.poll(() => page.evaluate(() => scrollY)).toBeGreaterThan(original - 4);
  await expect.poll(() => page.evaluate(() => scrollY)).toBeLessThan(original + 4);
  await openNav(page, 'Search');
  await page.getByRole('searchbox').fill('London');
  await page.getByRole('combobox', { name: 'Section', exact: true }).selectOption('Business');
  await expect(page.getByText('18 results', { exact: true })).toBeVisible();
  await page.locator('.archive-search-hit').last().scrollIntoViewIfNeeded();
  const searchY = await page.evaluate(() => scrollY);
  await openNav(page, 'Settings');
  await openNav(page, 'Search');
  await expect(page.getByRole('searchbox')).toHaveValue('London');
  await expect(page.getByRole('combobox', { name: 'Section', exact: true })).toHaveValue('Business');
  await expect.poll(() => page.evaluate(() => scrollY)).toBeGreaterThan(searchY - 4);
});
test('text-only feature cards and carousel controls are intentional and accessible', async ({ page }) => {
  const first = page.locator('[data-story-id="story-0"]');
  await expect(first.getByRole('heading')).toHaveText('London report 0');
  await expect(first.locator('.news-card-summary')).toHaveCount(0);
  await expect(first.locator('.news-card-media')).not.toBeVisible();
  const dot = page.getByRole('button', { name: 'Show top story 2 of 3' });
  const rect = await dot.boundingBox();
  expect(rect.width).toBeGreaterThanOrEqual(44); expect(rect.height).toBeGreaterThanOrEqual(44);
  await dot.click();
  await expect(page.locator('.editorial-carousel-slide').nth(0)).toHaveAttribute('inert', '');
  await expect(page.locator('.editorial-carousel-slide').nth(1)).not.toHaveAttribute('inert', '');
});
