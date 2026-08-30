import Dexie, { type Table } from 'dexie';

export type LondonNewsUserState = {
  theme: 'light' | 'dark';
  accent: string;
  hideRead: boolean;
  readIds: string[];
  savedIds: string[];
  hiddenSources: string[];
};

type PreferenceRecord = {
  key: string;
  value: string;
  updatedAt: number;
};

type ReadStoryRecord = {
  id: string;
  readAt: number;
};

type SavedStoryRecord = {
  id: string;
  savedAt: number;
};

type HiddenSourceRecord = {
  name: string;
  hiddenAt: number;
};

class LondonNewsDatabase extends Dexie {
  preferences!: Table<PreferenceRecord, string>;
  readStories!: Table<ReadStoryRecord, string>;
  savedStories!: Table<SavedStoryRecord, string>;
  hiddenSources!: Table<HiddenSourceRecord, string>;

  constructor() {
    super('london-news-user-state');
    this.version(1).stores({
      preferences: '&key,updatedAt',
      readStories: '&id,readAt',
      hiddenSources: '&name,hiddenAt'
    });
    this.version(2).stores({
      preferences: '&key,updatedAt',
      readStories: '&id,readAt',
      savedStories: '&id,savedAt',
      hiddenSources: '&name,hiddenAt'
    });
    // Read Later launched with an unsafe legacy-key import that could pull
    // unrelated browser data into savedStories. Version 3 resets only that
    // brand-new table once, then all future entries come from explicit saves.
    this.version(3).stores({
      preferences: '&key,updatedAt',
      readStories: '&id,readAt',
      savedStories: '&id,savedAt',
      hiddenSources: '&name,hiddenAt'
    }).upgrade(async (transaction) => {
      await transaction.table('savedStories').clear();
    });
  }
}

const db = new LondonNewsDatabase();
const CHANNEL_NAME = 'london-news-user-state';
const BAD_READ_LATER_KEY = 'london-news-read-later';
const LEGACY = {
  theme: 'london-news-theme',
  accent: 'london-news-accent',
  hideRead: 'london-news-hide-read',
  reads: 'london-news-read-articles',
  // This is a new fallback key, not a legacy migration source. The original
  // key was already present in some browsers and must never be imported.
  saved: 'london-news-read-later-v1',
  hiddenSources: 'london-news-hidden-sources'
};

const channel = typeof BroadcastChannel !== 'undefined' ? new BroadcastChannel(CHANNEL_NAME) : null;

function safeArray(key: string): string[] {
  if (typeof localStorage === 'undefined') return [];
  try {
    const value = JSON.parse(localStorage.getItem(key) || '[]');
    return Array.isArray(value) ? value.map(String).filter(Boolean) : [];
  } catch {
    return [];
  }
}

function preferredTheme(): 'light' | 'dark' {
  if (typeof matchMedia !== 'undefined' && matchMedia('(prefers-color-scheme: dark)').matches) return 'dark';
  return 'light';
}

async function snapshot(): Promise<LondonNewsUserState> {
  const [preferenceRows, readRows, savedRows, hiddenRows] = await Promise.all([
    db.preferences.toArray(),
    db.readStories.orderBy('readAt').reverse().toArray(),
    db.savedStories.orderBy('savedAt').reverse().toArray(),
    db.hiddenSources.toArray()
  ]);
  const preferences = new Map(preferenceRows.map((row) => [row.key, row.value]));
  const theme = preferences.get('theme') === 'dark' ? 'dark' : preferences.get('theme') === 'light' ? 'light' : preferredTheme();
  const accent = preferences.get('accent') || 'green';
  const hideRead = preferences.get('hideRead') === 'true';
  return {
    theme,
    accent,
    hideRead,
    readIds: readRows.map((row) => row.id),
    savedIds: savedRows.map((row) => row.id),
    hiddenSources: hiddenRows.map((row) => row.name).sort((a, b) => a.localeCompare(b))
  };
}

function syncLegacyMirrors(state: LondonNewsUserState) {
  if (typeof localStorage === 'undefined') return;
  localStorage.setItem(LEGACY.theme, state.theme);
  localStorage.setItem(LEGACY.accent, state.accent);
  localStorage.setItem(LEGACY.hideRead, state.hideRead ? 'true' : 'false');
  localStorage.setItem(LEGACY.reads, JSON.stringify(state.readIds));
  localStorage.setItem(LEGACY.saved, JSON.stringify(state.savedIds));
  localStorage.setItem(LEGACY.hiddenSources, JSON.stringify(state.hiddenSources));
}

function emit(state: LondonNewsUserState, broadcast = true) {
  syncLegacyMirrors(state);
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('london-news-user-state', { detail: state }));
  }
  if (broadcast) channel?.postMessage(state);
}

