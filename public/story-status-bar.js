(() => {
  const root = document.documentElement;
  const standalone =
    window.navigator.standalone === true
    || window.matchMedia?.('(display-mode: standalone)').matches === true;

  root.classList.toggle('standalone-webapp', standalone);
  if (!standalone) return;

  const ownScript = document.currentScript;
  let basePath = '';
  try {
    const pathname = ownScript?.src ? new URL(ownScript.src).pathname : '';
    basePath = pathname.replace(/\/story-status-bar\.js$/, '');
  } catch {
    basePath = '';
  }
  if (basePath === '/') basePath = '';

  const themeColourMeta = Array.from(document.querySelectorAll('meta[name="theme-color"]'))
    .map((meta) => ({ meta, original: meta.getAttribute('content') || '' }));

  let feedPromise;
  let scheduled = false;
  let lastStoryId = '';

  function currentStoryId() {
    const prefix = `${basePath}/story/`.replace(/\/+/g, '/');
    const pathname = window.location.pathname;
    if (!pathname.startsWith(prefix)) return '';
    const remainder = pathname.slice(prefix.length).split('/')[0];
    try {
      return decodeURIComponent(remainder || '');
    } catch {
      return remainder || '';
    }
  }

  function loadFeed() {
    if (!feedPromise) {
      feedPromise = fetch(`${basePath}/data/app-feed.json`, {
        credentials: 'same-origin',
        cache: 'no-store'
      })
        .then((response) => {
          if (!response.ok) throw new Error(`Feed ${response.status}`);
          return response.json();
        })
        .catch(() => ({ stories: [] }));
    }
    return feedPromise;
  }

  function validColour(value) {
    const colour = String(value || '').trim();
    return /^#[0-9a-f]{6}$/i.test(colour) ? colour : '';
  }

  function setSystemThemeColour(colour) {
    const value = validColour(colour);
    if (!value) return;
    for (const entry of themeColourMeta) {
      entry.meta.setAttribute('content', value);
    }
  }

  function restoreSystemThemeColour() {
    for (const entry of themeColourMeta) {
      entry.meta.setAttribute('content', entry.original);
    }
  }

  function clearStoryColour() {
    root.style.removeProperty('--story-status-colour');
    root.style.removeProperty('background-color');
    root.classList.remove('story-status-coloured');
    restoreSystemThemeColour();
  }

  function applyStoryColour(colour) {
    const value = validColour(colour);
    if (!value) {
      clearStoryColour();
      return;
    }

    root.style.setProperty('--story-status-colour', value);
    root.style.setProperty('background-color', value);
    root.classList.add('story-status-coloured');
    setSystemThemeColour(value);
  }

  async function syncStoryColour() {
    scheduled = false;
    const storyPage = document.querySelector('.svelte-article-page');
    const storyId = storyPage ? currentStoryId() : '';

    if (!storyId) {
      lastStoryId = '';
      clearStoryColour();
      return;
    }

    if (
      storyId === lastStoryId
      && root.classList.contains('story-status-coloured')
      && root.style.getPropertyValue('--story-status-colour')
    ) return;
    lastStoryId = storyId;

    const feed = await loadFeed();
    if (currentStoryId() !== storyId) return;

    const story = (feed.stories || []).find((item) => String(item.id) === storyId);
    applyStoryColour(story?.hero_top_colour);
  }

  function scheduleSync() {
    if (scheduled) return;
    scheduled = true;
    window.requestAnimationFrame(syncStoryColour);
  }

  window.addEventListener('pageshow', scheduleSync);
  window.addEventListener('popstate', scheduleSync);
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) scheduleSync();
  });

  const observer = new MutationObserver(scheduleSync);
  observer.observe(document.body, { childList: true, subtree: true });
  scheduleSync();
})();
