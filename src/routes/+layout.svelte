<script>
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { base } from '$app/paths';
  import { initialiseAppState, userState } from '$lib/appState';
  import { loadFeed } from '$lib/newsData';
  import Icon from '$lib/components/Icon.svelte';

  import '../styles/global.css';
  import '../styles/article-rich.css';
  import '../styles/editorial-home.css';
  import '../styles/feed-scope.css';
  import '../styles/mobile-card-fixes.css';
  import '../styles/polish.css';
  import '../styles/svelte-app.css';

  let homeDate = formatHomeDate(new Date());
  let homeUpdated = '';
  let isBackToTop = false;

  function normalizedPath(pathname = '') {
    const withoutBase = base && pathname.startsWith(base) ? pathname.slice(base.length) : pathname;
    return withoutBase || '/';
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

  $: currentPath = normalizedPath($page.url.pathname);
  $: onHome = currentPath === '/';
  $: onStory = currentPath.startsWith('/story/');
  $: onDirectory = currentPath.startsWith('/sections/') || currentPath.startsWith('/sources/');
  $: onSearch = currentPath.startsWith('/search/');
  $: onReadLater = currentPath.startsWith('/read-later/');
  $: onSettings = currentPath.startsWith('/settings/');
  $: activeIndex = onHome || onStory ? 0 : onDirectory ? 1 : onSearch ? 2 : onReadLater ? 3 : onSettings ? 4 : 0;
  $: if (!onHome) isBackToTop = false;

  function handleHomeTab(event) {
    if (!onHome || !isBackToTop) return;
    event.preventDefault();
    const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
    window.scrollTo({ top: 0, behavior: reduced ? 'auto' : 'smooth' });
  }

  onMount(() => {
    initialiseAppState().catch(() => {});

    loadFeed().then((feed) => {
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

    const syncHomeAction = () => {
      if (!onHome) {
        isBackToTop = false;
        return;
      }
      const threshold = Math.min(420, Math.max(240, window.innerHeight * 0.38));
      isBackToTop = window.scrollY > threshold;
    };

    window.addEventListener('scroll', syncHomeAction, { passive: true });
    window.addEventListener('resize', syncHomeAction, { passive: true });
    syncHomeAction();

    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register(`${base}/sw.js`).then((registration) => registration.update()).catch(() => {});
    }

    return () => {
      unsubscribe();
      window.removeEventListener('scroll', syncHomeAction);
      window.removeEventListener('resize', syncHomeAction);
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
      <a class="brand brand-news" href={`${base}/`} data-sveltekit-preload-data="tap" aria-label="Forest City News home">
        <Icon name="tree" size={34} strokeWidth={2.25} className="brand-news-icon" />
        <span class="brand-news-wordmark">News</span>
      </a>
    </div>

    <div class="header-actions">
      <a class="icon-button header-search-link" href={`${base}/search/`} data-sveltekit-preload-data="tap" aria-label="Search news" title="Search">
        <Icon name="search" size={22} />
      </a>
      <a class:active={onDirectory} class="icon-button desktop-sources-link" href={`${base}/sections/`} data-sveltekit-preload-data="tap" aria-label="Browse sections and sources" title="Sections" aria-current={onDirectory ? 'page' : undefined}>
        <Icon name="grid" size={22} strokeWidth={onDirectory ? 2.5 : 2} />
      </a>
      <a class:active={onSettings} class="icon-button settings-link" href={`${base}/settings/`} data-sveltekit-preload-data="tap" aria-label="Settings" title="Settings" aria-current={onSettings ? 'page' : undefined}>
        <Icon name="settings" size={22} strokeWidth={onSettings ? 2.5 : 2} />
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

<div class="svelte-route-stage">
  <slot />
</div>

<footer class="site-footer shell">
  <div>
    <strong>Forest City News</strong>
    <span>Local reporting from across London, Ontario</span>
  </div>
  <span>Times shown in London, Ontario</span>
</footer>

<nav
  class="mobile-tab-bar svelte-mobile-tab-bar"
  aria-label="Primary navigation"
  data-active-index={String(activeIndex)}
  style={`--indicator-index:${activeIndex};--mobile-tab-count:5;`}
>
  <span class="mobile-tab-indicator" aria-hidden="true"></span>

  <a
    class:active={onHome || onStory}
    class:is-back-to-top={onHome && isBackToTop}
    class="mobile-tab mobile-home-tab"
    href={`${base}/`}
    data-sveltekit-preload-data="tap"
    aria-label={onHome && isBackToTop ? 'Back to top' : 'Home'}
    title={onHome && isBackToTop ? 'Back to top' : 'Home'}
    aria-current={onHome ? 'page' : undefined}
    on:click={handleHomeTab}
  >
    <Icon name={onHome && isBackToTop ? 'arrow-up' : 'house'} size={24} strokeWidth={onHome || onStory ? 2.5 : 2} />
    <span class="visually-hidden">Home</span>
  </a>

  <a class:active={onDirectory} class="mobile-tab" href={`${base}/sections/`} data-sveltekit-preload-data="tap" aria-label="Sections" title="Sections" aria-current={onDirectory ? 'page' : undefined}>
    <Icon name="grid" size={24} strokeWidth={onDirectory ? 2.5 : 2} />
    <span class="visually-hidden">Sections</span>
  </a>

  <a class:active={onSearch} class="mobile-tab" href={`${base}/search/`} data-sveltekit-preload-data="tap" aria-label="Search" title="Search" aria-current={onSearch ? 'page' : undefined}>
    <Icon name="search" size={24} strokeWidth={onSearch ? 2.5 : 2} />
    <span class="visually-hidden">Search</span>
  </a>

  <a class:active={onReadLater} class="mobile-tab" href={`${base}/read-later/`} data-sveltekit-preload-data="tap" aria-label="Read Later" title="Read Later" aria-current={onReadLater ? 'page' : undefined}>
    <Icon name="bookmark" size={24} strokeWidth={onReadLater ? 2.5 : 2} />
    <span class="visually-hidden">Read Later</span>
  </a>

  <a class:active={onSettings} class="mobile-tab" href={`${base}/settings/`} data-sveltekit-preload-data="tap" aria-label="Settings" title="Settings" aria-current={onSettings ? 'page' : undefined}>
    <Icon name="settings" size={24} strokeWidth={onSettings ? 2.5 : 2} />
    <span class="visually-hidden">Settings</span>
  </a>
</nav>

<style>
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

  :global(.brand-news-icon) {
    flex: 0 0 auto;
    width: 34px !important;
    height: 34px !important;
  }

  .brand-news-wordmark {
    display: inline-block;
    transform: translateY(-1px);
  }

  :global(.mobile-tab .lucide-icon) {
    transition: transform 160ms ease;
  }

  .mobile-tab:active :global(.lucide-icon) {
    transform: scale(0.92);
  }

  @media (max-width: 760px) {
    .brand-news {
      gap: 7px !important;
      font-size: 26px !important;
    }

    :global(.brand-news-icon) {
      width: 32px !important;
      height: 32px !important;
    }

    :global(.svelte-mobile-tab-bar) {
      --mobile-tab-count: 5 !important;
      grid-template-columns: repeat(5, minmax(0, 1fr)) !important;
    }

    :global(.svelte-mobile-tab-bar > .mobile-tab:nth-of-type(1)) { grid-column: 1 !important; }
    :global(.svelte-mobile-tab-bar > .mobile-tab:nth-of-type(2)) { grid-column: 2 !important; }
    :global(.svelte-mobile-tab-bar > .mobile-tab:nth-of-type(3)) { grid-column: 3 !important; }
    :global(.svelte-mobile-tab-bar > .mobile-tab:nth-of-type(4)) { grid-column: 4 !important; }
    :global(.svelte-mobile-tab-bar > .mobile-tab:nth-of-type(5)) { grid-column: 5 !important; }
  }
</style>
