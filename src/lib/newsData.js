import { base } from '$app/paths';

let feedPromise;
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
  return story;
}

export async function loadFeed() {
  if (!feedPromise) {
    feedPromise = (async () => {
      const response = await fetch(dataUrl('app-feed.json'), { cache: 'no-store' });
      if (!response.ok) throw new Error(`Unable to load news feed (${response.status})`);
      const feed = await response.json();
      feed.stories = Array.isArray(feed.stories) ? feed.stories.map(feedCard) : [];
      return feed;
    })().catch((error) => {
      feedPromise = undefined;
      throw error;
    });
  }
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
