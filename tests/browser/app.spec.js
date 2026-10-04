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
      image: i === 1 ? `${base}/images/social.png` : '',
      _data_file: `story-${i}.json`, cluster_representative: true,
      content_status: 'full', quality: { score: 90 }
    }))
  };
}
test.beforeEach(async ({ page }, testInfo) => {
  if (testInfo.project.name.includes('standalone')) await page.addInitScript(() => Object.defineProperty(navigator, 'standalone', { configurable: true, get: () => true }));
  if (testInfo.title.includes('font downloads')) await page.route(/\.(woff2?|ttf|otf)(\?|$)/, route => route.abort());
  if (testInfo.title.startsWith('background refresh')) await page.clock.install();
  if (testInfo.title.startsWith('removed bookmarks')) await page.addInitScript(() => {
    const request = indexedDB.open('london-news-user-state', 30);
    request.onupgradeneeded = () => {
      const db = request.result;
      for (const [name, key, index] of [['preferences','key','updatedAt'],['readStories','id','readAt'],['savedStories','id','savedAt'],['hiddenSources','name','hiddenAt']]) {
        const store = db.createObjectStore(name, { keyPath: key }); store.createIndex(index, index);
      }
    };
    request.onsuccess = () => {
      const db = request.result; const tx = db.transaction(['preferences','readStories','savedStories','hiddenSources'], 'readwrite');
      tx.objectStore('preferences').put({key:'theme',value:'dark',updatedAt:1});
      tx.objectStore('readStories').put({id:'story-10',readAt:1});
      tx.objectStore('savedStories').put({id:'story-12',savedAt:1});
      tx.objectStore('hiddenSources').put({name:'Other publisher',hiddenAt:1});
      tx.oncomplete = () => db.close();
    };
  });
  const edition = fixture();
  if (testInfo.title.startsWith('responsive images')) Object.assign(edition.stories[0], {
    image: `${base}/images/social.png`,
    editorial_image: `${base}/images/social.png?hero-2400`, editorial_image_source: `${base}/images/social.png`,
    editorial_image_width: 2400, editorial_image_height: 1350,
    editorial_image_variants: [{url:`${base}/images/social.png?hero-640`,width:640,height:360},{url:`${base}/images/social.png?hero-1600`,width:1600,height:900},{url:`${base}/images/social.png?hero-2400`,width:2400,height:1350}],
    card_image_small: `${base}/images/social.png?card-320`, card_image: `${base}/images/social.png?card-1200`,
    card_image_variants: [{url:`${base}/images/social.png?card-320`,width:320,height:180},{url:`${base}/images/social.png?card-640`,width:640,height:360},{url:`${base}/images/social.png?card-1200`,width:1200,height:675}]
  });
  if (testInfo.title.startsWith('related recommendations')) edition.stories.slice(-4).forEach(story => { story.scope = 'canada'; });
  if (testInfo.title.startsWith('top story card content anchors')) {
    edition.stories[0].title = 'A much longer top story headline that wraps across several lines without changing where the story content begins or where the timestamp sits';
    edition.stories[1].title = 'Short top story';
  }
  if (testInfo.title.startsWith('aggregated coverage')) {
    const sources = ['Global News London', 'CBC News London', 'CTV News London', 'London Police Service'];
    edition.stories.slice(0, 4).forEach((story, i) => Object.assign(story, {
      source: sources[i], cluster_id: 'same-event', cluster_sources: sources,
      cluster_source_count: 4, cluster_representative: i === 0
    }));
  }
  await page.route('**/images/tracking.png', route => route.fulfill({contentType:'image/png',body:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aL1kAAAAASUVORK5CYII=','base64')}));
  await page.route('**/data/app-feed.json', route => route.fulfill({ json: edition }));
  await page.route('**/data/stories/*.json', route => {
    const id = route.request().url().split('/').pop().replace('.json', '');
    const meta = edition.stories.find(s => s.id === id);
    const tracking = testInfo.title.startsWith('responsive images') ? [{type:'image',url:`${base}/images/tracking.png`,alt:'Tracking image'}] : [];
    return route.fulfill({ json: { ...meta, content_blocks: [...tracking, ...Array.from({ length: 30 }, (_, i) => ({ type: 'paragraph', text: `Paragraph ${i}. This is reporting about London. It includes enough detail to test reading and returning to the same position without refreshing the page.` }))] } });
  });
  await page.goto('./');
  await expect(page.locator('.news-card').first()).toBeVisible();
});
async function openNav(page, name) {
  const mobile = page.viewportSize().width <= 760;
  const labels = { Search: 'Search news', Sections: 'Browse sections and sources', Settings: 'Settings', Home: 'Forest City News home' };
  if (mobile) {
    await page.getByRole('navigation', { name: 'Primary navigation' }).getByRole('link', { name, exact: true }).click();
    return;
  }
  // The restored desktop header is intentionally non-sticky. Trigger the link
  // without Playwright first scrolling it into view, so screen-position memory
  // is tested independently of test-runner auto-scroll.
  await page.getByRole('link', { name: labels[name], exact: true }).evaluate((link) => link.click());
}
async function noOverflow(page) {
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
}
test('self-hosted variable Inter and the shared type scale are active', async ({ page }) => {
  const fontState = await page.evaluate(async () => {
    await document.fonts.load('650 1rem Inter');
    await document.fonts.load('italic 400 1rem Inter');
    await document.fonts.ready;
    const resources = performance.getEntriesByType('resource').map((entry) => entry.name);
    return {
      family: getComputedStyle(document.body).fontFamily,
      roman: document.fonts.check('650 1rem Inter'),
      italic: document.fonts.check('italic 400 1rem Inter'),
      romanAsset: resources.some((url) => /InterVariable[^/]*\.woff2/i.test(url) && !/Italic/i.test(url)),
      italicAsset: resources.some((url) => /InterVariable[^/]*Italic[^/]*\.woff2/i.test(url))
    };
  });

  expect(fontState.family).toContain('Inter');
  expect(fontState.roman).toBe(true);
  expect(fontState.italic).toBe(true);
  expect(fontState.romanAsset).toBe(true);
  expect(fontState.italicAsset).toBe(true);

  const metaSize = await page.locator('.news-card-footer').first().evaluate(
    (node) => Number.parseFloat(getComputedStyle(node).fontSize)
  );
  expect(metaSize).toBeGreaterThanOrEqual(14);
});

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
test('forward navigation starts at the top while Back restores the previous position', async ({ page }) => {
  const cardContainer = page.locator('[data-story-id="story-20"]');
  const card = cardContainer.locator('.news-card-link');
  await cardContainer.scrollIntoViewIfNeeded();
  await expect.poll(async () => {
    await cardContainer.scrollIntoViewIfNeeded();
    return page.evaluate(() => scrollY);
  }).toBeGreaterThan(500);
  const original = await page.evaluate(() => scrollY);

  // A newly opened story must render at the top immediately, regardless of the
  // scroll position of the feed it came from.
  await card.click();
  await expect(page.getByRole('heading', { name: 'London report 20', exact: true })).toBeVisible();
  await expect.poll(() => page.evaluate(() => scrollY)).toBeLessThanOrEqual(1);

  // Browser Back returns to the exact point in the feed.
  await page.goBack();
  await expect(page.locator('main.home-page')).toBeVisible();
  await expect.poll(() => page.evaluate(() => scrollY)).toBeGreaterThan(original - 4);
  await expect.poll(() => page.evaluate(() => scrollY)).toBeLessThan(original + 4);

  // A warmed/cached article follows the same rule.
  await card.click();
  await expect(page.getByRole('heading', { name: 'London report 20', exact: true })).toBeVisible();
  await expect.poll(() => page.evaluate(() => scrollY)).toBeLessThanOrEqual(1);
  await page.goBack();
  await expect.poll(() => page.evaluate(() => scrollY)).toBeGreaterThan(original - 4);
  await expect.poll(() => page.evaluate(() => scrollY)).toBeLessThan(original + 4);

  // Moving to another screen is also a fresh navigation, so it begins at the
  // top. Returning with Back restores the previous screen position and state.
  await openNav(page, 'Search');
  await expect.poll(() => page.evaluate(() => scrollY)).toBeLessThanOrEqual(1);
  await page.getByRole('searchbox').fill('London');
  await page.getByRole('combobox', { name: 'Section', exact: true }).selectOption('Business');
  await expect(page.getByText('18 results', { exact: true })).toBeVisible();
  await page.locator('.archive-search-hit').last().scrollIntoViewIfNeeded();
  const searchY = await page.evaluate(() => scrollY);

  await openNav(page, 'Settings');
  await expect.poll(() => page.evaluate(() => scrollY)).toBeLessThanOrEqual(1);
  await page.goBack();
  await expect(page.getByRole('searchbox')).toHaveValue('London');
  await expect(page.getByRole('combobox', { name: 'Section', exact: true })).toHaveValue('Business');
  await expect.poll(() => page.evaluate(() => scrollY)).toBeGreaterThan(searchY - 4);
});
test('missing-art feed cards keep the placeholder on the same left side as real images', async ({ page }) => {
  const card = page.locator('[data-story-id="story-10"]');
  await card.scrollIntoViewIfNeeded();

  const media = card.locator('.news-card-media');
  const body = card.locator('.news-card-body');
  await expect(media).toBeVisible();
  await expect(body).toBeVisible();

  const boxes = await Promise.all([media.boundingBox(), body.boundingBox()]);
  const [mediaBox, bodyBox] = boxes;
  expect(mediaBox).not.toBeNull();
  expect(bodyBox).not.toBeNull();

  // Feed cards with art are image-left/copy-right. Missing art must preserve
  // that exact order and must not paint a second pseudo placeholder.
  expect(mediaBox.x + mediaBox.width).toBeLessThanOrEqual(bodyBox.x + 1);
  const pseudo = await card.evaluate((node) => getComputedStyle(node, '::before').display);
  expect(pseudo).toBe('none');
});

test('restored feature cards, publisher text and category pills remain functional', async ({ page }) => {
  const first = page.locator('[data-story-id="story-0"]');
  await expect(first.getByRole('heading')).toHaveText('London report 0');
  await expect(first.locator('.news-card-summary')).toHaveCount(0);

  // Pre-polish cards keep their visual image fallback instead of becoming
  // text-only. Publisher identity is text in the accent colour, never a logo.
  const featureMedia = first.locator('.news-card-media');
  await expect(featureMedia).toBeVisible();
  await expect(first.locator('.news-card-placeholder-brand')).toContainText('News');
  await expect(first.locator('.card-source-name')).toHaveText('CTV News London');

  // A missing editorial image occupies one 16:9 media slot, not the old
  // doubled placeholder that stacked two green panels on mobile.
  const featurePseudo = await first.evaluate((node) => getComputedStyle(node, '::before').display);
  expect(featurePseudo).toBe('none');
  if (page.viewportSize().width <= 720) {
    const featureBox = await featureMedia.boundingBox();
    expect(featureBox).not.toBeNull();
    expect(featureBox.height / featureBox.width).toBeGreaterThan(0.54);
    expect(featureBox.height / featureBox.width).toBeLessThan(0.59);
  }
  await expect(first.locator('.card-source-mark')).toHaveCount(0);

  const pills = page.locator('.category-pill-strip');
  const latestPill = pills.getByRole('button', { name: 'Latest', exact: true });
  await expect(latestPill).toBeVisible();
  await expect(pills.getByRole('button', { name: 'Business', exact: true })).toBeVisible();

  // Section pills are intentionally a little more compact visually than the
  // feed scope selector, while retaining a 44px tap target.
  const pillMetrics = await latestPill.evaluate((node) => ({
    height: node.getBoundingClientRect().height,
    fontSize: Number.parseFloat(getComputedStyle(node).fontSize),
    visualInset: Number.parseFloat(getComputedStyle(node, '::before').top)
  }));
  const scopeMetrics = await page.locator('.feed-scope-button').first().evaluate((node) => ({
    height: node.getBoundingClientRect().height,
    fontSize: Number.parseFloat(getComputedStyle(node).fontSize)
  }));
  expect(pillMetrics.height).toBeGreaterThanOrEqual(44);
  expect(pillMetrics.fontSize).toBeLessThan(scopeMetrics.fontSize);
  expect(pillMetrics.visualInset).toBeGreaterThan(0);

  await pills.getByRole('button', { name: 'Business', exact: true }).click();
  await expect(pills.getByRole('button', { name: 'Business', exact: true })).toHaveAttribute('aria-pressed', 'true');

  // Return to all stories before checking the carousel interaction.
  await pills.getByRole('button', { name: 'Latest', exact: true }).click();
  const dot = page.getByRole('button', { name: 'Show top story 2 of 3' });
  await dot.click();
  await expect(page.locator('.editorial-carousel-slide').nth(0)).toHaveAttribute('inert', '');
  await expect(page.locator('.editorial-carousel-slide').nth(1)).not.toHaveAttribute('inert', '');
});

test('top story card content anchors stay stable across title lengths', async ({ page }) => {
  const cards = page.locator('.editorial-carousel-slide .editorial-carousel-card.news-card.card-featured');
  await expect(cards).toHaveCount(3);

  const metrics = await cards.evaluateAll((nodes) => nodes.slice(0, 2).map((card) => {
    const body = card.querySelector('.news-card-body');
    const source = card.querySelector('.card-source-name');
    const title = card.querySelector('h3');
    const footer = card.querySelector('.news-card-footer');
    const bodyBox = body.getBoundingClientRect();
    const sourceBox = source.getBoundingClientRect();
    const titleBox = title.getBoundingClientRect();
    const footerBox = footer.getBoundingClientRect();
    return {
      bodyHeight: bodyBox.height,
      sourceOffset: sourceBox.top - bodyBox.top,
      titleOffset: titleBox.top - bodyBox.top,
      sourceBottom: sourceBox.bottom - bodyBox.top,
      footerGap: bodyBox.bottom - footerBox.bottom
    };
  }));

  expect(Math.abs(metrics[0].bodyHeight - metrics[1].bodyHeight)).toBeLessThanOrEqual(2);
  for (const item of metrics) {
    expect(item.sourceOffset).toBeGreaterThanOrEqual(0);
    expect(item.sourceOffset).toBeLessThanOrEqual(50);
    expect(item.titleOffset).toBeGreaterThanOrEqual(item.sourceBottom - 1);
    expect(item.footerGap).toBeGreaterThanOrEqual(6);
    expect(item.footerGap).toBeLessThanOrEqual(10);
  }
});

test('public page headers are shared, subtitle-free and aligned', async ({ page }) => {
  await expect(page.locator('.home-header-date')).toHaveCount(0);

  const routes = [
    ['latest/', 'Latest'],
    ['search/', 'Search'],
    ['sections/', 'Sections'],
    ['settings/', 'Settings']
  ];
  const metrics = [];

  for (const [route, title] of routes) {
    await page.goto('./' + route);
    const heading = page.locator('.standard-page-heading');
    await expect(heading).toBeVisible();
    await expect(heading.getByRole('heading', { level: 1 })).toHaveText(title);
    await expect(heading.locator('.masthead-label')).toHaveCount(0);
    await expect(heading.locator('.page-heading-description')).toHaveCount(0);
    metrics.push(await heading.getByRole('heading', { level: 1 }).evaluate((node) => {
      const box = node.getBoundingClientRect();
      return {
        x: box.x,
        y: box.y,
        fontSize: Number.parseFloat(getComputedStyle(node).fontSize),
        lineHeight: Number.parseFloat(getComputedStyle(node).lineHeight)
      };
    }));
  }

  for (const metric of metrics.slice(1)) {
    expect(Math.abs(metric.x - metrics[0].x)).toBeLessThanOrEqual(1);
    expect(Math.abs(metric.y - metrics[0].y)).toBeLessThanOrEqual(1);
    expect(metric.fontSize).toBe(metrics[0].fontSize);
    expect(metric.lineHeight).toBe(metrics[0].lineHeight);
  }
});

test('sections segmented selector matches the shared segmented-control scale', async ({ page }) => {
  const scopeMetrics = await page.locator('.feed-scope-switch').evaluate((node) => ({
    height: node.getBoundingClientRect().height,
    fontSize: Number.parseFloat(getComputedStyle(node.querySelector('button')).fontSize)
  }));

  await page.goto('./sections/');
  const tabs = page.locator('.directory-tabs');
  await expect(tabs).toBeVisible();
  const tabMetrics = await tabs.evaluate((node) => {
    const shell = node.closest('.standard-page-shell');
    const shellStyle = getComputedStyle(shell);
    return {
      width: node.getBoundingClientRect().width,
      height: node.getBoundingClientRect().height,
      shellContentWidth: shell.clientWidth - Number.parseFloat(shellStyle.paddingLeft) - Number.parseFloat(shellStyle.paddingRight),
      fontSize: Number.parseFloat(getComputedStyle(node.querySelector('button')).fontSize)
    };
  });

  expect(Math.abs(tabMetrics.height - scopeMetrics.height)).toBeLessThanOrEqual(1);
  expect(tabMetrics.fontSize).toBe(scopeMetrics.fontSize);
  if (page.viewportSize().width <= 760) {
    expect(Math.abs(tabMetrics.width - tabMetrics.shellContentWidth)).toBeLessThanOrEqual(1);
  }
});

test('background refresh offers an edition without replacing the current list', async ({ page }) => {
  const fresh = fixture(1);
  fresh.stories[0].title = 'A newly published London report';
  await page.route('**/images/tracking.png', route => route.fulfill({contentType:'image/png',body:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aL1kAAAAASUVORK5CYII=','base64')}));
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


test('removed bookmarks migrate safely without losing preferences or read history', async ({ page }) => {
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await expect(page.locator('.news-card-save')).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Read Later', exact: true })).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => new Promise(resolve => {
    const request = indexedDB.open('london-news-user-state');
    request.onsuccess = () => {
      const db = request.result;
      const names = Array.from(db.objectStoreNames);
      const tx = db.transaction(['readStories','hiddenSources']);
      const reads = tx.objectStore('readStories').get('story-10');
      const hidden = tx.objectStore('hiddenSources').get('Other publisher');
      tx.oncomplete = () => { resolve({ removed: !names.includes('savedStories'), read: !!reads.result, hidden: !!hidden.result }); db.close(); };
    };
  }))).toEqual({removed:true,read:true,hidden:true});
});

test('related recommendations separate local reporting from Canada coverage', async ({ page }) => {
  await page.locator('[data-story-id="story-0"] .news-card-link').click();
  const london = page.getByRole('region', {name:'More from London',exact:true});
  const canada = page.getByRole('region', {name:'More from Canada',exact:true});
  await expect(london.locator('.news-card')).toHaveCount(4);
  await expect(canada.locator('.news-card')).toHaveCount(4);
  await expect(london.locator('[data-scope="canada"]')).toHaveCount(0);
  await expect(canada.locator('[data-scope="local"]')).toHaveCount(0);
  await expect(page.locator('.news-card-save')).toHaveCount(0);
});


test('responsive images use card derivatives and higher quality full viewport article covers', async ({ page }) => {
  const card = page.locator('[data-story-id="story-0"] .news-card-photo');
  await expect(card).toHaveAttribute('srcset', /card-320.*320w.*card-640.*640w.*card-1200.*1200w/);
  await expect(card).not.toHaveAttribute('srcset', /hero/);
  await page.locator('[data-story-id="story-0"] .news-card-link').click();

  const cover = page.locator('.article-cover');
  const hero = page.locator('.article-cover-media img');
  await expect(hero).toHaveAttribute('srcset', /hero-640.*640w.*hero-1600.*1600w.*hero-2400.*2400w/);
  await expect(hero).not.toHaveAttribute('src', /card-/);
  await expect(page.locator('.article-cover-fade')).toHaveCount(0);
  await expect(page.locator('.article-body-hero')).toHaveCount(0);

  const geometry = await cover.evaluate((node) => {
    const box = node.getBoundingClientRect();
    const image = node.querySelector('.article-cover-media img');
    const title = node.querySelector('h1');
    return {
      height: box.height,
      viewport: window.innerHeight,
      imageHeight: image.getBoundingClientRect().height,
      titleSize: Number.parseFloat(getComputedStyle(title).fontSize)
    };
  });
  expect(Math.abs(geometry.height - geometry.viewport)).toBeLessThanOrEqual(2);
  expect(Math.abs(geometry.imageHeight - geometry.viewport)).toBeLessThanOrEqual(2);
  expect(geometry.titleSize).toBeGreaterThanOrEqual(page.viewportSize().width <= 760 ? 48 : 52);

  const tracking = page.getByAltText('Tracking image');
  await expect.poll(() => tracking.evaluate(image => image.complete)).toBe(true);
  await expect(tracking).toBeHidden();
  await expect(tracking.locator('..')).toBeHidden();
  await noOverflow(page);
});
