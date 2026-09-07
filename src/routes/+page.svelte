<script>
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import NewsCard from '$lib/components/NewsCard.svelte';
  import { loadFeed, scopeForStory, sortNewest } from '$lib/newsData';
  import { userState } from '$lib/appState';

  const preferredCategories = [
    'Public Safety',
    'City Hall',
    'Business',
    'Traffic',
    'Education',
    'Health',
    'Community',
    'Sports'
  ];

  let feed;
  let error = '';
  let activeScope = 'local';
  let activeCategory = 'All';

  onMount(async () => {
    try {
      feed = await loadFeed();
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Unable to load the latest news.';
    }
  });

  $: requestedSection = $page.url.searchParams.get('section');
  $: if (requestedSection && requestedSection !== activeCategory) {
    activeCategory = requestedSection;
  }

  $: sourceHealth = feed?.source_health || {};
  $: hiddenSources = new Set($userState.hiddenSources.map((value) => value.toLowerCase()));
  $: readIds = new Set($userState.readIds);

  $: baseStories = feed
    ? sortNewest((feed.stories || []).filter((story) => story?.cluster_representative !== false))
    : [];

  $: categories = [
    'All',
    ...preferredCategories.filter((category) => baseStories.some((story) => story.category === category)),
    ...[...new Set(baseStories.map((story) => story.category).filter(Boolean))]
      .filter((category) => !preferredCategories.includes(category) && !['Local', 'Canada'].includes(category))
      .sort()
  ];

  $: filteredStories = baseStories.filter((story) => {
    const source = String(story.source || '').toLowerCase();
    if (hiddenSources.has(source)) return false;
    if ($userState.hideRead && readIds.has(String(story.id))) return false;

    const storyScope = scopeForStory(story, sourceHealth);
    if (activeScope !== 'all' && storyScope !== activeScope) return false;
    if (activeCategory !== 'All' && story.category !== activeCategory) return false;
    return true;
  });

  $: topStories = filteredStories.slice(0, 3);
  $: timelineStories = filteredStories.slice(3, 63);

  function updatedLabel() {
    if (!feed?.generated_at) return '';
    try {
      return new Intl.DateTimeFormat('en-CA', {
        timeZone: 'America/Toronto',
        hour: 'numeric',
        minute: '2-digit'
      }).format(new Date(feed.generated_at));
    } catch {
      return '';
    }
  }
</script>

<svelte:head>
  <title>Forest City News | London, Ontario</title>
  <meta name="description" content="A fast, local-first news reader for London, Ontario and Canada." />
</svelte:head>

<main class="app-page home-page editorial-home" id="main-content">
  <div class="shell">
    <section class="home-masthead">
      <div>
        <p class="eyebrow">London, Ontario</p>
        <h1>Forest City News</h1>
      </div>
      {#if feed}
        <p class="home-updated">Updated {updatedLabel()}</p>
      {/if}
    </section>

    <div class="app-control-row home-scope-controls" aria-label="News scope">
      <button class:active={activeScope === 'local'} class="app-chip" type="button" on:click={() => activeScope = 'local'}>Local</button>
      <button class:active={activeScope === 'canada'} class="app-chip" type="button" on:click={() => activeScope = 'canada'}>Canada</button>
      <button class:active={activeScope === 'all'} class="app-chip" type="button" on:click={() => activeScope = 'all'}>All</button>
    </div>

    <div class="app-control-row home-category-controls" aria-label="News category">
      {#each categories as category}
        <button
          class:active={activeCategory === category}
          class="app-chip"
          type="button"
          on:click={() => activeCategory = category}
        >
          {category}
        </button>
      {/each}
    </div>

    {#if error}
      <div class="app-error">{error}</div>
    {:else if !feed}
      <div class="app-loading-grid" aria-label="Loading news">
        <div class="app-skeleton"></div>
        <div class="app-skeleton"></div>
        <div class="app-skeleton"></div>
      </div>
    {:else if filteredStories.length === 0}
      <div class="app-empty">No stories match these filters right now.</div>
    {:else}
      <section class="home-top-stories" aria-labelledby="top-stories-heading">
        <div class="app-section-heading">
          <div>
            <p class="eyebrow">{activeScope === 'local' ? 'Around London' : activeScope === 'canada' ? 'Across Canada' : 'Latest'}</p>
            <h2 id="top-stories-heading">Top stories</h2>
          </div>
        </div>

        <div class="home-lead-grid">
          {#if topStories[0]}
            <NewsCard story={topStories[0]} variant="featured" />
          {/if}
          <div class="home-support-grid">
            {#each topStories.slice(1) as story}
              <NewsCard {story} showSummary={false} />
            {/each}
          </div>
        </div>
      </section>

      {#if timelineStories.length}
        <section class="home-latest" id="latest" aria-labelledby="latest-heading">
          <div class="app-section-heading">
            <div>
              <p class="eyebrow">Live feed</p>
              <h2 id="latest-heading">Latest</h2>
            </div>
          </div>

          <div class="app-story-grid">
            {#each timelineStories as story (story.id)}
              <NewsCard {story} />
            {/each}
          </div>
        </section>
      {/if}
    {/if}
  </div>
</main>

<style>
  .home-masthead {
    padding: 24px 0 22px;
    display: flex;
    justify-content: space-between;
    align-items: end;
    gap: 20px;
  }

  .home-masthead .eyebrow {
    margin: 0 0 4px;
    color: var(--accent, #34c759);
    text-transform: uppercase;
    font-size: 11px;
    font-weight: 800;
    letter-spacing: .09em;
  }

  .home-masthead h1 {
    margin: 0;
    font-size: clamp(38px, 7vw, 70px);
    line-height: .92;
    letter-spacing: -0.055em;
    color: var(--text);
  }

  .home-updated {
    margin: 0;
    color: var(--text-tertiary);
    font-size: 12px;
    font-weight: 600;
  }

  .home-scope-controls {
    margin-bottom: 10px;
  }

  .home-category-controls {
    padding-bottom: 15px;
  }

  .home-lead-grid {
    display: grid;
    grid-template-columns: minmax(0, 1.7fr) minmax(280px, .8fr);
    gap: 28px;
    align-items: start;
  }

  .home-support-grid {
    display: grid;
    gap: 28px;
  }

  .home-latest {
    margin-top: 12px;
  }

  @media (max-width: 760px) {
    .home-masthead {
      padding-top: 8px;
    }

    .home-masthead h1 {
      font-size: 42px;
    }

    .home-updated {
      display: none;
    }

    .home-lead-grid {
      grid-template-columns: 1fr;
      gap: 28px;
    }

    .home-support-grid {
      grid-template-columns: 1fr 1fr;
      gap: 14px;
    }
  }

  @media (max-width: 520px) {
    .home-support-grid {
      grid-template-columns: 1fr;
      gap: 26px;
    }
  }
</style>