async function reconcileLegacyState() {
  if (typeof localStorage === 'undefined') return;
  const now = Date.now();
  const theme = localStorage.getItem(LEGACY.theme);
  const accent = localStorage.getItem(LEGACY.accent);
  const hideRead = localStorage.getItem(LEGACY.hideRead);
  const readIds = safeArray(LEGACY.reads);
  const hiddenSources = safeArray(LEGACY.hiddenSources);

  // Never import Read Later from the pre-launch key. Saved stories are new state
  // and may only be created by an explicit bookmark action.
  localStorage.removeItem(BAD_READ_LATER_KEY);

  await db.transaction('rw', db.preferences, db.readStories, db.hiddenSources, async () => {
    const preferences: PreferenceRecord[] = [];
    if (theme === 'light' || theme === 'dark') preferences.push({ key: 'theme', value: theme, updatedAt: now });
    if (accent) preferences.push({ key: 'accent', value: accent, updatedAt: now });
    if (hideRead === 'true' || hideRead === 'false') preferences.push({ key: 'hideRead', value: hideRead, updatedAt: now });

    for (const preference of preferences) {
      const existing = await db.preferences.get(preference.key);
      if (!existing) await db.preferences.put(preference);
    }

    if (readIds.length) {
      const existingReads = new Set((await db.readStories.bulkGet(readIds)).map((row) => row?.id).filter(Boolean));
      const missing = readIds
        .filter((id) => !existingReads.has(id))
        .map((id, index) => ({ id, readAt: now - index }));
      if (missing.length) await db.readStories.bulkPut(missing);
    }

    if (hiddenSources.length) {
      const existingHidden = new Set((await db.hiddenSources.bulkGet(hiddenSources)).map((row) => row?.name).filter(Boolean));
      const missing = hiddenSources
        .filter((name) => !existingHidden.has(name))
        .map((name, index) => ({ name, hiddenAt: now - index }));
      if (missing.length) await db.hiddenSources.bulkPut(missing);
    }
  });
}

export async function initialiseUserState(): Promise<LondonNewsUserState> {
  try {
    await reconcileLegacyState();
    const state = await snapshot();
    emit(state, false);
    return state;
  } catch {
    const fallback: LondonNewsUserState = {
      theme: (typeof localStorage !== 'undefined' && localStorage.getItem(LEGACY.theme) === 'dark') ? 'dark' : preferredTheme(),
      accent: typeof localStorage !== 'undefined' ? localStorage.getItem(LEGACY.accent) || 'green' : 'green',
      hideRead: typeof localStorage !== 'undefined' && localStorage.getItem(LEGACY.hideRead) === 'true',
      readIds: safeArray(LEGACY.reads),
      savedIds: safeArray(LEGACY.saved),
      hiddenSources: safeArray(LEGACY.hiddenSources)
    };
    emit(fallback, false);
    return fallback;
  }
}

export async function importLegacyUserState(): Promise<LondonNewsUserState> {
  await reconcileLegacyState();
  const state = await snapshot();
  emit(state);
  return state;
}

export async function getUserState(): Promise<LondonNewsUserState> {
  try {
    return await snapshot();
  } catch {
    return initialiseUserState();
  }
}

export async function setPreference(key: 'theme' | 'accent' | 'hideRead', value: string | boolean) {
  const text = typeof value === 'boolean' ? (value ? 'true' : 'false') : String(value);
  await db.preferences.put({ key, value: text, updatedAt: Date.now() });
  const state = await snapshot();
  emit(state);
  return state;
}

export async function markStoryRead(id: string) {
  const storyId = String(id || '').trim();
  if (!storyId) return getUserState();
  await db.readStories.put({ id: storyId, readAt: Date.now() });
  const count = await db.readStories.count();
  if (count > 1000) {
    const stale = await db.readStories.orderBy('readAt').limit(count - 1000).primaryKeys();
    await db.readStories.bulkDelete(stale);
  }
  const state = await snapshot();
  emit(state);
  return state;
}

export async function clearReadHistory() {
  await db.readStories.clear();
  const state = await snapshot();
  emit(state);
  return state;
}

export async function setStorySaved(id: string, saved: boolean) {
  const storyId = String(id || '').trim();
  if (!storyId) return getUserState();
  if (saved) await db.savedStories.put({ id: storyId, savedAt: Date.now() });
  else await db.savedStories.delete(storyId);
  const state = await snapshot();
  emit(state);
  return state;
}

export async function toggleStorySaved(id: string) {
  const storyId = String(id || '').trim();
  if (!storyId) return getUserState();
  const existing = await db.savedStories.get(storyId);
  return setStorySaved(storyId, !existing);
}

export async function clearSavedStories() {
  await db.savedStories.clear();
  const state = await snapshot();
  emit(state);
  return state;
}

export async function setSourceHidden(name: string, hidden: boolean) {
  const sourceName = String(name || '').trim();
  if (!sourceName) return getUserState();
  if (hidden) await db.hiddenSources.put({ name: sourceName, hiddenAt: Date.now() });
  else await db.hiddenSources.delete(sourceName);
  const state = await snapshot();
  emit(state);
  return state;
}

export async function showAllSources() {
  await db.hiddenSources.clear();
  const state = await snapshot();
  emit(state);
  return state;
}

export function onUserStateChange(listener: (state: LondonNewsUserState) => void) {
  const localHandler = (event: Event) => listener((event as CustomEvent<LondonNewsUserState>).detail);
  const channelHandler = (event: MessageEvent<LondonNewsUserState>) => {
    syncLegacyMirrors(event.data);
    listener(event.data);
  };
  if (typeof window !== 'undefined') window.addEventListener('london-news-user-state', localHandler);
  channel?.addEventListener('message', channelHandler);
  return () => {
    if (typeof window !== 'undefined') window.removeEventListener('london-news-user-state', localHandler);
    channel?.removeEventListener('message', channelHandler);
  };
}
