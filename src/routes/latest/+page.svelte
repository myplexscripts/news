<script>
  import { onMount } from 'svelte';
  import NewsCard from '$lib/components/NewsCard.svelte';
  import { loadFeed, sortNewest } from '$lib/newsData';
  import { userState } from '$lib/appState';

  let feed;
  let error = '';

  onMount(async () => {
    try {
      feed = await loadFeed();
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Unable to load latest stories.';
    }
  });

  $: hidden = new Set($userState.hiddenSources.map((source) => source.toLowerCase()));
  $: reads = new Set($userState.readIds);
  $: stories = feed
    ? sortNewest(feed.stories || []).filter((story) => {
        if (story.cluster_representative === false) return false;
        if (hidden.has(String(story.source || '').toLowerCase())) return false;
        if ($userState.hideRead && reads.has(String(story.id))) return false;
        return true;
      }).slice(0, 120)
    : [];
</script>

<svelte:head>
  <title>Latest | Forest City News</title>
</svelte:head>

<main class="app-page" id="main-content">
  <section class="shell">
    <header class="app-page-heading">
      <p class="eyebrow">Newest first</p>
      <h1>Latest</h1>
      <p>The newest stories from every enabled source.</p>
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
      <div class="app-story-grid">
        {#each stories as story (story.id)}
          <NewsCard {story} />
        {/each}
      </div>
    {/if}
  </section>
</main>
