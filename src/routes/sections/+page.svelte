<script>
  import { onMount } from 'svelte';
  import { base } from '$app/paths';
  import { loadFeed } from '$lib/newsData';
  import { setHiddenSource, revealAllSources, userState } from '$lib/appState';

  let feed;
  let error = '';

  onMount(async () => {
    try {
      feed = await loadFeed();
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Unable to load sections.';
    }
  });

  $: categories = feed
    ? [...new Set((feed.stories || []).map((story) => story.category).filter(Boolean))]
        .map((name) => ({
          name,
          count: feed.stories.filter((story) => story.category === name).length
        }))
        .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name))
    : [];

  $: sources = feed
    ? [...new Set((feed.stories || []).map((story) => story.source).filter(Boolean))]
        .map((name) => ({
          name,
          count: feed.stories.filter((story) => story.source === name).length,
          hidden: $userState.hiddenSources.includes(name)
        }))
        .sort((a, b) => a.name.localeCompare(b.name))
    : [];

  async function toggleSource(source) {
    await setHiddenSource(source.name, !source.hidden).catch(() => {});
  }
</script>

<svelte:head>
  <title>Sections | Forest City News</title>
  <meta name="description" content="Browse Forest City News sections and publishers." />
</svelte:head>

<main class="app-page" id="main-content">
  <section class="shell">
    <header class="app-page-heading">
      <p class="eyebrow">Browse</p>
      <h1>Sections</h1>
      <p>Jump into a topic or choose which publishers appear in your feed.</p>
    </header>

    {#if error}
      <div class="app-error">{error}</div>
    {:else if !feed}
      <div class="app-loading-grid">
        <div class="app-skeleton"></div>
        <div class="app-skeleton"></div>
        <div class="app-skeleton"></div>
      </div>
    {:else}
      <section aria-labelledby="topics-heading">
        <div class="app-section-heading">
          <div>
            <p class="eyebrow">Topics</p>
            <h2 id="topics-heading">News sections</h2>
          </div>
        </div>

        <div class="directory-grid">
          {#each categories as category}
            <a class="directory-card" href={`${base}/?section=${encodeURIComponent(category.name)}#latest`}>
              <span>
                <strong>{category.name}</strong>
                <small>{category.count} stories</small>
              </span>
              <i class="ph ph-arrow-right" aria-hidden="true"></i>
            </a>
          {/each}
        </div>
      </section>

      <section aria-labelledby="sources-heading">
        <div class="app-section-heading">
          <div>
            <p class="eyebrow">Publishers</p>
            <h2 id="sources-heading">Sources</h2>
          </div>
          {#if $userState.hiddenSources.length}
            <button class="section-text-action" type="button" on:click={() => revealAllSources().catch(() => {})}>Show all</button>
          {/if}
        </div>

        <div class="source-list">
          {#each sources as source}
            <button class:hidden={source.hidden} class="source-row" type="button" on:click={() => toggleSource(source)}>
              <span>
                <strong>{source.name}</strong>
                <small>{source.count} stories</small>
              </span>
              <span class="source-state">{source.hidden ? 'Hidden' : 'Shown'}</span>
            </button>
          {/each}
        </div>
      </section>
    {/if}
  </section>
</main>

<style>
  .directory-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 12px;
  }

  .directory-card,
  .source-row {
    box-sizing: border-box;
    min-height: 86px;
    border: 0;
    border-radius: 16px;
    padding: 18px;
    background: var(--surface-subtle);
    color: var(--text);
    text-decoration: none;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 18px;
    text-align: left;
  }

  .directory-card strong,
  .source-row strong {
    display: block;
    font-size: 16px;
    letter-spacing: -.02em;
  }

  .directory-card small,
  .source-row small {
    display: block;
    margin-top: 4px;
    color: var(--text-tertiary);
    font-size: 12px;
  }

  .directory-card:active,
  .source-row:active {
    transform: scale(.99);
  }

  .source-list {
    display: grid;
    gap: 8px;
  }

  .source-row {
    width: 100%;
    min-height: 66px;
    cursor: pointer;
  }

  .source-row.hidden {
    opacity: .58;
  }

  .source-state,
  .section-text-action {
    color: var(--accent, #34c759);
    font-size: 13px;
    font-weight: 700;
  }

  .section-text-action {
    border: 0;
    background: none;
    cursor: pointer;
  }

  @media (max-width: 760px) {
    .directory-grid {
      grid-template-columns: 1fr 1fr;
    }
  }

  @media (max-width: 460px) {
    .directory-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
