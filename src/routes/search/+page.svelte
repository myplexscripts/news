<script>
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import Icon from '$lib/components/Icon.svelte';
  import { loadFeed, resolveAsset, scopeForStory, sortNewest, storyHref } from '$lib/newsData';
  import { userState } from '$lib/appState';

  let feed;
  let error = '';
  let query = '';
  let activeScope = 'all';
  let activeCategory = '';
  let activeSource = '';
  let activeDays = '';

  onMount(async () => {
    query = $page.url.searchParams.get('q') || '';
    try {
      feed = await loadFeed();
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Unable to load search.';
    }
  });

  function syncUrl() {
    const url = new URL(window.location.href);
    if (query.trim()) url.searchParams.set('q', query.trim());
    else url.searchParams.delete('q');
    history.replaceState(history.state, '', url);
  }

  function clearSearch() {
    query = '';
    syncUrl();
  }

  function formatDate(value) {
    try {
      return new Intl.DateTimeFormat('en-CA', {
        timeZone: 'America/Toronto',
        month: 'short',
        day: 'numeric',
        year: 'numeric'
      }).format(new Date(value));
    } catch {
      return '';
    }
  }

  $: normalized = query.trim().toLowerCase();
  $: sourceHealth = feed?.source_health || [];
  $: hiddenSources = new Set(($userState.hiddenSources || []).map((value) => String(value).toLowerCase()));
  $: readIds = new Set(($userState.readIds || []).map(String));
  $: categories = [...new Set((feed?.stories || []).map((story) => story.category).filter(Boolean))].sort();
  $: sources = [...new Set((feed?.stories || []).map((story) => story.source).filter(Boolean))].sort();
  $: cutoff = Number(activeDays || 0) > 0 ? Date.now() - Number(activeDays) * 86400000 : 0;

  $: results = !feed || normalized.length < 2
    ? []
    : sortNewest(feed.stories || []).filter((story) => {
        const source = String(story.source || '');
        if (hiddenSources.has(source.toLowerCase())) return false;
        if ($userState.hideRead && readIds.has(String(story.id))) return false;
        if (activeScope !== 'all' && scopeForStory(story, sourceHealth) !== activeScope) return false;
        if (activeCategory && story.category !== activeCategory) return false;
        if (activeSource && source !== activeSource) return false;
        if (cutoff) {
          const published = new Date(story.cluster_latest_published || story.published || 0).getTime();
          if (!Number.isFinite(published) || published < cutoff) return false;
        }

        const haystack = [story.title, story.summary, story.source, story.category, ...(story.story_topics || [])]
          .map((value) => String(value || '').toLowerCase())
          .join(' ');
        return normalized.split(/\s+/).every((term) => haystack.includes(term));
      }).slice(0, 80);
</script>

<svelte:head>
  <title>Search | Forest City News</title>
  <meta name="description" content="Search Forest City News stories." />
</svelte:head>

