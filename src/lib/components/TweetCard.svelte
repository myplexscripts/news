<script>
  export let block;

  let videoActive = false;

  $: photos = Array.isArray(block?.photos)
    ? block.photos
        .map((photo) => typeof photo === 'string' ? { url: photo } : photo)
        .filter((photo) => photo?.url)
        .slice(0, 4)
    : [];
  $: handle = String(block?.handle || '').replace(/^@/, '');
  $: displayHandle = handle ? `@${handle}` : 'X';
  $: sourceUrl = block?.source_url || block?.url || '';
  $: videoUrl = block?.video_url || '';
  $: poster = block?.poster || '';
  $: publishedLabel = formatPublished(block?.published);

  function formatPublished(value) {
    if (!value) return '';
    try {
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return '';
      return new Intl.DateTimeFormat('en-CA', {
        timeZone: 'America/Toronto',
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: 'numeric',
        minute: '2-digit'
      }).format(date);
    } catch {
      return '';
    }
  }

  function playVideo() {
    videoActive = true;
  }
</script>

<article class="tweet-card" aria-label="Post on X">
  <header class="tweet-header">
    <div class="tweet-author">
      <div class="tweet-avatar" aria-hidden="true">
        {#if block?.avatar}
          <img src={block.avatar} alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer" />
        {:else}
          <i class="ph ph-user-circle" aria-hidden="true"></i>
        {/if}
      </div>
      <div class="tweet-author-copy">
        {#if block?.author_name}<strong>{block.author_name}</strong>{/if}
        <span>{displayHandle}</span>
      </div>
    </div>
    <span class="tweet-x-mark" aria-hidden="true">X</span>
  </header>

  {#if block?.text}
    <p class="tweet-text">{block.text}</p>
  {/if}

  {#if videoUrl}
    <div class="tweet-video">
      {#if videoActive}
        <video controls autoplay playsinline preload="none" poster={poster || undefined} src={videoUrl}></video>
      {:else}
        <button class="tweet-video-play" type="button" on:click={playVideo} aria-label="Play video from this post">
          {#if poster}
            <img src={poster} alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer" />
          {/if}
          <span class="tweet-play-button" aria-hidden="true"><i class="ph-fill ph-play"></i></span>
        </button>
      {/if}
    </div>
  {:else if photos.length}
    <div class={`tweet-photos tweet-photos-${photos.length}`}>
      {#each photos as photo, index}
        <img
          src={photo.url}
          alt={photo.alt || `Image ${index + 1} from this post`}
          width={photo.width || undefined}
          height={photo.height || undefined}
          loading="lazy"
          decoding="async"
          referrerpolicy="no-referrer"
        />
      {/each}
    </div>
  {/if}

  <footer class="tweet-footer">
    {#if publishedLabel}<time datetime={block.published}>{publishedLabel}</time>{/if}
    {#if sourceUrl}
      <a href={sourceUrl} target="_blank" rel="noopener noreferrer">
        View on X <i class="ph ph-arrow-up-right" aria-hidden="true"></i>
      </a>
    {/if}
  </footer>
</article>

<style>
  .tweet-card {
    width: 100%;
    margin: 30px 0;
    padding: 18px;
    border-radius: 20px;
    background: var(--surface-subtle);
    color: var(--text, var(--ink));
  }

  .tweet-header,
  .tweet-author,
  .tweet-footer {
    display: flex;
    align-items: center;
  }

  .tweet-header {
    justify-content: space-between;
    gap: 16px;
  }

  .tweet-author {
    min-width: 0;
    gap: 11px;
  }

  .tweet-avatar {
    width: 44px;
    height: 44px;
    min-width: 44px;
    display: grid;
    place-items: center;
    overflow: hidden;
    border-radius: 50%;
    background: var(--surface);
    color: var(--muted);
  }

  .tweet-avatar img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .tweet-avatar i {
    font-size: 28px;
  }

  .tweet-author-copy {
    min-width: 0;
    display: grid;
    line-height: 1.2;
  }

  .tweet-author-copy strong {
    overflow: hidden;
    color: var(--text, var(--ink));
    font-size: 16px;
    font-weight: 750;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .tweet-author-copy span {
    overflow: hidden;
    color: var(--muted);
    font-size: 14px;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .tweet-x-mark {
    flex: 0 0 auto;
    color: var(--text, var(--ink));
    font-size: 21px;
    font-weight: 800;
    line-height: 1;
  }

  .tweet-text {
    margin: 16px 0 0 !important;
    color: var(--text, var(--ink)) !important;
    font-size: 18px !important;
    line-height: 1.5 !important;
    white-space: pre-wrap;
  }

  .tweet-photos,
  .tweet-video {
    margin-top: 16px;
    overflow: hidden;
    border-radius: 16px;
    background: var(--gray-6);
  }

  .tweet-photos {
    display: grid;
    gap: 2px;
  }

  .tweet-photos-1 {
    grid-template-columns: 1fr;
  }

  .tweet-photos-2,
  .tweet-photos-3,
  .tweet-photos-4 {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .tweet-photos-3 img:first-child {
    grid-row: span 2;
  }

  .tweet-photos img {
    width: 100%;
    height: 100%;
    min-height: 170px;
    max-height: 360px;
    object-fit: cover;
  }

  .tweet-video {
    position: relative;
    aspect-ratio: 16 / 9;
  }

  .tweet-video video,
  .tweet-video-play,
  .tweet-video-play > img {
    width: 100%;
    height: 100%;
  }

  .tweet-video video {
    display: block;
    object-fit: contain;
    background: #000;
  }

  .tweet-video-play {
    position: relative;
    display: grid;
    place-items: center;
    padding: 0;
    border: 0;
    background: var(--gray-6);
    cursor: pointer;
  }

  .tweet-video-play > img {
    position: absolute;
    inset: 0;
    object-fit: cover;
  }

  .tweet-play-button {
    position: relative;
    z-index: 1;
    width: 52px;
    height: 52px;
    display: grid;
    place-items: center;
    border-radius: 50%;
    background: rgb(0 0 0 / 0.72);
    color: #fff;
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
  }

  .tweet-play-button i {
    margin-left: 2px;
    font-size: 24px;
  }

  .tweet-footer {
    min-height: 44px;
    justify-content: space-between;
    gap: 16px;
    margin-top: 10px;
    color: var(--muted);
    font-size: 14px;
  }

  .tweet-footer time {
    min-width: 0;
    font-size: 14px;
  }

  .tweet-footer a {
    flex: 0 0 auto;
    min-height: 44px;
    display: inline-flex;
    align-items: center;
    gap: 5px;
    color: var(--accent);
    font-size: 14px;
    font-weight: 700;
  }

  .tweet-footer a i {
    font-size: 16px;
  }

  @media (max-width: 760px) {
    .tweet-card {
      margin: 24px 0;
      padding: 16px;
      border-radius: 18px;
    }

    .tweet-text {
      font-size: 17px !important;
    }

    .tweet-photos img {
      min-height: 128px;
      max-height: 280px;
    }
  }
</style>
