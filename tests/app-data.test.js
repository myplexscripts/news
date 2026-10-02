import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import { cleanTitle, cleanSummary } from '../src/lib/editorialText.js';
import { readScreen, rememberScreen, readPosition, rememberPosition } from '../src/lib/screenState.js';

async function dataModule(fetcher, clock) {
  let code = await readFile(new URL('../src/lib/newsData.js', import.meta.url), 'utf8');
  code = code.replace("import { base } from '$app/paths';", "const base = '/news';");
  code = code.replace("import { writable } from 'svelte/store';", `import { writable } from ${JSON.stringify(pathToFileURL(process.cwd() + '/node_modules/svelte/src/store/index-server.js').href)};`);
  code = code.replace("from './editorialText'", `from ${JSON.stringify(new URL('../src/lib/editorialText.js', import.meta.url).href)}`);
  // Each case uses an isolated module cache and controlled network/clock.
  code = `const fetch = globalThis.__testFetch; const now = globalThis.__testClock; const Date = class extends globalThis.Date { static now() { return now(); } };\n` + code;
  globalThis.__testFetch = fetcher;
  globalThis.__testClock = clock;
  return import('data:text/javascript;base64,' + Buffer.from(code + `\n// ${Math.random()}`).toString('base64'));
}
const edition = (generated_at, title = 'Headline') => ({ generated_at, stories: [{ id: 'one', title, summary: title }] });
test('known publisher suffixes and repeated decks are removed without changing reporting', () => {
  assert.equal(cleanTitle('London votes - CBC.CA'), 'London votes');
  assert.equal(cleanTitle('CBC reports on London'), 'CBC reports on London');
  assert.equal(cleanSummary('London votes CBC', 'London votes'), '');
  assert.equal(cleanSummary('A different detail.', 'London votes'), 'A different detail.');
});
test('tabs keep independent filters, content and positions with bounded memory', () => {
  rememberScreen('home', { category: 'Business' });
  rememberScreen('search', { query: 'rocket' });
  assert.equal(readScreen('home').category, 'Business');
  assert.equal(readScreen('search').query, 'rocket');
  rememberPosition('/home', { y: 960 });
  assert.equal(readPosition('/home').y, 960);
  for (let i = 0; i < 45; i++) rememberScreen('article' + i, {});
  assert.equal(readScreen('home'), undefined);
});
test('feed requests coalesce, expire, refresh and preserve cached data on failure', async () => {
  let now = 10000; let calls = 0; let payload = edition('2026-10-02T12:00:00Z'); let fail = false;
  const mod = await dataModule(async () => { calls++; if (fail) throw new Error('offline'); return { ok: true, json: async () => payload }; }, () => now);
  const [first, same] = await Promise.all([mod.loadFeed(), mod.loadFeed()]);
  assert.equal(calls, 1);
  assert.equal(first, same);
  assert.equal(await mod.loadFeed(), first);
  assert.equal(calls, 1);
  now += 300001; payload = edition('2026-10-02T12:05:00Z');
  const next = await mod.loadFeed();
  assert.equal(calls, 2); assert.notEqual(next, first);
  fail = true;
  assert.equal(await mod.loadFeed({ force: true }), next);
  assert.equal(mod.getCachedFeed(), next);
  let status; mod.feedStatus.subscribe(value => status = value)();
  assert.equal(status.unavailable, true);
  fail = false;
  assert.equal(await mod.loadFeed({ force: true }), next);
  mod.feedStatus.subscribe(value => status = value)();
  assert.equal(status.unavailable, false);
});
test('invalid first feed rejects and can retry; article prefetch populates synchronous cache', async () => {
  let valid = false; let calls = 0;
  const mod = await dataModule(async url => {
    calls++;
    if (url.includes('/stories/')) return { ok: true, json: async () => ({ id: 'one', title: 'Title - CBC.CA' }) };
    return { ok: true, json: async () => valid ? edition('2026-10-02T12:00:00Z') : {} };
  }, () => 10000);
  await assert.rejects(mod.loadFeed());
  valid = true; await mod.loadFeed();
  await mod.loadStory('one');
  assert.equal(mod.getCachedStory('one').title, 'Title');
  await mod.loadStory('one');
  assert.equal(calls, 3);
});

test('article image derivatives only apply to their matching original sources', async () => {
  const source = 'https://example.test/new-photo.jpg';
  const mod = await dataModule(async () => ({ok:true,json:async () => ({
    id:'images', title:'Report', image:source,
    editorial_image:'cache/old.webp',editorial_image_source:'https://example.test/old-photo.jpg',
    editorial_image_variants:[{url:'cache/old-640.webp',width:640}],
    content_blocks:[{type:'image',url:source,optimized_url:'cache/old.webp',optimized_url_source:'https://example.test/old-photo.jpg',image_variants:[{url:'cache/old-640.webp',width:640}]}]
  })}), () => 1);
  const article = await mod.loadStory('images',{_data_file:'images.json'});
  assert.equal(article.image,source);
  assert.deepEqual(article.editorial_image_variants,[]);
  assert.deepEqual(article.content_blocks[0].image_variants,[]);
});
