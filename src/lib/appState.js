import { writable } from 'svelte/store';

export const DEFAULT_USER_STATE = {
  theme: 'light',
  accent: 'green',
  hideRead: false,
  readIds: [],
  savedIds: [],
  hiddenSources: []
};

export const userState = writable(DEFAULT_USER_STATE);

let modulePromise;
let stateInitialised = false;

function stateModule() {
  modulePromise ||= import('./userState');
  return modulePromise;
}

export async function initialiseAppState() {
  const mod = await stateModule();
  if (!stateInitialised) {
    const state = await mod.initialiseUserState();
    userState.set(state);
    mod.onUserStateChange((next) => userState.set(next));
    stateInitialised = true;
  } else {
    userState.set(await mod.getUserState());
  }
}

export async function saveStory(id, saved) {
  const mod = await stateModule();
  return mod.setStorySaved(id, saved);
}

export async function toggleSavedStory(id) {
  const mod = await stateModule();
  return mod.toggleStorySaved(id);
}

export async function markRead(id) {
  const mod = await stateModule();
  return mod.markStoryRead(id);
}

export async function setAppPreference(key, value) {
  const mod = await stateModule();
  return mod.setPreference(key, value);
}

export async function setHiddenSource(name, hidden) {
  const mod = await stateModule();
  return mod.setSourceHidden(name, hidden);
}

export async function revealAllSources() {
  const mod = await stateModule();
  return mod.showAllSources();
}

export async function clearRead() {
  const mod = await stateModule();
  return mod.clearReadHistory();
}

export async function clearSaved() {
  const mod = await stateModule();
  return mod.clearSavedStories();
}

export async function clearEverything() {
  const mod = await stateModule();
  const next = await mod.clearAllUserData();
  userState.set(next);
  return next;
}
