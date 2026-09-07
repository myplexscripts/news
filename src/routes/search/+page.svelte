<script>
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import NewsCard from '$lib/components/NewsCard.svelte';
  import { loadFeed, sortNewest } from '$lib/newsData';
  import { userState } from '$lib/appState';

  let feed;
  let error = '';
  let query = '';

  onMount(async () => {
    query = $page.url.searchParams.get('q') || '';
    try {
      feed = await loadFeed();
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Unable to load search.';
    }
  });

  $: normalized = query.trim().toLowerCase();
  $: hiddenSources = new Set($userState.hiddenSources.map((value) => value.toLowerCase()));
  $: readIds = new Set($userState.readIds);

  $: results = !feed || normalized.length < 2
    ? []
    : sortNewest(feed.stories || []).filter((story) => {
        if (hiddenSources.has(String(story.source || '').toLowerCase())) return false;
        if ($userState.hideRead && readIds.has(String(story.id))) return false;
        const haystack = [
          story.title,
          story.summary,
          story.source,
          story.category
        ].map((value) => String(value || '').toLowerCase()).join(' ');
        return normalized.split(/\s+/).every((term) => haystack.includes(term));
      }).slice(0, 80);

  function syncUrl() {
    const url = new URL(window.location.href);
    if (query.trim()) url.searchParams.set('q', query.trim());
    else url.searchParams.delete('q');
    history.replaceState(history.state, '', url);
  }
</script>

<svelte:head>
  <title>Search | Forest City News</title>
  <meta name="description" content="Search Forest City News." />
</svelte:head>

<main class="app-page" id="main-content">
  <section class="shell">
    <header class="app-page-heading">
      <p class="eyebrow">Find stories</p>
      <h1>Search</h1>
      <p>Search headlines, summaries, publishers and sections.</p>
    </header>

    <label class="app-search-field">
      <i class="ph ph-magnifying-glass" aria-hidden="true"></i>
      <input
        type="search"
        bind:value={query}
        on:input={syncUrl}
        placeholder="Search Forest City News"
        autocomplete="off"
        autocapitalize="off"
        spellcheck="false"
      />
    </label>

    {#if error}
      <div class="app-error search-state">{error}</div>
    {:else if !feed}
      <div class="app-loading-grid search-state">
        <div class="app-skeleton"></div>
        <div class="app-skeleton"></div>
        <div class="app-skeleton"></div>
      </div>
    {:else if normalized.length < 2}
      <div class="app-empty search-state">Type at least two characters to search.</div>
    {:else if results.length === 0}
      <div class="app-empty search-state">No stories found for “{query.trim()}”.</div>
    {:else}
      <div class="app-section-heading">
        <div>
          <p class="eyebrow">Results</p>
          <h2>{results.length} {results.length === 1 ? 'story' : 'stories'}</h2>
        </div>
      </div>
      <div class="app-story-grid">
        {#each results as story (story.id)}
          <NewsCard {story} />
        {/each}
      </div>
    {/if}
  </section>
</main>

<style>
  .search-state {
    margin-top: 26px;
  }
</style>
