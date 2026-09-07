<script>
  import { onMount } from 'svelte';
  import NewsCard from '$lib/components/NewsCard.svelte';
  import { loadFeed } from '$lib/newsData';
  import { clearSaved, userState } from '$lib/appState';

  let feed;
  let error = '';

  onMount(async () => {
    try {
      feed = await loadFeed();
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Unable to load Read Later.';
    }
  });

  $: byId = new Map((feed?.stories || []).map((story) => [String(story.id), story]));
  $: savedStories = $userState.savedIds.map((id) => byId.get(String(id))).filter(Boolean);
</script>

<svelte:head>
  <title>Read Later | Forest City News</title>
  <meta name="description" content="Stories saved for later in Forest City News." />
</svelte:head>

<main class="app-page" id="main-content">
  <section class="shell">
    <header class="app-page-heading saved-heading">
      <div>
        <p class="eyebrow">Your list</p>
        <h1>Read Later</h1>
        <p>Stories you save stay on this device.</p>
      </div>
      {#if savedStories.length}
        <button class="clear-saved" type="button" on:click={() => clearSaved().catch(() => {})}>Clear</button>
      {/if}
    </header>

    {#if error}
      <div class="app-error">{error}</div>
    {:else if !feed}
      <div class="app-loading-grid">
        <div class="app-skeleton"></div>
        <div class="app-skeleton"></div>
        <div class="app-skeleton"></div>
      </div>
    {:else if savedStories.length === 0}
      <div class="app-empty">You have not saved any stories yet.</div>
    {:else}
      <div class="app-story-grid">
        {#each savedStories as story (story.id)}
          <NewsCard {story} />
        {/each}
      </div>
    {/if}
  </section>
</main>

<style>
  .saved-heading {
    display: flex;
    justify-content: space-between;
    align-items: end;
    gap: 20px;
  }

  .clear-saved {
    border: 0;
    background: none;
    color: var(--accent, #34c759);
    font-size: 14px;
    font-weight: 700;
    cursor: pointer;
    padding: 8px 0;
  }
</style>