<main class="directory-page search-page" id="main-content">
  <section class="directory-shell shell">
    <header class="page-heading directory-heading">
      <div class="page-heading-copy">
        <p class="masthead-label">Find stories</p>
        <h1>Search</h1>
        <p class="page-heading-description">Search headlines, publishers and topics across Forest City News.</p>
      </div>
    </header>

    <div class="search-page-field search-page-field-refined">
      <Icon name="search" size={20} />
      <input
        id="archiveSearch"
        type="search"
        bind:value={query}
        on:input={syncUrl}
        placeholder="Search Forest City News"
        autocomplete="off"
        autocapitalize="off"
        spellcheck="false"
        aria-label="Search Forest City News"
      />
      {#if query}
        <button class="search-clear-button" type="button" aria-label="Clear search" on:click={clearSearch}>
          <Icon name="circle-x" size={20} />
        </button>
      {/if}
    </div>

    <div class="archive-search-controls" aria-label="Search filters">
      <div class="archive-scope-switch" role="group" aria-label="Search feed">
        <button class:active={activeScope === 'all'} type="button" aria-pressed={activeScope === 'all'} on:click={() => activeScope = 'all'}>All</button>
        <button class:active={activeScope === 'local'} type="button" aria-pressed={activeScope === 'local'} on:click={() => activeScope = 'local'}>Local</button>
        <button class:active={activeScope === 'canada'} type="button" aria-pressed={activeScope === 'canada'} on:click={() => activeScope = 'canada'}>Canada</button>
      </div>

      <label>
        <span>Section</span>
        <select bind:value={activeCategory}>
          <option value="">All sections</option>
          {#each categories as category}<option value={category}>{category}</option>{/each}
        </select>
      </label>

      <label>
        <span>Source</span>
        <select bind:value={activeSource}>
          <option value="">All sources</option>
          {#each sources as source}<option value={source}>{source}</option>{/each}
        </select>
      </label>

      <label>
        <span>Date</span>
        <select bind:value={activeDays}>
          <option value="">Any time</option>
          <option value="1">Past 24 hours</option>
          <option value="7">Past 7 days</option>
          <option value="30">Past 30 days</option>
          <option value="365">Past year</option>
        </select>
      </label>
    </div>

    {#if error}
      <p class="search-result-status app-error">{error}</p>
    {:else if !feed}
      <p class="search-result-status" aria-live="polite">Loading search index.</p>
    {:else if normalized.length < 2}
      <p class="search-result-status" aria-live="polite">{normalized.length ? 'Type at least 2 characters.' : 'Start typing to search.'}</p>
    {:else}
      <p class="search-result-status" aria-live="polite">
        {results.length ? `${results.length} ${results.length === 1 ? 'result' : 'results'}` : 'No matching stories.'}
      </p>

      {#if results.length}
        <div class="archive-search-results">
          {#each results as story (story.id)}
            <article class="archive-search-hit">
              {#if story.card_image_small || story.card_image || story.image}
                <a class="archive-search-hit-image" href={storyHref(story.id)} data-sveltekit-preload-data="tap" tabindex="-1">
                  <img src={resolveAsset(story.card_image_small || story.card_image || story.image)} alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer" />
                </a>
              {/if}

              <div class="archive-search-hit-body">
                <div class="archive-search-hit-meta">
                  <span>{story.source || 'Unknown source'}</span>
                  {#if story.category}<span>{story.category}</span>{/if}
                </div>

                <h2><a href={storyHref(story.id)} data-sveltekit-preload-data="tap">{story.title}</a></h2>
                {#if story.summary}<p>{story.summary}</p>{/if}

                <div class="archive-search-hit-footer">
                  <time datetime={story.cluster_latest_published || story.published}>{formatDate(story.cluster_latest_published || story.published)}</time>
                  {#if Number(story.word_count) > 0}<span>{Math.max(1, Math.round(Number(story.word_count) / 220))} min read</span>{/if}
                </div>
              </div>
            </article>
          {/each}
        </div>
      {/if}
    {/if}
  </section>
</main>

<style>
  .archive-search-controls {
    display: grid;
    grid-template-columns: auto repeat(3, minmax(150px, 1fr));
    gap: 12px;
    align-items: end;
    margin: 18px 0 12px;
  }

  .archive-search-controls label {
    display: grid;
    gap: 6px;
    color: var(--muted);
    font-size: 16px;
    font-weight: 600;
  }

  .archive-search-controls select {
    min-height: 44px;
    width: 100%;
    border: 1px solid var(--line);
    border-radius: 14px;
    background: var(--surface);
    color: var(--text);
    padding: 0 38px 0 12px;
    font: inherit;
    font-size: 16px;
  }

  .archive-scope-switch {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    padding: 4px;
    min-height: 44px;
    border: 1px solid var(--line);
    border-radius: 16px;
    background: var(--surface);
  }

  .archive-scope-switch button {
    min-width: 68px;
    min-height: 36px;
    border: 0;
    border-radius: 12px;
    background: transparent;
    color: var(--muted);
    font: inherit;
    font-size: 16px;
    font-weight: 700;
    cursor: pointer;
  }

  .archive-scope-switch button.active {
    background: var(--accent-soft);
    color: var(--accent-ink);
  }

  .archive-search-results {
    display: grid;
    gap: 0;
    margin-top: 16px;
    border-top: 1px solid var(--line);
  }

  .archive-search-hit {
    display: grid;
    grid-template-columns: 180px minmax(0, 1fr);
    gap: 22px;
    padding: 22px 0;
    border-bottom: 1px solid var(--line);
  }

  .archive-search-hit-image {
    display: block;
    aspect-ratio: 4 / 3;
    overflow: hidden;
    border-radius: 16px;
    background: var(--surface-2);
  }

  .archive-search-hit-image img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .archive-search-hit-body {
    min-width: 0;
    display: flex;
    flex-direction: column;
    justify-content: center;
  }

  .archive-search-hit-meta,
  .archive-search-hit-footer {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    color: var(--muted);
    font-size: 16px;
  }

  .archive-search-hit-meta span + span::before,
  .archive-search-hit-footer > * + *::before {
    content: '·';
    margin-right: 10px;
  }

  .archive-search-hit h2 {
    margin: 7px 0 6px;
    font-size: clamp(20px, 2vw, 28px);
    line-height: 1.12;
  }

  .archive-search-hit h2 a {
    color: var(--text);
    text-decoration: none;
  }

  .archive-search-hit h2 a:hover {
    color: var(--accent);
  }

  .archive-search-hit p {
    margin: 0 0 10px;
    color: var(--muted);
    line-height: 1.45;
  }

  .search-result-status {
    margin: 14px 0 0;
    color: var(--muted);
    font-size: 16px;
    font-weight: 600;
  }

  @media (max-width: 900px) {
    .archive-search-controls {
      grid-template-columns: 1fr 1fr;
    }
  }

  @media (max-width: 760px) {
    .archive-search-controls {
      grid-template-columns: 1fr;
      margin-top: 14px;
    }

    .archive-search-hit {
      grid-template-columns: 112px minmax(0, 1fr);
      gap: 14px;
      padding: 16px 0;
    }

    .archive-search-hit h2 {
      font-size: 19px;
    }

    .archive-search-hit p {
      display: none;
    }

    .archive-search-hit-meta,
    .archive-search-hit-footer {
      font-size: 14px;
    }
  }
</style>
