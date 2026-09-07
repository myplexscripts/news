<script>
  import { onMount } from 'svelte';
  import NewsCard from '$lib/components/NewsCard.svelte';
  import Icon from '$lib/components/Icon.svelte';
  import { loadFeed } from '$lib/newsData';
  import { userState } from '$lib/appState';

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
  $: savedStories = ($userState.savedIds || []).map((id) => byId.get(String(id))).filter(Boolean);
  $: unavailableCount = Math.max(0, ($userState.savedIds || []).length - savedStories.length);
</script>

<svelte:head>
  <title>Read Later | Forest City News</title>
  <meta name="description" content="Articles saved to read later on this device." />
  <meta name="robots" content="noindex" />
</svelte:head>

<main class="read-later-page" id="main-content">
  <section class="read-later-shell shell">
    <header class="page-heading">
      <div class="page-heading-copy">
        <p class="masthead-label">Saved</p>
        <h1>Read Later</h1>
        <p class="page-heading-description">Articles you bookmark are saved on this device until you remove them.</p>
      </div>
    </header>

    {#if error}
      <p class="read-later-status app-error">{error}</p>
    {:else if !feed}
      <p class="read-later-status" aria-live="polite">Loading saved articles…</p>
    {:else}
      <p class="read-later-status" aria-live="polite">
        {#if savedStories.length}
          {savedStories.length} saved {savedStories.length === 1 ? 'article' : 'articles'}{unavailableCount ? ` · ${unavailableCount} no longer in the current archive` : ''}
        {:else}
          No saved articles
        {/if}
      </p>

      {#if savedStories.length}
        <div class="read-later-grid" aria-label="Saved articles">
          {#each savedStories as story, index (story.id)}
            <NewsCard {story} {index} className="read-later-card is-saved-story" />
          {/each}
        </div>
      {:else}
        <div class="read-later-empty">
          <Icon name="bookmark" size={34} strokeWidth={2} />
          <h2>Nothing saved yet</h2>
          <p>Tap the bookmark on any article to keep it here for later.</p>
        </div>
      {/if}
    {/if}
  </section>
</main>

<style>
  .read-later-page {
    padding-bottom: 80px;
  }

  .read-later-shell {
    padding-top: 34px;
  }

  .read-later-status {
    margin: 0 0 18px;
    color: var(--muted);
    font-size: 16px;
    font-weight: 600;
  }

  .read-later-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 18px;
  }

  :global(html[data-hide-read='true']) .read-later-page :global(.news-card.is-read-story) {
    display: grid !important;
  }

  .read-later-empty {
    min-height: 260px;
    display: grid;
    place-items: center;
    align-content: center;
    gap: 8px;
    padding: 36px 20px;
    border-radius: 24px;
    background: var(--surface-subtle);
    text-align: center;
  }

  .read-later-empty :global(.lucide-icon) {
    color: var(--accent);
  }

  .read-later-empty h2,
  .read-later-empty p {
    margin: 0;
  }

  .read-later-empty h2 {
    font-size: 24px;
  }

  .read-later-empty p {
    max-width: 420px;
    color: var(--muted);
    font-size: 16px;
  }

  @media (max-width: 760px) {
    .read-later-shell {
      padding-top: 18px;
    }

    .read-later-grid {
      grid-template-columns: minmax(0, 1fr);
      gap: 12px;
    }
  }
</style>
