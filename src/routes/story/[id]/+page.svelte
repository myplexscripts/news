<script>
  import { browser } from '$app/environment';
  import { page } from '$app/stores';
  import { base } from '$app/paths';
  import NewsCard from '$lib/components/NewsCard.svelte';
  import TweetCard from '$lib/components/TweetCard.svelte';
  import { formatPublished, loadFeed, loadStory, resolveAsset } from '$lib/newsData';
  import { markRead } from '$lib/appState';

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

  function coverSourceFor(article) {
    if (!article) return '';
    if (article.image) return article.image;
    const firstInline = Array.isArray(article.content_blocks)
      ? article.content_blocks.find((block) => block?.type === 'image' && block?.url)
      : null;
    return firstInline?.url || article.card_image || '';
  }

  function buildBlocks(article, coverSource = '') {
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
    const coverKey = normalizeImageKey(coverSource || article.image || article.card_image || '');
    const seen = new Set(coverKey ? [coverKey] : []);

    return reader.filter((block) => {
      if (block.type !== 'image' || !block.url) return true;
      const key = normalizeImageKey(block.url);
      if (!key || seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }

  function revealOnScroll(node) {
    if (!browser) return {};

    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduced || !('IntersectionObserver' in window)) {
      node.classList.add('article-reveal-visible');
      return {};
    }

    const observer = new IntersectionObserver(
      (entries) => {
        if (!entries.some((entry) => entry.isIntersecting)) return;
        requestAnimationFrame(() => node.classList.add('article-reveal-visible'));
        observer.disconnect();
      },
      {
        threshold: 0.04,
        rootMargin: '0px 0px -108px 0px'
      }
    );

    observer.observe(node);
    return { destroy: () => observer.disconnect() };
  }

  $: coverSource = coverSourceFor(story);
  $: blocks = buildBlocks(story, coverSource);
  $: heroImage = resolveAsset(coverSource);
  $: firstTextBlock = blocks.find((block) => ['paragraph', 'quote'].includes(block.type) && block.text);
  $: showDeck = Boolean(
    story?.summary
    && !nearDuplicate(story.summary, story.title)
    && !(firstTextBlock?.text && nearDuplicate(story.summary, firstTextBlock.text))
  );
  $: readMinutes = story && Number(story.word_count) > 0
    ? Math.max(1, Math.round(Number(story.word_count) / 220))
    : null;
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
</script>

<svelte:head>
  <title>{story?.title ? `${story.title} | Forest City News` : 'Article | Forest City News'}</title>
  {#if story?.summary}<meta name="description" content={story.summary} />{/if}
</svelte:head>

<main class="article-page svelte-article-page" id="main-content">
  {#if loading}
    <div class="article-shell shell">
      <div class="article-loading">
        <div class="article-title-skeleton"></div>
        <div class="article-image-skeleton"></div>
        <div class="article-copy-skeleton"></div>
      </div>
    </div>
  {:else if error}
    <div class="article-shell shell">
      <div class="app-error">{error}</div>
    </div>
  {:else if story}
    <article class="editorial-story">
      <header class:cover-no-image={!heroImage} class="article-cover">
        {#if heroImage}
          <div class="article-cover-media" aria-hidden="true">
            <img src={heroImage} alt="" referrerpolicy="no-referrer" />
          </div>
        {/if}
        <div class="article-cover-fade article-cover-fade-top" aria-hidden="true"></div>
        <div class="article-cover-fade article-cover-fade-bottom" aria-hidden="true"></div>

        <div class="article-cover-content shell">
          <h1>{story.title}</h1>
          <div class="article-cover-source-row">
            <div class="article-cover-author">
              {#if story.author}<strong>{/^by\s+/i.test(story.author) ? story.author : `By ${story.author}`}</strong>{/if}
            </div>

            {#if story.url}
              <a class="article-cover-original" href={story.url} target="_blank" rel="noopener noreferrer">
                <span>Original article</span>
                <i class="ph ph-arrow-up-right" aria-hidden="true"></i>
              </a>
            {/if}
          </div>
        </div>
      </header>

      <div class="article-after-cover shell">
        <div class="article-content-layout">
          <div class="article-flow-meta article-reveal" use:revealOnScroll>
            <time datetime={story.published}>{formatPublished(story.published)}</time>
            {#if readMinutes}<span>{readMinutes} min read</span>{/if}
          </div>

          <div class="article-reader article-reader-refined article-reveal" use:revealOnScroll>
            {#if heroImage}
              <figure class="article-body-hero inline-article-image">
                <img
                  src={heroImage}
                  alt={story.image_alt || ''}
                  loading="eager"
                  decoding="async"
                  referrerpolicy="no-referrer"
                />
                {#if story.image_caption}<figcaption>{story.image_caption}</figcaption>{/if}
              </figure>
            {/if}

            {#if showDeck}
              <p class="article-deck article-deck-after-cover">{story.summary}</p>
            {/if}

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
                {:else if block.type === 'media' && block.media_type === 'tweet' && block.url}
                  <TweetCard {block} />
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
        </div>
      </div>
    </article>

    {#if related.length}
      <section class="related-section related-section-refined shell">
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
</main>

<style>
  :global(body:has(.svelte-article-page) .site-header) {
    position: absolute !important;
    inset: 0 0 auto !important;
    z-index: 60 !important;
    background: transparent !important;
    border-bottom: 0 !important;
    backdrop-filter: none !important;
    -webkit-backdrop-filter: none !important;
  }

  :global(body:has(.svelte-article-page) .site-header .header-inner) {
    min-height: calc(64px + env(safe-area-inset-top)) !important;
    padding-top: env(safe-area-inset-top);
  }

  :global(body:has(.svelte-article-page) .site-header .header-actions) {
    visibility: hidden;
    pointer-events: none;
  }

  :global(body:has(.svelte-article-page) .story-cover-secondary-meta) {
    display: none !important;
  }

  .svelte-article-page {
    padding: 0 0 48px;
    overflow: clip;
  }

  .article-shell {
    padding-top: calc(84px + env(safe-area-inset-top));
  }

  .editorial-story {
    position: relative;
  }

  .article-cover {
    position: relative;
    min-height: 100svh;
    height: 100svh;
    overflow: hidden;
    background: var(--bg);
    isolation: isolate;
  }

  :global(body:has(.svelte-article-page) .editorial-story .article-cover) {
    min-height: 100svh !important;
    height: 100svh !important;
  }

  .article-cover-media,
  .article-cover-fade {
    position: absolute;
    inset: 0;
  }

  .article-cover-media {
    z-index: -3;
    inset: 0 0 auto;
    height: 78svh;
  }

  .article-cover-media img {
    width: 100%;
    height: 100% !important;
    max-height: none !important;
    object-fit: cover !important;
    object-position: center center;
  }

  .article-cover-fade {
    pointer-events: none;
  }

  .article-cover-fade-top {
    z-index: -2;
    bottom: auto;
    height: 30%;
    background: linear-gradient(
      to bottom,
      color-mix(in srgb, var(--bg) 58%, transparent) 0%,
      color-mix(in srgb, var(--bg) 38%, transparent) 34%,
      color-mix(in srgb, var(--bg) 16%, transparent) 66%,
      transparent 100%
    );
  }

  .article-cover-fade-bottom {
    z-index: -1;
    top: 40svh;
    bottom: auto;
    height: 40svh;
    background: linear-gradient(
      to bottom,
      transparent 0%,
      color-mix(in srgb, var(--bg) 18%, transparent) 24%,
      color-mix(in srgb, var(--bg) 62%, transparent) 56%,
      color-mix(in srgb, var(--bg) 92%, transparent) 78%,
      var(--bg) 94%,
      var(--bg) 100%
    );
  }

  .cover-no-image .article-cover-fade-top,
  .cover-no-image .article-cover-fade-bottom {
    background: var(--bg);
  }

  .article-cover-content {
    position: relative;
    z-index: 2;
    height: 100%;
    display: flex;
    flex-direction: column;
    justify-content: flex-end;
    padding-top: calc(90px + env(safe-area-inset-top));
    padding-bottom: clamp(42px, 6.5vh, 82px);
  }

  .article-cover-content h1 {
    width: min(100%, 900px);
    margin: 0;
    color: var(--ink);
    font-size: clamp(38px, 4.8vw, 62px);
    line-height: 1.02;
    letter-spacing: -0.052em;
    text-wrap: balance;
  }

  .article-cover-source-row {
    width: min(100%, 900px);
    min-height: 48px;
    margin-top: 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 22px;
    opacity: 0;
    transform: translateY(8px);
    transition: opacity 240ms ease, transform 320ms cubic-bezier(.2,.8,.2,1);
  }

  :global(body.story-meta-visible) .article-cover-source-row {
    opacity: 1;
    transform: translateY(0);
  }

  .article-cover-author {
    min-width: 0;
    display: flex;
    align-items: center;
  }

  .article-cover-author strong {
    color: var(--ink);
    font-size: 16px;
    font-weight: 750;
    line-height: 1.25;
  }

  .article-cover-original {
    min-height: 44px;
    flex: 0 0 auto;
    display: inline-flex;
    align-items: center;
    justify-content: flex-end;
    gap: 6px;
    color: var(--accent);
    font-size: 16px;
    font-weight: 750;
    white-space: nowrap;
  }

  .article-cover-original i {
    font-size: 17px;
  }

  .article-after-cover {
    padding-top: 0;
  }

  :global(body:has(.svelte-article-page) .article-after-cover) {
    padding-top: 0 !important;
  }

  .article-content-layout {
    width: min(100%, 760px);
    margin-inline: auto;
  }

  .article-flow-meta {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 4px 12px;
    margin: 0 0 20px;
    color: var(--muted);
    line-height: 1.4;
  }

  .article-flow-meta time,
  .article-flow-meta span {
    font-size: 14px !important;
  }

  .article-flow-meta span::before {
    content: '•';
    margin-right: 12px;
    color: var(--tertiary);
  }

  .article-reveal {
    opacity: 0;
    visibility: hidden;
    transform: translateY(14px);
    filter: blur(3px);
    transition:
      opacity 260ms ease,
      transform 360ms cubic-bezier(.2,.8,.2,1),
      filter 280ms ease,
      visibility 0s linear 320ms;
  }

  .article-reveal.article-reveal-visible {
    opacity: 1;
    visibility: visible;
    transform: translateY(0);
    filter: blur(0);
    transition-delay: 0s;
  }

  .article-reader {
    min-width: 0;
    width: 100%;
  }

  .article-body-hero {
    margin: 0 0 34px;
  }

  .article-deck-after-cover {
    max-width: 760px;
    margin: 0 0 34px;
    padding-bottom: 30px;
    border-bottom: 1px solid var(--line);
  }

  .inline-article-image img {
    display: block;
    width: 100%;
    height: auto !important;
    max-height: none !important;
    object-fit: contain !important;
    border-radius: var(--radius-md);
    background: var(--gray-6);
  }

  .inline-article-image {
    margin: 30px 0;
  }

  .article-body-hero.inline-article-image {
    margin-top: 0;
  }

  .inline-article-image figcaption {
    margin-top: 8px;
    color: var(--text-tertiary);
    font-size: 14px;
    line-height: 1.4;
  }

  .article-copy,
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
    :global(body:has(.svelte-article-page) .site-header .header-inner) {
      min-height: calc(60px + env(safe-area-inset-top)) !important;
    }

    :global(body:has(.svelte-article-page) .editorial-story .article-cover) {
      min-height: 100svh !important;
      height: 100svh !important;
    }

    .article-cover-media {
      height: 76svh;
    }

    .article-cover-fade-top {
      height: 27%;
    }

    .article-cover-fade-bottom {
      top: 38svh;
      height: 40svh;
    }

    :global(body:has(.svelte-article-page) .editorial-story .article-cover-content) {
      padding-top: calc(82px + env(safe-area-inset-top)) !important;
      padding-bottom: max(112px, calc(92px + env(safe-area-inset-bottom))) !important;
    }

    .article-cover-content h1 {
      font-size: clamp(34px, 9vw, 46px);
      text-wrap: pretty;
    }

    .article-cover-source-row {
      margin-top: 20px;
      gap: 14px;
    }

    .article-cover-author strong,
    .article-cover-original {
      font-size: 14px !important;
    }

    .article-after-cover,
    :global(body:has(.svelte-article-page) .article-after-cover) {
      padding-top: 0 !important;
    }

    .article-content-layout {
      display: block;
      width: 100%;
    }

    .article-flow-meta {
      margin: 0 0 18px;
      padding-top: 0;
      gap: 2px 10px;
    }

    .article-flow-meta span::before {
      margin-right: 10px;
    }

    .article-body-hero {
      margin-bottom: 28px;
    }

    .article-deck-after-cover {
      margin-bottom: 28px;
      padding-bottom: 26px;
      font-size: 18px;
    }
  }

  @media (max-width: 390px) {
    :global(body:has(.svelte-article-page) .editorial-story .article-cover-content) {
      padding-bottom: max(108px, calc(88px + env(safe-area-inset-bottom))) !important;
    }

    .article-cover-source-row {
      align-items: flex-end;
    }

    .article-cover-original span {
      max-width: 110px;
      overflow: hidden;
      text-overflow: ellipsis;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .article-cover-source-row,
    .article-reveal {
      transition: none !important;
    }
  }
</style>
