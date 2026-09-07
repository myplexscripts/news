<script>
  import { userState, toggleSavedStory } from '$lib/appState';
  import { formatRelativeTime, prefetchStory, resolveAsset, storyHref } from '$lib/newsData';
  import { sourceLogoPath } from '$lib/sourceLogos';
  import { base } from '$app/paths';

  export let story;
  export let variant = 'standard';
  export let showSummary = true;

  $: id = String(story?.id || '');
  $: isSaved = $userState.savedIds.includes(id);
  $: isRead = $userState.readIds.includes(id);
  $: image = resolveAsset(
    variant === 'featured'
      ? story?.card_image || story?.image || story?.card_image_small
      : story?.card_image_small || story?.card_image || story?.image
  );
  $: logo = sourceLogoPath(story?.source || '', `${base}/`);
  $: href = storyHref(id);
  $: readMinutes = Number(story?.word_count) > 0
    ? Math.max(1, Math.round(Number(story.word_count) / 220))
    : null;

  function warm() {
    prefetchStory(story);
  }

  async function toggle(event) {
    event.preventDefault();
    event.stopPropagation();
    if (!id) return;
    await toggleSavedStory(id).catch(() => {});
  }
</script>

<article
  class:featured={variant === 'featured'}
  class:standard={variant !== 'featured'}
  class:is-read-story={isRead}
  class="news-card svelte-news-card"
  data-story-id={id}
  data-source={story?.source || ''}
  on:pointerenter={warm}
  on:pointerdown={warm}
>
  <a class="news-card-link" href={href} data-sveltekit-preload-data="tap" aria-label={story?.title || 'Open article'}>
    {#if image}
      <div class="news-card-media">
        <img src={image} alt={story?.image_alt || ''} loading={variant === 'featured' ? 'eager' : 'lazy'} decoding="async" referrerpolicy="no-referrer" />
      </div>
    {/if}

    <div class="news-card-copy">
      <div class="news-card-source">
        {#if logo}
          <img src={logo} alt="" aria-hidden="true" loading="lazy" />
        {/if}
        <span>{story?.source || 'Forest City News'}</span>
      </div>

      <h3>{story?.title}</h3>

      {#if showSummary && story?.summary}
        <p class="news-card-summary">{story.summary}</p>
      {/if}

      <div class="news-card-meta">
        <time>{formatRelativeTime(story?.cluster_latest_published || story?.published)}</time>
        {#if readMinutes}<span>{readMinutes} min</span>{/if}
        {#if Number(story?.cluster_source_count || 1) > 1}
          <span>{story.cluster_source_count} sources</span>
        {/if}
      </div>
    </div>
  </a>

  <button
    class:active={isSaved}
    class="news-card-save"
    type="button"
    aria-label={isSaved ? 'Remove from Read Later' : 'Save to Read Later'}
    aria-pressed={isSaved}
    on:click={toggle}
  >
    <i class={isSaved ? 'ph-fill ph-bookmark-simple' : 'ph ph-bookmark-simple'} aria-hidden="true"></i>
  </button>
</article>

<style>
  .svelte-news-card {
    position: relative;
    min-width: 0;
  }

  .news-card-link {
    color: inherit;
    text-decoration: none;
    display: block;
    height: 100%;
  }

  .news-card-media {
    overflow: hidden;
    background: var(--surface-subtle, #f2f2f2);
    border-radius: 16px;
    aspect-ratio: 16 / 10;
  }

  .news-card-media img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
    transition: transform 260ms cubic-bezier(.2,.8,.2,1);
  }

  .news-card-link:active .news-card-media img {
    transform: scale(.985);
  }

  .news-card-copy {
    padding-top: 12px;
  }

  .news-card-source {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
    margin-bottom: 7px;
    color: var(--accent, #34c759);
    font-size: 13px;
    line-height: 1.2;
    font-weight: 700;
  }

  .news-card-source img {
    width: auto;
    max-width: 82px;
    height: 17px;
    object-fit: contain;
  }

  .news-card h3 {
    margin: 0;
    color: var(--text, #111);
    font-size: clamp(18px, 2vw, 24px);
    line-height: 1.08;
    letter-spacing: -0.025em;
    text-wrap: balance;
  }

  .featured h3 {
    font-size: clamp(26px, 4vw, 44px);
  }

  .news-card-summary {
    margin: 8px 0 0;
    color: var(--text-secondary, #666);
    line-height: 1.45;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .news-card-meta {
    margin-top: 10px;
    display: flex;
    flex-wrap: wrap;
    gap: 6px 10px;
    color: var(--text-tertiary, #777);
    font-size: 12px;
    font-weight: 600;
  }

  .news-card-meta span + span::before,
  .news-card-meta time + span::before {
    content: '•';
    margin-right: 10px;
    opacity: .55;
  }

  .news-card-save {
    position: absolute;
    right: 8px;
    top: 8px;
    width: 38px;
    height: 38px;
    border: 0;
    border-radius: 50%;
    display: grid;
    place-items: center;
    background: color-mix(in srgb, var(--background, #fff) 88%, transparent);
    color: var(--text, #111);
    box-shadow: 0 1px 10px rgba(0,0,0,.09);
    backdrop-filter: blur(14px) saturate(150%);
    -webkit-backdrop-filter: blur(14px) saturate(150%);
    cursor: pointer;
    font-size: 19px;
  }

  .news-card-save.active {
    color: var(--accent, #34c759);
  }

  .is-read-story {
    opacity: .64;
  }

  @media (max-width: 720px) {
    .news-card-media {
      border-radius: 13px;
    }

    .news-card h3 {
      font-size: 18px;
      line-height: 1.13;
    }

    .featured h3 {
      font-size: 27px;
    }

    .news-card-summary {
      font-size: 14px;
    }
  }
</style>
