<script>
  import { browser } from '$app/environment';
  import { onMount } from 'svelte';
  import { afterNavigate, goto, preloadCode } from '$app/navigation';
  import AppNavigation from '$lib/components/AppNavigation.svelte';
  import { page } from '$app/stores';
  import { base } from '$app/paths';
  import { initialiseAppState, userState } from '$lib/appState';
  import { loadFeed } from '$lib/newsData';
  import { sourceLogoPath } from '$lib/sourceLogos';

  import '../styles/global.css';
  import '../styles/article-rich.css';
  import '../styles/editorial-home.css';
  import '../styles/feed-scope.css';
  import '../styles/mobile-card-fixes.css';
  import '../styles/polish.css';
  import '../styles/svelte-app.css';
  import '../styles/app-system.css';

  let canGoBack = false;
  let routeStage;
  let routeAnimation;
  afterNavigate(({ from, to }) => {
    canGoBack = !!from;
    document.documentElement.classList.toggle('story-route', !!to?.url.pathname.includes('/story/'));
    if (!from || from.url.pathname === to?.url.pathname) return;
    routeAnimation?.cancel();
    if (!matchMedia('(prefers-reduced-motion: reduce)').matches) {
      routeAnimation = routeStage?.animate([{ opacity: 0.65 }, { opacity: 1 }], { duration: 180, easing: 'ease-out' });
    }
  });

  let homeDate = formatHomeDate(new Date());
  let homeUpdated = '';
  let storyMetaVisible = false;
  let shellFeed;

  function normalizedPath(pathname = '') {
    const withoutBase = base && pathname.startsWith(base) ? pathname.slice(base.length) : pathname;
    return withoutBase || '/';
  }

  function storyIdFromPath(pathname = '') {
    const match = String(pathname).match(/^\/story\/([^/]+)/);
    if (!match) return '';
    try {
      return decodeURIComponent(match[1]);
    } catch {
      return match[1];
    }
  }

  function formatHomeDate(value) {
    try {
      return new Intl.DateTimeFormat('en-CA', {
        timeZone: 'America/Toronto',
        month: 'long',
        day: 'numeric'
      }).format(new Date(value));
    } catch {
      return '';
    }
  }

  function formatUpdated(value) {
    try {
      return new Intl.DateTimeFormat('en-CA', {
        timeZone: 'America/Toronto',
        hour: 'numeric',
        minute: '2-digit'
      }).format(new Date(value));
    } catch {
      return '';
    }
  }

  function formatStoryPublished(value) {
    if (!value) return '';
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

  $: currentPath = normalizedPath($page.url.pathname);
  $: onHome = currentPath === '/';
  $: onStory = currentPath.startsWith('/story/');
  $: onDirectory = currentPath.startsWith('/sections/') || currentPath.startsWith('/sources/');
  $: onSearch = currentPath.startsWith('/search/');
  $: onSettings = currentPath.startsWith('/settings/');
  $: currentStoryId = onStory ? storyIdFromPath(currentPath) : '';
  $: storyMeta = currentStoryId && shellFeed
    ? (shellFeed.stories || []).find((item) => String(item.id) === String(currentStoryId))
    : null;
  $: storySourceName = storyMeta?.source || '';
  $: storySourceLogo = storySourceName ? sourceLogoPath(storySourceName, `${base}/`) : '';
  $: storyPublishedLabel = formatStoryPublished(storyMeta?.published);
  $: storyReadMinutes = storyMeta && Number(storyMeta.word_count) > 0
    ? Math.max(1, Math.round(Number(storyMeta.word_count) / 220))
    : null;
  $: if (!onStory) {
    storyMetaVisible = false;
  }
  $: if (browser && currentPath) queueMicrotask(syncScrollChrome);
  $: if (browser && onStory && storyMeta) queueMicrotask(() => syncStoryHeroAuthor());

  function activeIcon(active, icon) {
    return active ? `ph-fill ph-${icon}` : `ph ph-${icon}`;
  }

  function syncStoryHeroAuthor(attempt = 0) {
    if (!browser || !onStory || !storyMeta) return;
    const slot = document.querySelector('.article-cover-source');
    if (!slot) {
      if (attempt < 18) requestAnimationFrame(() => syncStoryHeroAuthor(attempt + 1));
      return;
    }

    const author = String(storyMeta.author || '').trim();
    slot.replaceChildren();
    if (!author) return;

    const label = document.createElement('strong');
    label.className = 'story-hero-author';
    label.textContent = /^by\s+/i.test(author) ? author : `By ${author}`;
    slot.appendChild(label);
  }

  function syncScrollChrome() {
    if (!browser) return;

    const storyScroll = onStory ? window.scrollY : 0;
    storyMetaVisible = onStory && storyScroll > 34;
    document.body.classList.toggle('story-meta-visible', storyMetaVisible);
  }

  onMount(() => {
    initialiseAppState().catch(() => {});
    const preloadTimer = window.setTimeout(() => {
      if (!navigator.connection?.saveData) preloadCode(`${base}/*`).catch(() => {});
    }, 300);

    loadFeed().then((feed) => {
      shellFeed = feed;
      if (!feed?.generated_at) return;
      homeDate = formatHomeDate(feed.generated_at);
      homeUpdated = formatUpdated(feed.generated_at);
    }).catch(() => {});

    const unsubscribe = userState.subscribe((state) => {
      const root = document.documentElement;
      root.dataset.theme = state.theme || 'light';
      root.dataset.accent = state.accent || 'green';
      root.dataset.hideRead = state.hideRead ? 'true' : 'false';
    });

    window.addEventListener('scroll', syncScrollChrome, { passive: true });
    window.addEventListener('resize', syncScrollChrome, { passive: true });
    syncScrollChrome();

    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register(`${base}/sw.js`).then((registration) => registration.update()).catch(() => {});
    }

    return () => {
      unsubscribe();
      clearTimeout(preloadTimer);
      routeAnimation?.cancel();
      document.body.classList.remove('story-meta-visible');
      window.removeEventListener('scroll', syncScrollChrome);
      window.removeEventListener('resize', syncScrollChrome);
    };
  });
