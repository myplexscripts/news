<script>
  import { browser } from '$app/environment';
  import { page } from '$app/stores';
  import { base } from '$app/paths';
  import { goto } from '$app/navigation';
  import NewsCard from '$lib/components/NewsCard.svelte';
  import { formatPublished, loadFeed, loadStory, resolveAsset } from '$lib/newsData';
  import { markRead } from '$lib/appState';
  import { sourceLogoPath } from '$lib/sourceLogos';

  let feed;
  let story;
  let currentId = '';
  let error = '';
  let loading = true;
  let readTimer;

  $: requestedId = String($page.params.id || '');
  $: if (browser && requestedId && requestedId !== currentId) {
    openStory(requestedId);
  }

  async function openStory(id) {
    currentId = id;
    loading = true;
    error = '';
    story = undefined;
    clearTimeout(readTimer);

    try {
      feed ||= await loadFeed();
      const metadata = (feed.stories || []).find((item) => String(item.id) === id);
      if (!metadata) throw new Error('This story is no longer available.');
      story = await loadStory(id, metadata);

      readTimer = window.setTimeout(() => {
        if (document.visibilityState === 'visible' && currentId === id) {
          markRead(id).catch(() => {});
        }
      }, 1200);
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Unable to open this story.';
    } finally {
      loading = false;
    }
  }

  function goBack() {
    if (history.length > 1) history.back();
    else goto(`${base}/`);
  }

  function compareKey(value = '') {
    return String(value)
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function nearDuplicate(left = '', right = '') {
    const a = compareKey(left);
    const b = compareKey(right);
    if (!a || !b) return false;
    if (a === b) return true;
    const shorter = a.length <= b.length ? a : b;
    const longer = a.length <= b.length ? b : a;
    return shorter.length >= 28 && longer.startsWith(shorter) && shorter.length / longer.length >= 0.58;
  }

  function normalizeImageKey(value = '') {
    try {
      const url = new URL(value);
      return `${url.hostname}${url.pathname}`.toLowerCase().replace(/\/$/, '');
    } catch {
      return String(value).split('?')[0].toLowerCase().replace(/\/$/, '');
    }
  }

  function buildBlocks(article) {
    if (!article) return [];

    const legacy = Array.isArray(article.paragraphs) && article.paragraphs.length
      ? article.paragraphs
      : article.content
        ? String(article.content).split(/\n+/).filter(Boolean)
        : article.summary
          ? [article.summary]
          : [];

    const blocks = Array.isArray(article.content_blocks) && article.content_blocks.length
      ? article.content_blocks
      : legacy.map((text) => ({ type: 'paragraph', text }));

    const qualityScore = article.quality?.score ?? (article.content_status === 'full' ? 70 : 40);
    const usable = blocks.length > 0
      && !['failed', 'summary'].includes(article.content_status)
      && qualityScore >= 45;

    const reader = usable ? blocks : article.summary ? [{ type: 'paragraph', text: article.summary }] : blocks;
    const heroKey = normalizeImageKey(article.image || article.card_image || '');
    const seen = new Set(heroKey ? [heroKey] : []);

    return reader.filter((block) => {
      if (block.type !== 'image' || !block.url) return true;
      const key = normalizeImageKey(block.url);
      if (!key || seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }

  $: blocks = buildBlocks(story);
  $: heroImage = resolveAsset(story?.image || story?.card_image || '');
  $: sourceLogo = story ? sourceLogoPath(story.source || '', `${base}/`) : '';
  $: firstTextBlock = blocks.find((block) => ['paragraph', 'quote'].includes(block.type) && block.text);
  $: showDeck = Boolean(
    story?.summary
    && !nearDuplicate(story.summary, story.title)
    && !(firstTextBlock?.text && nearDuplicate(story.summary, firstTextBlock.text))
  );
  $: readMinutes = story && Number(story.word_count) > 0
    ? Math.max(1, Math.round(Number(story.word_count) / 220))
    : null;
  $: clusterCoverage = story && feed
    ? (feed.stories || [])
        .filter((item) => item.cluster_id && item.cluster_id === story.cluster_id && String(item.id) !== String(story.id))
        .slice(0, 5)
    : [];
  $: related = story && feed
    ? (feed.stories || [])
        .filter((item) =>
          String(item.id) !== String(story.id)
          && item.cluster_representative !== false
          && item.cluster_id !== story.cluster_id
          && (item.category === story.category || item.source === story.source)
        )
        .slice(0, 4)
    : [];
  $: tags = story
    ? [...new Set([story.category, ...(Array.isArray(story.story_topics) ? story.story_topics : [])].filter(Boolean))]
        .filter((tag) => String(tag).toLowerCase() !== 'full story')
    : [];
</script>

<svelte:head>
  <title>{story?.title ? `${story.title} | Forest City News` : 'Article | Forest City News'}</title>
  {#if story?.summary}<meta name="description" content={story.summary} />{/if}
</svelte:head>

<main class="article-page svelte-article-page" id="main-content">
  <div class="article-shell shell">
    <button class="article-back" type="button" on:click={goBack} aria-label="Go back">
      <i class="ph ph-arrow-left" aria-hidden="true"></i>
      <span>Back</span>
    </button>

    {#if loading}
      <div class="article-loading">
        <div class="article-title-skeleton"></div>
        <div class="article-image-skeleton"></div>
        <div class="article-copy-skeleton"></div>
      </div>
    {:else if error}
      <div class="app-error">{error}</div>
    {:else if story}
      <article class="article-layout article-layout-refined">
        <header class="article-header article-header-refined">
          {#if sourceLogo}
            <img class="article-source-heading-logo" src={sourceLogo} alt={`${story.source} logo`} />
          {:else if story.source}
            <span class="article-source-heading-name">{story.source}</span>
          {/if}

          <h1>{story.title}</h1>
          {#if showDeck}
            <p class="article-deck">{story.summary}</p>
          {/if}
        </header>

        <aside class="article-sidebar article-sidebar-refined" aria-label="Article source and details">
          <div class="article-sidebar-sticky">
            {#if sourceLogo}
              <img class="article-sidebar-source-logo" src={sourceLogo} alt={`${story.source} logo`} />
            {/if}
            <div class="article-source-card article-source-card-refined">
              <div class="source-card-identity">
                <span class="source-card-label">Published by</span>
                <strong class="source-card-name">{story.source}</strong>
              </div>
              <div class="source-card-details">
                {#if story.author}<span>By {story.author}</span>{/if}
                <time datetime={story.published}>{formatPublished(story.published)}</time>
              </div>

              {#if clusterCoverage.length}
                <div class="source-coverage">
                  <span class="source-card-label">Also covered by</span>
                  <div class="source-coverage-links">
                    {#each clusterCoverage as item}
                      <a href={`${base}/story/${encodeURIComponent(item.id)}/`} data-sveltekit-preload-data="tap">
                        <span>{item.source}</span>
                        <i class="ph ph-arrow-right" aria-hidden="true"></i>
                      </a>
                    {/each}
                  </div>
                </div>
              {/if}

              {#if story.url}
                <a class="source-original-link" href={story.url} target="_blank" rel="noopener noreferrer">
                  Original article <i class="ph ph-arrow-up-right" aria-hidden="true"></i>
                </a>
              {/if}
            </div>

            {#if readMinutes || tags.length}
              <div class="article-sidebar-details">
                {#if readMinutes}
                  <div class="article-sidebar-readtime">
                    <i class="ph ph-clock" aria-hidden="true"></i>
                    <span>{readMinutes} min read</span>
                  </div>
                {/if}
                {#if tags.length}
                  <div class="article-sidebar-tags" aria-label="Story categories and tags">
                    {#each tags as tag}<span>{tag}</span>{/each}
                  </div>
                {/if}
              </div>
            {/if}
          </div>
        </aside>

        {#if heroImage}
          <figure class="article-hero article-hero-refined">
            <img src={heroImage} alt={story.image_alt || ''} referrerpolicy="no-referrer" />
            {#if story.image_caption}<figcaption>{story.image_caption}</figcaption>{/if}
          </figure>
        {/if}

        <div class="article-reader article-reader-refined">
          <div class="article-copy article-copy-refined">
            {#if blocks.length === 0}
              <p>No readable article body was returned by this source.</p>
            {/if}

            {#each blocks as block}
              {#if block.type === 'paragraph' && block.html}
                <p>{@html block.html}</p>
              {:else if block.type === 'paragraph' && block.text}
                <p>{#if block.emphasis === 'strong'}<strong>{block.text}</strong>{:else}{block.text}{/if}</p>
              {:else if block.type === 'heading' && block.text && Number(block.level) === 3}
                <h3>{#if block.html}{@html block.html}{:else}{block.text}{/if}</h3>
              {:else if block.type === 'heading' && block.text}
                <h2>{#if block.html}{@html block.html}{:else}{block.text}{/if}</h2>
              {:else if block.type === 'quote' && block.text}
                <blockquote>{#if block.html}{@html block.html}{:else}{block.text}{/if}</blockquote>
              {:else if block.type === 'list' && block.ordered}
                <ol>
                  {#each block.items || [] as item}
                    <li>{#if typeof item === 'string'}{item}{:else if item?.html}{@html item.html}{:else}{item?.text}{/if}</li>
                  {/each}
                </ol>
              {:else if block.type === 'list'}
                <ul>
                  {#each block.items || [] as item}
                    <li>{#if typeof item === 'string'}{item}{:else if item?.html}{@html item.html}{:else}{item?.text}{/if}</li>
                  {/each}
                </ul>
              {:else if block.type === 'image' && block.url}
                <figure class="inline-article-image">
                  <img
                    src={resolveAsset(block.url)}
                    alt={block.alt || ''}
                    width={block.width || undefined}
                    height={block.height || undefined}
                    loading="lazy"
                    decoding="async"
                    referrerpolicy="no-referrer"
                  />
                  {#if block.caption}<figcaption>{block.caption}</figcaption>{/if}
                </figure>
              {:else if block.type === 'media' && block.media_type === 'audio' && block.url}
                <figure class="article-media article-media-audio">
                  {#if block.title}<figcaption>{block.title}</figcaption>{/if}
                  <audio controls preload="none" src={block.url}></audio>
                </figure>
              {:else if block.type === 'media' && block.media_type === 'video' && block.url}
                <figure class="article-media article-media-video">
                  {#if block.title}<figcaption>{block.title}</figcaption>{/if}
                  <video controls playsinline preload="metadata" poster={block.poster || undefined} src={block.url}></video>
                </figure>
              {:else if block.type === 'media' && block.media_type === 'embed' && block.url}
                <figure class="article-media article-media-embed">
                  {#if block.title}<figcaption>{block.title}</figcaption>{/if}
                  <div class="article-media-frame">
                    <iframe
                      src={block.url}
                      title={block.title || 'Embedded media'}
                      loading="lazy"
                      referrerpolicy="no-referrer"
                      allow="autoplay; encrypted-media; picture-in-picture"
                      allowfullscreen
                    ></iframe>
                  </div>
                  {#if block.source_url}
                    <a class="article-embed-source" href={block.source_url} target="_blank" rel="noopener noreferrer">
                      View original post <i class="ph ph-arrow-up-right" aria-hidden="true"></i>
                    </a>
                  {/if}
                </figure>
              {:else if block.type === 'media' && block.media_type === 'link' && block.url}
                <a class="article-media article-media-link" href={block.url} target="_blank" rel="noopener noreferrer">
                  <i class="ph ph-play-circle" aria-hidden="true"></i>
                  <span>
                    <strong>{block.title || 'Open media at source'}</strong>
                    <small>Open media from {story.source}</small>
                  </span>
                  <i class="ph ph-arrow-up-right" aria-hidden="true"></i>
                </a>
              {/if}
            {/each}
          </div>
        </div>
      </article>

      {#if related.length}
        <section class="related-section related-section-refined">
          <div class="app-section-heading">
            <div>
              <p class="eyebrow">Keep reading</p>
              <h2>More from London</h2>
            </div>
          </div>
          <div class="app-story-grid two">
            {#each related as item (item.id)}
              <NewsCard story={item} />
            {/each}
          </div>
        </section>
      {/if}
    {/if}
  </div>
</main>

<style>
  .svelte-article-page {
    padding: 18px 0 48px;
  }

  .article-back {
    border: 0;
    background: none;
    color: var(--accent, #34c759);
    min-height: 42px;
    padding: 0;
    margin-bottom: 10px;
    display: inline-flex;
    align-items: center;
    gap: 7px;
    font-size: 14px;
    font-weight: 750;
    cursor: pointer;
  }

  .article-header h1 {
    color: var(--text);
  }

  .article-source-heading-name {
    color: var(--accent, #34c759);
    font-weight: 750;
  }

  .article-hero img,
  .inline-article-image img {
    display: block;
    width: 100%;
    height: auto !important;
    max-height: none !important;
    object-fit: contain !important;
  }

  .inline-article-image {
    margin: 30px 0;
  }

  .inline-article-image figcaption,
  .article-hero figcaption {
    margin-top: 8px;
    color: var(--text-tertiary);
    font-size: 12px;
    line-height: 1.4;
  }

  .article-copy {
    color: var(--text);
  }

  .article-copy p,
  .article-copy li {
    color: var(--text);
  }

  .article-loading {
    display: grid;
    gap: 20px;
    padding-top: 20px;
  }

  .article-title-skeleton,
  .article-image-skeleton,
  .article-copy-skeleton {
    border-radius: 16px;
    background: var(--surface-subtle);
  }

  .article-title-skeleton {
    height: 110px;
    max-width: 850px;
  }

  .article-image-skeleton {
    height: min(54vw, 540px);
  }

  .article-copy-skeleton {
    height: 420px;
    max-width: 720px;
  }

  @media (max-width: 760px) {
    .svelte-article-page {
      padding-top: 5px;
    }

    .article-back span {
      display: none;
    }
  }
</style>
