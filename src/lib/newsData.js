import { base } from '$app/paths';
import { writable } from 'svelte/store';
import { cleanTitle, cleanSummary } from './editorialText';

let feedPromise;
let cachedFeed;
let checkedAt = 0;
const FEED_TTL = 5 * 60 * 1000;
export const feedUpdates = writable(null);
export const homeEdition = writable(null);
export const feedStatus = writable({ refreshing: false, unavailable: false });
const cachedStories = new Map();
export const getCachedStory = (id) => cachedStories.get(String(id));
export const getCachedFeed = () => cachedFeed;
const storyPromises = new Map();

const dataUrl = (path) => `${base}/data/${path}`.replace(/\/+/g, '/');

export function resolveAsset(value = '') {
  const src = String(value || '').trim();
  if (!src) return '';
  if (/^https?:\/\//i.test(src) || src.startsWith('/')) return src;
  return `${base}/${src}`.replace(/\/+/g, '/');
}

export function storyHref(id) {
  return `${base}/story/${encodeURIComponent(String(id || ''))}/`;
}

function feedCard(story) {
  const title = cleanTitle(story.title);
  return { ...story, title, summary: cleanSummary(story.summary, title) };
}

function applyEditorialImages(story) {
  if (!story || typeof story !== 'object') return story;

  const originalHero = String(story.image || '').trim();
  const heroOptimized = String(story.editorial_image || '').trim();
  const heroSource = String(story.editorial_image_source || '').trim();
  const validHeroOptimized = heroOptimized && heroSource && heroSource === originalHero
    ? heroOptimized
    : '';
  let changed = false;
  const next = { ...story };

  if (!validHeroOptimized && story.editorial_image_variants?.length) {
    next.editorial_image_variants = [];
    changed = true;
  }
  if (validHeroOptimized) {
    next.original_image = originalHero;
    next.image = validHeroOptimized;
    next.image_width = story.editorial_image_width;
    next.image_height = story.editorial_image_height;
    changed = true;
  }

  if (Array.isArray(story.content_blocks)) {
    const blocks = story.content_blocks.map((block) => {
      if (!block || block.type !== 'image') return block;
      const source = String(block.url || '').trim();
      const optimizedSource = String(block.optimized_url_source || '').trim();
      const blockOptimized = String(block.optimized_url || '').trim();
      const validBlockOptimized = blockOptimized && optimizedSource === source ? blockOptimized : '';
      const optimized = validBlockOptimized
        || (validHeroOptimized && source === heroSource ? validHeroOptimized : '');
      if (!optimized) {
        if (block.image_variants?.length) { changed = true; return { ...block, image_variants: [] }; }
        return block;
      }
      if (optimized === source) return block;
      changed = true;
      return { ...block, original_url: source, url: optimized, width: block.optimized_url_width || block.width, height: block.optimized_url_height || block.height };
    });
    if (changed) next.content_blocks = blocks;
  }

  return changed ? next : story;
}

export function loadFeed({ force = false } = {}) {
  if (cachedFeed && !force && Date.now() - checkedAt < FEED_TTL) return Promise.resolve(cachedFeed);
  if (feedPromise) return feedPromise;
  feedStatus.set({ refreshing: true, unavailable: false });
  feedPromise = (async () => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 12000);
    try {
      const response = await fetch(dataUrl('app-feed.json'), { cache: 'no-store', signal: controller.signal });
      if (!response.ok) throw new Error(`Unable to load news feed (${response.status})`);
      const feed = await response.json();
      if (!Array.isArray(feed.stories) || !feed.generated_at) throw new Error('The news feed is temporarily unavailable.');
      feed.stories = feed.stories.map(feedCard);
      checkedAt = Date.now();
      // Retain object identity when the server has no new edition.
      if (!cachedFeed || cachedFeed.generated_at !== feed.generated_at) {
        cachedFeed = feed;
        feedUpdates.set(feed);
      }
      feedStatus.set({ refreshing: false, unavailable: false });
      return cachedFeed;
    } catch (error) {
      feedStatus.set({ refreshing: false, unavailable: true });
      if (cachedFeed) return cachedFeed;
      throw error;
    } finally {
      clearTimeout(timeout);
      feedPromise = undefined;
    }
  })();
  return feedPromise;
}

export function storyTimestamp(story) {
  const value = story?.cluster_latest_published || story?.published || 0;
  const time = new Date(value).getTime();
  return Number.isFinite(time) ? time : 0;
}

export function sortNewest(stories = []) {
  return [...stories].sort((a, b) => storyTimestamp(b) - storyTimestamp(a));
}

export async function loadStory(id, metadata) {
  const storyId = String(id || '').trim();
  if (!storyId) throw new Error('Missing story id');

  if (!storyPromises.has(storyId)) {
    const filename = metadata?._data_file || `${encodeURIComponent(storyId)}.json`;
    const promise = fetch(dataUrl(`stories/${filename}`), { cache: 'no-store' })
      .then((response) => {
        if (!response.ok) throw new Error(`Unable to load article (${response.status})`);
        return response.json();
      })
      .then((payload) => {
        const story = applyEditorialImages(feedCard(payload));
        cachedStories.set(storyId, story);
        if (cachedStories.size > 80) {
          const oldest = cachedStories.keys().next().value;
          cachedStories.delete(oldest);
          storyPromises.delete(oldest);
        }
        return story;
      })
      .catch((error) => {
        storyPromises.delete(storyId);
        throw error;
      });
    storyPromises.set(storyId, promise);
  }

  return storyPromises.get(storyId);
}

export function prefetchStory(story) {
  if (!story?.id) return;
  loadStory(story.id, story).catch(() => {});
}

export function scopeForStory(story, sourceHealth = {}) {
  const explicit = String(story?.scope || '').toLowerCase();
  if (explicit === 'local' || explicit === 'canada') return explicit;

  const source = String(story?.discovery_via || story?.source || '').trim();
  const health = sourceHealth?.[source] || {};
  const scope = String(health.scope || '').toLowerCase();
  return scope === 'local' || scope === 'canada' ? scope : 'local';
}

export function formatRelativeTime(value) {
  const time = new Date(value || 0).getTime();
  if (!Number.isFinite(time)) return '';
  const minutes = Math.max(0, Math.floor((Date.now() - time) / 60000));
  if (minutes < 1) return 'Just now';
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d`;
  try {
    return new Intl.DateTimeFormat('en-CA', {
      month: 'short',
      day: 'numeric',
      timeZone: 'America/Toronto'
    }).format(new Date(time));
  } catch {
    return '';
  }
}

export function formatPublished(value) {
  try {
    return new Intl.DateTimeFormat('en-CA', {
      timeZone: 'America/Toronto',
      weekday: 'long',
      month: 'long',
      day: 'numeric',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit'
    }).format(new Date(value));
  } catch {
    return '';
  }
}