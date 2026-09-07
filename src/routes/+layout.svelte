<script>
  import { onMount } from 'svelte';
  import { onNavigate } from '$app/navigation';
  import { page } from '$app/stores';
  import { base } from '$app/paths';
  import { initialiseAppState, userState } from '$lib/appState';

  import '../styles/global.css';
  import '../styles/article-rich.css';
  import '../styles/editorial-home.css';
  import '../styles/feed-scope.css';
  import '../styles/mobile-card-fixes.css';
  import '../styles/polish.css';
  import '../styles/svelte-app.css';

  const tabs = [
    { href: `${base}/`, label: 'Home', icon: 'house' },
    { href: `${base}/sections/`, label: 'Sections', icon: 'squares-four' },
    { href: `${base}/search/`, label: 'Search', icon: 'magnifying-glass' },
    { href: `${base}/read-later/`, label: 'Read Later', icon: 'bookmark-simple' },
    { href: `${base}/settings/`, label: 'Settings', icon: 'gear-six' }
  ];

  function normalizedPath(pathname = '') {
    const withoutBase = base && pathname.startsWith(base) ? pathname.slice(base.length) : pathname;
    return withoutBase || '/';
  }

  function isActive(href) {
    const current = normalizedPath($page.url.pathname);
    const target = normalizedPath(href);
    if (target === '/') return current === '/' || current.startsWith('/story/');
    return current.startsWith(target);
  }

  onNavigate((navigation) => {
    if (typeof document === 'undefined' || !document.startViewTransition) return;
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    return new Promise((resolve) => {
      document.startViewTransition(async () => {
        resolve();
        await navigation.complete;
      });
    });
  });

  onMount(() => {
    initialiseAppState().catch(() => {});

    const unsubscribe = userState.subscribe((state) => {
      const root = document.documentElement;
      root.dataset.theme = state.theme || 'light';
      root.dataset.accent = state.accent || 'green';
      root.dataset.hideRead = state.hideRead ? 'true' : 'false';
    });

    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register(`${base}/sw.js`).catch(() => {});
    }

    return () => {
      unsubscribe();
    };
  });
</script>

<svelte:head>
  <title>Forest City News</title>
  <meta name="description" content="Local news from London, Ontario, plus important stories from across Canada." />
</svelte:head>

<div class="app-shell">
  <a class="skip-link" href="#main-content">Skip to content</a>

  <header class="site-header app-header">
    <div class="site-header-inner shell">
      <a class="site-brand" href={`${base}/`} data-sveltekit-preload-data="tap" aria-label="Forest City News home">
        <span class="brand-mark" aria-hidden="true"><i class="ph-fill ph-tree"></i></span>
        <span class="brand-copy">
          <strong>Forest City</strong>
          <span>News</span>
        </span>
      </a>

      <nav class="header-actions" aria-label="Quick links">
        <a href={`${base}/search/`} data-sveltekit-preload-data="tap" aria-label="Search">
          <i class="ph ph-magnifying-glass" aria-hidden="true"></i>
        </a>
        <a href={`${base}/sections/`} data-sveltekit-preload-data="tap" aria-label="Sections">
          <i class="ph ph-squares-four" aria-hidden="true"></i>
        </a>
        <a href={`${base}/settings/`} data-sveltekit-preload-data="tap" aria-label="Settings">
          <i class="ph ph-gear-six" aria-hidden="true"></i>
        </a>
      </nav>
    </div>
  </header>

  <div class="app-route-stage">
    <slot />
  </div>

  <footer class="site-footer">
    <div class="shell app-footer-inner">
      <span>Forest City News</span>
      <span>London, Ontario</span>
    </div>
  </footer>

  <nav class="mobile-tab-bar app-tab-bar" aria-label="Primary">
    <div class="app-tab-bar-inner">
      {#each tabs as tab}
        <a
          href={tab.href}
          class:active={isActive(tab.href)}
          class="app-tab"
          data-sveltekit-preload-data="tap"
          aria-current={isActive(tab.href) ? 'page' : undefined}
        >
          <span class="app-tab-icon">
            <i class={isActive(tab.href) ? `ph-fill ph-${tab.icon}` : `ph ph-${tab.icon}`} aria-hidden="true"></i>
          </span>
          <span>{tab.label}</span>
        </a>
      {/each}
    </div>
  </nav>
</div>
