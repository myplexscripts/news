<script>
  import { userState, toggleSavedStory } from '$lib/appState';
  import { prefetchStory, resolveAsset, storyHref } from '$lib/newsData';
  import { sourceLogoPath } from '$lib/sourceLogos';
  import { base } from '$app/paths';
  import Icon from '$lib/components/Icon.svelte';

  export let story;
  export let variant = 'standard';
  export let showSummary = true;
  export let className = '';
  export let index = 99;
  export let dateGroup = '';

  let fallbackIndex = 0;
  let fallbackStoryId = '';

  $: id = String(story?.id || '');
  $: if (id !== fallbackStoryId) {
    fallbackStoryId = id;
    fallbackIndex = 0;
  }
  $: isSaved = $userState.savedIds.includes(id);
  $: isRead = $userState.readIds.includes(id);
  $: rawCandidates = variant === 'standard'
    ? [story?.card_image_small, story?.card_image, story?.image]
    : [story?.card_image, story?.image, story?.card_image_small];
  $: imageCandidates = [...new Set(rawCandidates.map((value) => resolveAsset(value)).filter(Boolean))];
  $: image = imageCandidates[fallbackIndex] || '';
  $: logo = sourceLogoPath(story?.source || '', `${base}/`);
  $: href = storyHref(id);
  $: timestamp = story?.cluster_latest_published || story?.published;
  $: readMinutes = Number(story?.word_count) > 0
    ? Math.max(1, Math.round(Number(story.word_count) / 220))
    : null;
  $: clusterSources = Array.isArray(story?.cluster_sources) && story.cluster_sources.length
    ? story.cluster_sources
    : [story?.source].filter(Boolean);
  $: sourceCount = Math.max(Number(story?.cluster_source_count || 0), clusterSources.length || 1);
  $: categoryClass = `category-${String(story?.category || 'Local').toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;
  $: title = truncateTitle(story?.title || '');

  function truncateTitle(value) {
    const words = String(value || '').trim().split(/\s+/).filter(Boolean);
    return words.length > 20 ? `${words.slice(0, 20).join(' ')}…` : words.join(' ');
  }

  function published(value) {
    try {
      return new Intl.DateTimeFormat('en-CA', {
        timeZone: 'America/Toronto',
        month: 'short',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit'
      }).format(new Date(value));
    } catch {
      return '';
    }
  }

  function warm() {
    prefetchStory(story);
  }

  function imageError() {
    fallbackIndex += 1;
  }

  function syncImageMode(event) {
    const imageElement = event.currentTarget;
    const media = imageElement?.closest?.('.news-card-media');
    if (!media || !imageElement.naturalWidth || !imageElement.naturalHeight) return;
    const contained = imageElement.naturalHeight >= imageElement.naturalWidth;
    media.classList.toggle('is-contained-image', contained);
    media.classList.toggle('is-fill-image', !contained);
  }

  async function toggle(event) {
    event.preventDefault();
    event.stopPropagation();
    if (!id) return;
    await toggleSavedStory(id).catch(() => {});
  }
</script>

<article
  class={`news-card card-${variant} ${categoryClass} ${className}`}
  class:is-read-story={isRead}
  class:no-image={!image}
  data-story-id={id}
  data-category={story?.category || ''}
  data-source={story?.source || ''}
  data-sources={clusterSources.join('|')}
  data-scope={story?.scope || 'local'}
  data-date-group={dateGroup}
  on:pointerenter={warm}
  on:pointerdown={warm}
>
  <a class="news-card-link" href={href} data-sveltekit-preload-data="tap" aria-label={story?.title || 'Open article'}></a>

  {#if image}
    <div class="news-card-media">
      {#if variant === 'featured'}
        <img
          class="news-card-photo-backdrop"
          src={image}
          alt=""
          aria-hidden="true"
          loading={index < 3 ? 'eager' : 'lazy'}
          decoding="async"
          referrerpolicy="no-referrer"
        />
      {/if}
      <img
        class="news-card-photo"
        src={image}
        alt={story?.image_alt || ''}
        loading={index < 3 ? 'eager' : 'lazy'}
        decoding="async"
        referrerpolicy="no-referrer"
        style={`--focus-x:${story?.image_focus_x ?? 50}%;--focus-y:${story?.image_focus_y ?? 50}%`}
        on:load={syncImageMode}
        on:error={imageError}
      />
    </div>
  {/if}

  <div class="news-card-body">
    {#if logo && variant === 'featured'}
      <span class="card-source-mark-slot">
        <img class="card-source-mark" src={logo} alt="" loading="lazy" decoding="async" />
      </span>
    {:else if logo}
      <img class="card-source-mark" src={logo} alt="" loading="lazy" decoding="async" />
    {/if}

    {#if story?.source}
      <span class="card-source-name" hidden={Boolean(logo)}>{story.source}</span>
    {/if}

    <h3 title={story?.title || ''}>{title}</h3>

    <div class="news-card-footer">
      <time datetime={timestamp}>{published(timestamp)}</time>
      {#if sourceCount > 1}
        <span class="news-card-coverage" title={`Covered by ${sourceCount} sources`}>
          <Icon name="layers" size={16} strokeWidth={2.25} />
          {sourceCount} sources
        </span>
      {/if}
      {#if readMinutes}<span>{readMinutes} min read</span>{/if}
    </div>

    {#if showSummary && story?.summary}
      <p class="news-card-summary">{story.summary}</p>
    {/if}

    <button
      class:is-saved={isSaved}
      class="news-card-save"
      type="button"
      aria-label={isSaved ? 'Remove from Read Later' : 'Save to Read Later'}
      aria-pressed={isSaved}
      title={isSaved ? 'Remove from Read Later' : 'Save to Read Later'}
      on:click={toggle}
    >
      <Icon name="bookmark" size={22} strokeWidth={isSaved ? 2.75 : 2} />
    </button>
  </div>
</article>

<style>
  .news-card {
    position: relative;
  }

  .news-card-link {
    position: absolute;
    inset: 0;
    z-index: 2;
    border-radius: inherit;
  }

  .news-card-link:focus-visible {
    outline: 3px solid var(--accent);
    outline-offset: 3px;
  }

  .news-card-body {
    position: relative;
    padding-bottom: 56px !important;
  }

  .news-card-coverage {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    color: var(--accent);
    font-size: 16px;
    font-weight: 700;
  }

  .news-card-save {
    position: absolute;
    z-index: 4;
    right: 10px;
    bottom: 8px;
    width: 44px;
    height: 44px;
    display: grid;
    place-items: center;
    padding: 0;
    border: 0;
    border-radius: 0;
    background: transparent;
    color: var(--muted);
    cursor: pointer;
  }

  .news-card-save:hover,
  .news-card-save:focus-visible,
  .news-card-save.is-saved {
    color: var(--accent);
  }

  .news-card-save:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }

  .card-source-mark-slot {
    min-height: 24px;
    display: flex;
    align-items: center;
  }
</style>
