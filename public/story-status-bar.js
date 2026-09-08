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

  const statusStrip = document.getElementById('ios-status-strip');
  const themeColourMeta = Array.from(document.querySelectorAll('meta[name="theme-color"]'))
    .map((meta) => ({ meta, original: meta.getAttribute('content') || '' }));

  let feedPromise;
  let scheduled = false;
  let lastStoryId = '';
  let resizeScheduled = false;

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

  function measureSafeAreaTop() {
    const probe = document.createElement('div');
    probe.setAttribute('aria-hidden', 'true');
    probe.style.cssText = [
      'position:fixed',
      'top:0',
      'left:0',
      'width:0',
      'height:env(safe-area-inset-top, 0px)',
      'visibility:hidden',
      'pointer-events:none'
    ].join(';');

    document.documentElement.appendChild(probe);
    const measured = Number.parseFloat(getComputedStyle(probe).height) || 0;
    probe.remove();

    const isiPhone = /iPhone|iPod/i.test(navigator.userAgent);
    const isiPad = /iPad/i.test(navigator.userAgent)
      || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);

    // iOS can report a zero top safe-area inset in wide/landscape standalone
    // layouts even though the system status row still overlays the web view.
    const fallback = isiPhone ? 59 : isiPad ? 24 : 0;
    const height = measured > 0 ? measured : fallback;
    root.style.setProperty('--standalone-status-height', `${Math.round(height)}px`);
  }

  function scheduleSafeAreaMeasure() {
    if (resizeScheduled) return;
    resizeScheduled = true;
    window.requestAnimationFrame(() => {
      resizeScheduled = false;
      measureSafeAreaTop();
    });
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
    root.classList.remove('story-status-coloured');
    if (statusStrip) statusStrip.style.removeProperty('background-color');
    restoreSystemThemeColour();
  }

  function applyStoryColour(colour) {
    const value = validColour(colour);
    if (!value) {
      clearStoryColour();
      return;
    }

    root.style.setProperty('--story-status-colour', value);
    root.classList.add('story-status-coloured');
    if (statusStrip) statusStrip.style.setProperty('background-color', value, 'important');
    setSystemThemeColour(value);
  }

  async function syncStoryColour() {
    scheduled = false;
    const storyId = currentStoryId();
    root.classList.toggle('story-route', Boolean(storyId));

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

  measureSafeAreaTop();
  root.classList.toggle('story-route', Boolean(currentStoryId()));

  window.addEventListener('pageshow', () => {
    scheduleSafeAreaMeasure();
    scheduleSync();
  });
  window.addEventListener('popstate', scheduleSync);
  window.addEventListener('resize', scheduleSafeAreaMeasure, { passive: true });
  window.addEventListener('orientationchange', scheduleSafeAreaMeasure);
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) {
      scheduleSafeAreaMeasure();
      scheduleSync();
    }
  });

  const observer = new MutationObserver(scheduleSync);
  observer.observe(document.body, { childList: true, subtree: true });
  scheduleSync();
})();
