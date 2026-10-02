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
test.beforeEach(async ({ page }, testInfo) => {
  if (testInfo.project.name.includes('standalone')) await page.addInitScript(() => Object.defineProperty(navigator, 'standalone', { configurable: true, get: () => true }));
  if (testInfo.title.includes('font downloads')) await page.route(/\.(woff2?|ttf|otf)(\?|$)/, route => route.abort());
  if (testInfo.title.startsWith('background refresh')) await page.clock.install();
  const edition = fixture();
  if (testInfo.title.startsWith('aggregated coverage')) {
    const sources = ['Global News London', 'CBC News London', 'CTV News London', 'London Police Service'];
    edition.stories.slice(0, 4).forEach((story, i) => Object.assign(story, {
      source: sources[i], cluster_id: 'same-event', cluster_sources: sources,
      cluster_source_count: 4, cluster_representative: i === 0
    }));
  }
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
  const cardContainer = page.locator('[data-story-id="story-20"]');
  const card = cardContainer.locator('.news-card-link');
  await cardContainer.scrollIntoViewIfNeeded();
  await expect.poll(async () => {
    await cardContainer.scrollIntoViewIfNeeded();
    return page.evaluate(() => scrollY);
  }).toBeGreaterThan(500);
  const original = await page.evaluate(() => scrollY);
  await card.click();
  await expect(page.getByRole('heading', { name: 'London report 20', exact: true })).toBeVisible();
  await page.goBack();
  await expect(page.locator('main.home-page')).toBeVisible();
  await expect.poll(() => page.evaluate(() => scrollY)).toBeGreaterThan(original - 4);
  await expect.poll(() => page.evaluate(() => scrollY)).toBeLessThan(original + 4);
  // A warmed article renders immediately. Returning quickly must still restore.
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

test('background refresh offers an edition without replacing the current list', async ({ page }) => {
  const fresh = fixture(1);
  fresh.stories[0].title = 'A newly published London report';
  await page.route('**/data/app-feed.json', route => route.fulfill({ json: fresh }));
  await page.clock.fastForward(300001);
  await expect(page.getByRole('button', { name: 'New updates available' })).toBeVisible();
  await expect(page.locator('[data-story-id="story-0"] h3')).toHaveText('London report 0');
  await page.getByRole('button', { name: 'New updates available' }).click();
  await expect(page.locator('[data-story-id="story-0"] h3')).toHaveText('A newly published London report');
});


test('mobile navigation stays visible with blocked font downloads', async ({ page }, testInfo) => {
  test.skip(page.viewportSize().width > 760, 'Mobile navigation is hidden on desktop.');
  const nav = page.getByRole('navigation', { name: 'Primary navigation' });
  async function checkIcons() {
    const bounds = await nav.boundingBox();
    expect(bounds.height).toBe(68);
    expect(bounds.y).toBeGreaterThan(0);
    expect(bounds.y + bounds.height).toBeLessThanOrEqual(page.viewportSize().height);
    const links = nav.locator('a.mobile-tab');
    await expect(links).toHaveCount(4);
    for (const link of await links.all()) {
      await expect(link).toBeVisible();
      const rect = await link.boundingBox();
      expect(rect.width).toBeGreaterThanOrEqual(44);
      expect(rect.height).toBeGreaterThanOrEqual(44);
      const icon = link.locator('svg.nav-icon');
      await expect(icon).toBeVisible();
      const pixels = await icon.evaluate(el => ({
        width: el.getBoundingClientRect().width, height: el.getBoundingClientRect().height,
        drawing: el.getBBox().width, colour: getComputedStyle(el).color,
        opacity: getComputedStyle(el).opacity
      }));
      expect(pixels.width).toBe(27); expect(pixels.height).toBe(27);
      expect(pixels.drawing).toBeGreaterThan(0); expect(pixels.opacity).toBe('1');
      expect(pixels.colour).not.toBe('rgba(0, 0, 0, 0)');
      const hit = await page.evaluate(({x,y}) => document.elementFromPoint(x,y)?.closest('a.mobile-tab')?.dataset.mobileTab, { x: rect.x+rect.width/2, y: rect.y+rect.height/2 });
      expect(hit).toBe(await link.getAttribute('data-mobile-tab'));
    }
  }
  await checkIcons();
  await page.screenshot({ path: testInfo.outputPath('mobile-navigation-light.png'), fullPage: false });
  await openNav(page, 'Settings');
  await page.getByRole('button', { name: 'Dark', exact: true }).click();
  await openNav(page, 'Home');
  await checkIcons();
  await page.screenshot({ path: testInfo.outputPath('mobile-navigation-dark.png'), fullPage: false });
  for (const name of ['Sections', 'Search', 'Settings']) {
    await openNav(page, name);
    await expect(page.getByRole('heading', { name, exact: true })).toBeVisible();
    await checkIcons();
  }
});


test('aggregated coverage occupies one top slot and alternate reports remain readable', async ({ page }) => {
  for (const id of ['story-1', 'story-2', 'story-3']) await expect(page.locator(`[data-story-id="${id}"]`)).toHaveCount(0);
  await expect(page.locator('[data-story-id="story-0"]')).toContainText('4 sources');
  await expect(page.locator('[data-story-id="story-4"]')).toHaveCount(1);
  await expect(page.locator('[data-story-id="story-5"]')).toHaveCount(1);
  await page.locator('[data-story-id="story-0"] .news-card-link').click();
  const coverage = page.getByRole('region', { name: 'Also covered by' });
  await expect(coverage.getByRole('link')).toHaveCount(3);
  await coverage.getByRole('link').filter({ hasText: 'CBC News London' }).click();
  await expect(page.getByRole('heading', { name: 'London report 1', exact: true })).toBeVisible();
  await page.goBack();
  await expect(page.getByRole('heading', { name: 'London report 0', exact: true })).toBeVisible();
});