</script>

<svelte:head>
  <title>Forest City News</title>
  <meta name="description" content="Local news from London, Ontario, plus important stories from across Canada." />
</svelte:head>

<a class="skip-link" href="#main-content">Skip to content</a>

<header class:site-header-home={onHome} class="site-header">
  <div class:home-header-inner={onHome} class="shell header-inner header-inner-simple">
    <div class="brand-area">
      {#if onStory}
        <button class="icon-button reader-back" type="button" aria-label="Back" on:click={() => canGoBack ? history.back() : goto(`${base}/`)}>
          <i class="ph ph-caret-left" aria-hidden="true"></i>
        </button>
        <a
          class="brand brand-story-source"
          href={`${base}/`}
          data-sveltekit-preload-data="tap"
          aria-label={storySourceName ? `${storySourceName}, return home` : 'Return home'}
        >
          {#if storySourceLogo}
            <img class="brand-story-source-logo" src={storySourceLogo} alt={storySourceName} />
          {:else if storySourceName}
            <span class="brand-story-source-name">{storySourceName}</span>
          {/if}
        </a>
      {:else}
        <a class="brand brand-news" href={`${base}/`} data-sveltekit-preload-data="tap" aria-label="Forest City News home">
          <i class="ph-fill ph-tree brand-news-icon" aria-hidden="true"></i>
          <span class="brand-news-wordmark">News</span>
        </a>
      {/if}
    </div>

    <div class="header-actions">
      <a class="icon-button header-search-link" href={`${base}/search/`} data-sveltekit-preload-data="tap" aria-label="Search news" title="Search">
        <i class="ph ph-magnifying-glass" aria-hidden="true"></i>
      </a>
      <a class:active={onDirectory} class="icon-button desktop-sources-link" href={`${base}/sections/`} data-sveltekit-preload-data="tap" aria-label="Browse sections and sources" title="Sections" aria-current={onDirectory ? 'page' : undefined}>
        <i class={activeIcon(onDirectory, 'hard-drives')} aria-hidden="true"></i>
      </a>
      <a class:active={onSettings} class="icon-button settings-link" href={`${base}/settings/`} data-sveltekit-preload-data="tap" aria-label="Settings" title="Settings" aria-current={onSettings ? 'page' : undefined}>
        <i class={activeIcon(onSettings, 'gear-six')} aria-hidden="true"></i>
      </a>
    </div>

    {#if onHome}
      <div class="home-meta-row">
        <p class="home-header-date">{homeDate}</p>
        {#if homeUpdated}<p class="home-header-updated">Updated {homeUpdated}</p>{/if}
      </div>
    {/if}
  </div>
</header>

{#if onStory && storyMeta}
  <div
    class:visible={storyMetaVisible}
    class="story-cover-secondary-meta"
    aria-hidden={storyMetaVisible ? 'false' : 'true'}
  >
    {#if storyPublishedLabel}<time datetime={storyMeta.published}>{storyPublishedLabel}</time>{/if}
    {#if storyReadMinutes}<span>{storyReadMinutes} min read</span>{/if}
  </div>
{/if}

<div class="svelte-route-stage" bind:this={routeStage}>
  <slot />
</div>

<footer class="site-footer shell">
  <div>
    <strong>Forest City News</strong>
    <span>Local reporting from across London, Ontario</span>
  </div>
  <span>Times shown in London, Ontario</span>
</footer>

<AppNavigation {currentPath} />

<style>
  .reader-back { flex: 0 0 44px; margin-right: 8px; }
  .brand-area { display: flex; align-items: center; min-width: 0; }
  .brand::after,
  .brand > span::after {
    content: none !important;
    display: none !important;
  }

  .brand-news {
    gap: 8px !important;
    font-size: 28px !important;
    line-height: 1 !important;
    font-weight: 800 !important;
    letter-spacing: -0.045em !important;
  }

  .brand-news-icon {
    flex: 0 0 auto;
    font-size: 34px !important;
    line-height: 1 !important;
  }

  .brand-news-wordmark {
    display: inline-block;
    transform: translateY(-1px);
  }

  .brand-story-source {
    max-width: min(72vw, 320px);
    overflow: hidden;
  }

  .brand-story-source-logo {
    width: auto !important;
    height: auto !important;
    max-width: min(68vw, 280px) !important;
    max-height: 42px !important;
    object-fit: contain !important;
    object-position: left center !important;
    filter: grayscale(1) brightness(0);
  }

  :global(html[data-theme='dark']) .brand-story-source-logo {
    filter: grayscale(1) brightness(0) invert(1);
  }

  .brand-story-source-name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--ink);
    font-size: 22px !important;
    font-weight: 800;
    letter-spacing: -0.035em;
  }

  .story-cover-secondary-meta {
    position: absolute;
    z-index: 65;
    top: calc(100svh - 78px);
    left: 50%;
    width: min(calc(100% - 64px), var(--content));
    display: grid;
    gap: 2px;
    color: var(--muted);
    font-size: 15px;
    line-height: 1.35;
    opacity: 0;
    visibility: hidden;
    transform: translate(-50%, 8px);
    filter: blur(3px);
    pointer-events: none;
    transition:
      opacity 220ms ease,
      transform 320ms cubic-bezier(.2,.8,.2,1),
      filter 240ms ease,
      visibility 0s linear 240ms;
  }

  .story-cover-secondary-meta.visible {
    opacity: 1;
    visibility: visible;
    transform: translate(-50%, 0);
    filter: blur(0);
    transition-delay: 0s;
  }

  .story-cover-secondary-meta time,
  .story-cover-secondary-meta span {
    font-size: 15px !important;
  }


  :global(body:has(.svelte-article-page) .article-cover-source) {
    visibility: visible !important;
  }

  :global(body:has(.svelte-article-page) .article-cover-source > img),
  :global(body:has(.svelte-article-page) .article-cover-source > strong:not(.story-hero-author)) {
    display: none !important;
  }

  :global(body:has(.svelte-article-page) .story-hero-author) {
    display: block !important;
    color: var(--ink) !important;
    font-size: 16px !important;
    font-weight: 750 !important;
    line-height: 1.25 !important;
  }

  :global(body:has(.svelte-article-page) .article-after-cover) {
    position: relative !important;
    padding-top: 20px !important;
  }

  :global(body:has(.svelte-article-page) .article-content-layout) {
    display: block !important;
    width: min(100%, 760px) !important;
    margin-inline: auto !important;
  }

  :global(body:has(.svelte-article-page) .article-reader) {
    width: 100% !important;
  }

  :global(body:has(.svelte-article-page) .article-source-panel) {
    display: none !important;
  }

  :global(body:has(.svelte-article-page) .source-coverage),
  :global(body:has(.svelte-article-page) .source-card-tags) {
    display: none !important;
  }

  @media (max-width: 760px) {
    .brand-news {
      gap: 7px !important;
      font-size: 26px !important;
    }

    .brand-news-icon {
      font-size: 32px !important;
    }

    .brand-story-source {
      max-width: 78vw;
    }

    .brand-story-source-logo {
      max-width: 72vw !important;
      max-height: 38px !important;
    }

    .brand-story-source-name {
      max-width: 72vw;
      font-size: 20px !important;
    }

    .story-cover-secondary-meta {
      top: calc(88svh - 72px);
      width: min(calc(100% - 28px), var(--content));
      gap: 1px;
      font-size: 14px;
    }

    .story-cover-secondary-meta time,
    .story-cover-secondary-meta span {
      font-size: 14px !important;
    }

    :global(body:has(.svelte-article-page) .article-cover) {
      min-height: 88svh !important;
      height: 88svh !important;
    }

    :global(body:has(.svelte-article-page) .article-cover-content) {
      padding-bottom: max(92px, calc(72px + env(safe-area-inset-bottom))) !important;
    }

    :global(body:has(.svelte-article-page) .article-after-cover) {
      padding-top: 18px !important;
    }

  }

  @media (prefers-reduced-motion: reduce) {
    .story-cover-secondary-meta { transition: none !important; }
  }
</style>
