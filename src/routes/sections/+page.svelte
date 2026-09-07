<script>
  import { onMount } from 'svelte';
  import { base } from '$app/paths';
  import { loadFeed } from '$lib/newsData';
  import { setHiddenSource, revealAllSources, userState } from '$lib/appState';
  import { sourceLogoPath } from '$lib/sourceLogos';

  const preferredOrder = ['Local', 'Public Safety', 'City Hall', 'Business', 'Traffic', 'Education', 'Health', 'Community', 'Sports'];
  const iconFor = (category) => ({
    'Local': 'ph-map-pin',
    'Public Safety': 'ph-shield-check',
    'City Hall': 'ph-buildings',
    'Business': 'ph-briefcase',
    'Traffic': 'ph-car',
    'Education': 'ph-graduation-cap',
    'Health': 'ph-heartbeat',
    'Community': 'ph-users-three',
    'Sports': 'ph-trophy'
  }[category] || 'ph-newspaper-clipping');

  let feed;
  let error = '';
  let activeTab = 'sections';

  onMount(async () => {
    activeTab = new URL(window.location.href).searchParams.get('tab') === 'sources' ? 'sources' : 'sections';
    try {
      feed = await loadFeed();
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Unable to load sections.';
    }
  });

  function setTab(tab) {
    activeTab = tab === 'sources' ? 'sources' : 'sections';
    const url = new URL(window.location.href);
    if (activeTab === 'sources') url.searchParams.set('tab', 'sources');
    else url.searchParams.delete('tab');
    history.replaceState(history.state, '', url);
  }

  function categoryClass(category = 'Local') {
    return `category-${String(category).toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;
  }

  function latestDate(value) {
    try {
      return new Intl.DateTimeFormat('en-CA', {
        timeZone: 'America/Toronto',
        month: 'short',
        day: 'numeric'
      }).format(new Date(value));
    } catch {
      return '';
    }
  }

  $: stories = (feed?.stories || []).filter((story) => story?.cluster_representative !== false);
  $: discovered = [...new Set(stories.map((story) => story.category).filter(Boolean))];
  $: categories = [
    ...preferredOrder.filter((category) => discovered.includes(category)),
    ...discovered.filter((category) => !preferredOrder.includes(category)).sort()
  ];
  $: healthBySource = new Map((feed?.source_health || []).map((item) => [String(item.source || ''), item]));
  $: sourceNames = [...new Set((feed?.stories || []).map((story) => story.source).filter(Boolean))].sort((a, b) => a.localeCompare(b));
  $: sources = sourceNames.map((name) => {
    const sourceStories = (feed?.stories || []).filter((story) => story.source === name);
    const latest = sourceStories.reduce((value, story) => {
      const date = story.cluster_latest_published || story.published;
      return !value || new Date(date) > new Date(value) ? date : value;
    }, '');
    const health = healthBySource.get(name) || {};
    return {
      name,
      latest,
      status: health.status || 'waiting',
      logo: sourceLogoPath(name, `${base}/`),
      hidden: $userState.hiddenSources.includes(name)
    };
  });
  $: shownCount = sources.filter((source) => !source.hidden).length;

  async function toggleSource(source, shown) {
    await setHiddenSource(source.name, !shown).catch(() => {});
  }
</script>

<svelte:head>
  <title>Sections | Forest City News</title>
  <meta name="description" content="Browse Forest City News by section or choose which sources appear in your feed." />
</svelte:head>

<main class="sections-page combined-directory-page" id="main-content">
  <section class="sections-shell shell">
    <header class="page-heading sections-heading">
      <div class="page-heading-copy">
        <p class="masthead-label">Browse</p>
        <h1>Sections</h1>
        <p class="page-heading-description">Browse by topic or choose which publishers appear in your feed.</p>
      </div>
    </header>

    {#if error}
      <div class="app-error">{error}</div>
    {:else if !feed}
      <div class="app-loading-grid embedded-loading">
        <div class="app-skeleton"></div>
        <div class="app-skeleton"></div>
        <div class="app-skeleton"></div>
      </div>
    {:else}
      <div class="directory-tabs" role="tablist" aria-label="Browse Forest City News">
        <button class:active={activeTab === 'sections'} class="directory-tab" type="button" role="tab" aria-selected={activeTab === 'sections'} on:click={() => setTab('sections')}>Sections</button>
        <button class:active={activeTab === 'sources'} class="directory-tab" type="button" role="tab" aria-selected={activeTab === 'sources'} on:click={() => setTab('sources')}>Sources</button>
      </div>

      {#if activeTab === 'sections'}
        <section class="directory-panel" aria-label="News sections">
          <div class="section-directory-grid">
            <a class="section-directory-card section-all" href={`${base}/latest/`} data-sveltekit-preload-data="tap">
              <span class="section-directory-icon"><i class="ph ph-clock-countdown" aria-hidden="true"></i></span>
              <div><strong>Latest</strong></div>
              <i class="ph ph-caret-right" aria-hidden="true"></i>
            </a>

            {#each categories as category}
              <a class={`section-directory-card ${categoryClass(category)}`} href={`${base}/?section=${encodeURIComponent(category)}#latest`} data-sveltekit-preload-data="tap">
                <span class="section-directory-icon"><i class={`ph ${iconFor(category)}`} aria-hidden="true"></i></span>
                <div><strong>{category}</strong></div>
                <i class="ph ph-caret-right" aria-hidden="true"></i>
              </a>
            {/each}
          </div>
        </section>
      {:else}
        <section class="directory-panel" aria-label="News sources">
          <div class="combined-sources-toolbar">
            <span aria-live="polite">{shownCount} of {sources.length} sources shown</span>
            <button class="bordered-button" type="button" disabled={shownCount === sources.length} on:click={() => revealAllSources().catch(() => {})}>Show all</button>
          </div>

          <div class="source-preference-list">
            {#each sources as source}
              <article class:source-hidden={source.hidden} class="source-preference-card">
                <div class="source-preference-identity">
                  <span class="source-preference-logo-wrap">
                    {#if source.logo}<img class="source-preference-logo" src={source.logo} alt="" loading="lazy" />{/if}
                  </span>
                  <div>
                    <h2>{source.name}</h2>
                    <p>
                      <span class={`source-health-dot source-health-${source.status}`} aria-hidden="true"></span>
                      {source.status === 'healthy' ? 'Healthy' : source.status === 'degraded' ? 'Limited extraction' : source.status === 'error' ? 'Temporarily unavailable' : 'Waiting'}
                      {#if source.latest}<span aria-hidden="true"> · </span>Latest {latestDate(source.latest)}{/if}
                    </p>
                  </div>
                </div>
                <label class="source-switch-row">
                  <span class="visually-hidden">Show {source.name}</span>
                  <input class="source-switch-input" type="checkbox" checked={!source.hidden} on:change={(event) => toggleSource(source, event.currentTarget.checked)} />
                  <span class="source-switch" aria-hidden="true"><span></span></span>
                </label>
              </article>
            {/each}
          </div>

          <div class="sources-footer-note">
            <i class="ph ph-device-mobile" aria-hidden="true"></i>
            <p>These preferences only affect what Forest City News shows you. They do not change what the collector gathers, and they stay on this browser unless you clear its site data.</p>
          </div>
        </section>
      {/if}
    {/if}
  </section>
</main>

<style>
  .embedded-loading {
    width: 100%;
  }

  .combined-directory-page .sections-heading {
    margin-bottom: 20px;
  }

  .directory-tabs {
    width: min(100%, 520px);
    margin: 0 0 28px;
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .section-directory-grid {
    display: flex;
    flex-direction: column;
    gap: 0;
    padding: 0;
    border: 0;
    border-radius: 24px;
    background: var(--gray-6);
    overflow: hidden;
  }

  :global(html[data-theme='dark']) .section-directory-grid {
    background: var(--surface);
  }

  .section-directory-card {
    position: relative;
    width: 100%;
    min-height: 72px;
    box-sizing: border-box;
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 12px 16px;
    border: 0;
    border-radius: 0;
    background: transparent;
    color: var(--ink);
    text-decoration: none;
  }

  .section-directory-card:not(:last-child)::after {
    content: '';
    position: absolute;
    left: 74px;
    right: 0;
    bottom: 0;
    height: 1px;
    background: var(--line);
  }

  .section-directory-icon {
    width: 46px;
    height: 46px;
    min-width: 46px;
    display: grid;
    place-items: center;
    border-radius: 12px;
    background: #fff;
    color: #000;
  }

  .section-directory-icon i {
    color: #000;
    font-size: 25px;
  }

  .section-directory-card > div {
    flex: 1 1 auto;
    min-width: 0;
  }

  .section-directory-card strong {
    display: block;
    color: var(--ink);
    font-size: 18px;
    font-weight: 500;
    line-height: 1.25;
  }

  .section-directory-card > i.ph-caret-right {
    display: none;
  }

  .combined-sources-toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    min-height: 52px;
    margin-bottom: 16px;
    color: var(--muted);
    font-size: 16px;
    font-weight: 600;
  }

  @media (max-width: 760px) {
    .directory-tabs {
      width: 100%;
      margin-bottom: 24px;
    }

    .section-directory-grid {
      border-radius: 22px;
    }

    .section-directory-card {
      min-height: 70px;
      padding: 12px 14px;
      gap: 13px;
    }

    .section-directory-card:not(:last-child)::after {
      left: 72px;
    }

    .section-directory-icon {
      width: 44px;
      height: 44px;
      min-width: 44px;
      border-radius: 11px;
    }

    .section-directory-icon i {
      font-size: 24px;
    }

    .section-directory-card strong {
      font-size: 17px;
    }

    .combined-sources-toolbar {
      margin-bottom: 12px;
    }
  }
</style>
