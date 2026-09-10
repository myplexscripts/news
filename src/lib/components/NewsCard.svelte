<script>
  import { userState, toggleSavedStory } from '$lib/appState';
  import { prefetchStory, resolveAsset, storyHref } from '$lib/newsData';
  import { sourceLogoPath } from '$lib/sourceLogos';
  import { base } from '$app/paths';

  export let story;
  export let variant = 'standard';
  export let showSummary = true;
  export let className = '';
  export let index = 99;
  export let dateGroup = '';
  export let homeLazy = false;

  let fallbackIndex = 0;
  let fallbackStoryId = '';
  let logoFailed = false;
  let homeImageActive = false;

  $: id = String(story?.id || '');
  $: if (id !== fallbackStoryId) {
    fallbackStoryId = id;
    fallbackIndex = 0;
    logoFailed = false;
    homeImageActive = !homeLazy || variant === 'featured' || (index >= 3 && index < 6);
  }
  $: if (!homeLazy || variant === 'featured' || (index >= 3 && index < 6)) homeImageActive = true;
  $: isSaved = $userState.savedIds.includes(id);
  $: isRead = $userState.readIds.includes(id);
  $: smallImage = resolveAsset(story?.card_image_small || '');
  $: largeImage = resolveAsset(story?.card_image || '');
  $: rawCandidates = variant === 'standard'
    ? [story?.card_image_small, story?.card_image, story?.image]
    : [story?.card_image, story?.image, story?.card_image_small];
  $: imageCandidates = [...new Set(rawCandidates.map((value) => resolveAsset(value)).filter(Boolean))];
  $: image = imageCandidates[fallbackIndex] || '';
  $: cachedSrcset = smallImage && largeImage && smallImage !== largeImage
    ? `${smallImage} 420w, ${largeImage} 720w`
    : '';
  $: imageSrcset = fallbackIndex === 0 && cachedSrcset ? cachedSrcset : '';
  $: imageSizes = variant === 'featured'
    ? '(max-width: 720px) calc(100vw - 24px), (max-width: 1280px) 44vw, 560px'
    : '(max-width: 720px) calc(100vw - 24px), (max-width: 1100px) 50vw, 360px';
  $: backdropImage = smallImage || image;
  $: shouldRequestImage = !homeLazy || variant === 'featured' || homeImageActive;
  $: logo = sourceLogoPath(story?.source || '', `${base}/`);
  $: usableLogo = Boolean(logo && !logoFailed);
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

  function activateMedia(media) {
    media?.dispatchEvent?.(new CustomEvent('homeimageactivate'));
  }

  function trackHomeImage(node) {
    if (!homeLazy || typeof window === 'undefined') return {};

    const activate = () => {
      homeImageActive = true;
    };
    node.addEventListener('homeimageactivate', activate);

    if (!('IntersectionObserver' in window)) {
      homeImageActive = true;
      return {
        destroy() {
          node.removeEventListener('homeimageactivate', activate);
        }
      };
    }

    const observer = new IntersectionObserver((entries) => {
      if (!entries.some((entry) => entry.isIntersecting)) return;

      const timelineImages = Array.from(document.querySelectorAll('[data-home-image-card="true"]'));
      if (variant === 'featured') {
        timelineImages.slice(0, 3).forEach(activateMedia);
      } else {
        const current = timelineImages.indexOf(node);
        if (current >= 0) timelineImages.slice(current, current + 4).forEach(activateMedia);
      }

      observer.disconnect();
    }, { threshold: 0.01 });

    observer.observe(node);
    return {
      destroy() {
        observer.disconnect();
        node.removeEventListener('homeimageactivate', activate);
      }
    };
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

  <div
    class:news-card-placeholder-media={!image}
    class="news-card-media"
    data-home-image-card={homeLazy && variant !== 'featured' && image ? 'true' : undefined}
    use:trackHomeImage
  >
    {#if image}
      {#if variant === 'featured'}
        <img
          class="news-card-photo-backdrop"
          src={shouldRequestImage ? backdropImage : undefined}
          alt=""
          aria-hidden="true"
          loading="eager"
          decoding="async"
          fetchpriority="low"
          referrerpolicy="no-referrer"
        />
      {/if}
      <img
        class="news-card-photo"
        src={shouldRequestImage ? image : undefined}
        srcset={shouldRequestImage && imageSrcset ? imageSrcset : undefined}
        sizes={imageSrcset ? imageSizes : undefined}
        alt={story?.image_alt || ''}
        loading={homeLazy ? (shouldRequestImage ? 'eager' : 'lazy') : (index < 3 ? 'eager' : 'lazy')}
        decoding="async"
        fetchpriority={variant === 'featured' && index === 0 ? 'high' : 'auto'}
        referrerpolicy="no-referrer"
        style={`--focus-x:${story?.image_focus_x ?? 50}%;--focus-y:${story?.image_focus_y ?? 50}%`}
        on:load={syncImageMode}
        on:error={imageError}
      />
    {:else}
      <div class="news-card-placeholder" aria-hidden="true">
        <span class="news-card-placeholder-brand">
          <i class="ph-fill ph-tree"></i>
          <strong>News</strong>
        </span>
      </div>
    {/if}
  </div>

  <div class="news-card-body">
    {#if usableLogo}
      <img
        class="card-source-mark"
        src={logo}
        alt=""
        loading="lazy"
        decoding="async"
        on:error={() => logoFailed = true}
      />
    {/if}

    {#if story?.source}
      <span class="card-source-name" hidden={usableLogo}>{story.source}</span>
    {/if}

    <h3 title={story?.title || ''}>{title}</h3>

    <div class="news-card-footer">
      <time datetime={timestamp}>{published(timestamp)}</time>
      {#if sourceCount > 1}
        <span class="news-card-coverage" title={`Covered by ${sourceCount} sources`}>
          <i class="ph ph-stack" aria-hidden="true"></i>
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
      <i class={isSaved ? 'ph-fill ph-bookmark-simple' : 'ph ph-bookmark-simple'} aria-hidden="true"></i>
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
    display: flex !important;
    flex-direction: column !important;
    align-items: stretch !important;
    padding-bottom: 56px !important;
  }

  .card-source-mark,
  .card-source-name {
    order: 0;
    align-self: flex-start;
    flex: 0 0 auto;
    margin: 0 0 8px !important;
  }

  .card-source-mark {
    display: block !important;
    width: auto !important;
    height: auto !important;
    max-width: min(150px, 100%) !important;
    max-height: 30px !important;
    object-fit: contain !important;
    object-position: left center !important;
    transform: none !important;
  }

  .card-source-name {
    color: var(--accent);
    font-size: 16px;
    font-weight: 700;
    line-height: 1.2;
  }

  .news-card h3 {
    order: 1;
  }

  .news-card-summary {
    order: 2;
  }

  .news-card-footer {
    order: 3;
    margin-top: auto !important;
  }

  .news-card-placeholder-media {
    background: var(--green) !important;
  }

  .news-card-placeholder {
    width: 100%;
    height: 100%;
    min-height: 100%;
    display: grid;
    place-items: center;
    background: var(--green);
    color: #fff;
  }

  .news-card-placeholder-brand {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    color: #fff;
    line-height: 1;
  }

  .news-card-placeholder-brand i {
    font-size: 30px;
    line-height: 1;
  }

  .news-card-placeholder-brand strong {
    color: #fff;
    font-size: 24px;
    font-weight: 800;
    line-height: 1;
    letter-spacing: -0.04em;
  }

  .news-card-coverage {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    color: var(--accent);
    font-size: 16px;
    font-weight: 700;
  }

  .news-card-coverage i {
    font-size: 16px;
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

  .news-card-save i {
    font-size: 22px;
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
</style>
