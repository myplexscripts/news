<script>
  import { onMount, onDestroy } from 'svelte';
  import { readScreen, rememberScreen } from '$lib/screenState';
  import NewsCard from '$lib/components/NewsCard.svelte';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import { getCachedFeed, loadFeed, feedUpdates, sortNewest } from '$lib/newsData';
  import { userState } from '$lib/appState';

  let feed = readScreen('latest')?.feed || getCachedFeed();
  onDestroy(() => rememberScreen('latest', { feed }));
  let error = '';
  onMount(() => feedUpdates.subscribe((latest) => {
    if (latest && !feed) { feed = latest; error = ''; }
  }));

  onMount(async () => {
    try {
      const latest = await loadFeed();
      if (!feed) feed = latest;
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

<main class="app-page standard-page" id="main-content">
  <section class="standard-page-shell shell">
    <PageHeader title="Latest" />

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
