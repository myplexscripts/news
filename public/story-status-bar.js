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
      feedPromise = fetch(`${basePath}/data/app-feed.json`, { credentials: 'same-origin' })
        .then((response) => {
          if (!response.ok) throw new Error(`Feed ${response.status}`);
          return response.json();
        })
        .catch(() => ({ stories: [] }));
    }
    return feedPromise;
  }

  async function syncStoryColour() {
    scheduled = false;
    const storyPage = document.querySelector('.svelte-article-page');
    const storyId = storyPage ? currentStoryId() : '';

    if (!storyId) {
      lastStoryId = '';
      root.style.removeProperty('--story-status-colour');
      return;
    }

    if (storyId === lastStoryId && root.style.getPropertyValue('--story-status-colour')) return;
    lastStoryId = storyId;

    const feed = await loadFeed();
    if (currentStoryId() !== storyId) return;

    const story = (feed.stories || []).find((item) => String(item.id) === storyId);
    const colour = String(story?.hero_top_colour || '').trim();
    if (/^#[0-9a-f]{6}$/i.test(colour)) {
      root.style.setProperty('--story-status-colour', colour);
    } else {
      root.style.removeProperty('--story-status-colour');
    }
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
