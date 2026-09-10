<script>
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import NewsCard from '$lib/components/NewsCard.svelte';
  import { loadFeed, scopeForStory, sortNewest } from '$lib/newsData';
  import { userState } from '$lib/appState';

  const preferredCategories = [
    'Public Safety',
    'City Hall',
    'Business',
    'Traffic',
    'Education',
    'Health',
    'Community',
    'Sports'
  ];

  const groupLabels = {
    today: 'Today',
    yesterday: 'Yesterday',
    'two-days-ago': 'Two Days Ago',
    earlier: 'Earlier'
  };

  const CAROUSEL_DELAY_MS = 7000;

  let feed;
  let error = '';
  let activeScope = 'local';
  let activeCategory = 'All';
  let activeSlide = 0;
  let dragStartX = null;
  let dragDelta = 0;
  let carouselPaused = false;
  let carouselTimer = null;

  function clearCarouselTimer() {
    if (carouselTimer === null || typeof window === 'undefined') return;
    window.clearTimeout(carouselTimer);
    carouselTimer = null;
  }

  function scheduleCarouselAdvance() {
    if (typeof window === 'undefined') return;
    clearCarouselTimer();
    carouselTimer = window.setTimeout(() => {
      carouselTimer = null;
      if (!carouselPaused && !document.hidden && topStories.length > 1) {
        setSlide(activeSlide + 1);
      }
      scheduleCarouselAdvance();
    }, CAROUSEL_DELAY_MS);
  }

  function resetCarouselTimer() {
    scheduleCarouselAdvance();
  }

  onMount(() => {
    let cancelled = false;

    try {
      const storedScope = localStorage.getItem('london-news-home-feed');
      if (['local', 'canada', 'all'].includes(storedScope || '')) activeScope = storedScope;
    } catch {}

    loadFeed().then((nextFeed) => {
      if (!cancelled) feed = nextFeed;
    }).catch((reason) => {
      if (!cancelled) error = reason instanceof Error ? reason.message : 'Unable to load the latest news.';
    });

    const handleVisibilityChange = () => {
      if (document.hidden) clearCarouselTimer();
      else scheduleCarouselAdvance();
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    scheduleCarouselAdvance();

    return () => {
      cancelled = true;
      clearCarouselTimer();
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  });

  function setScope(scope) {
    activeScope = scope;
    activeSlide = 0;
    resetCarouselTimer();
    try { localStorage.setItem('london-news-home-feed', scope); } catch {}
  }

  function categoryClass(category = 'Local') {
    return `category-${String(category).toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;
  }

  function localDateKey(value) {
    try {
      const parts = new Intl.DateTimeFormat('en-CA', {
        timeZone: 'America/Toronto',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit'
      }).formatToParts(new Date(value));
      const values = Object.fromEntries(parts.filter((part) => part.type !== 'literal').map((part) => [part.type, part.value]));
      return `${values.year}-${values.month}-${values.day}`;
    } catch {
      return '1970-01-01';
    }
  }

  function dayNumber(key) {
    const [year, month, day] = key.split('-').map(Number);
    return Math.floor(Date.UTC(year, month - 1, day) / 86400000);
  }

  function groupKeyFor(value, reference) {
    const diff = dayNumber(localDateKey(reference)) - dayNumber(localDateKey(value));
    if (diff <= 0) return 'today';
    if (diff === 1) return 'yesterday';
    if (diff === 2) return 'two-days-ago';
    return 'earlier';
  }

  function setCategory(category) {
    activeCategory = category;
    activeSlide = 0;
    resetCarouselTimer();
  }

  function setSlide(index) {
    const count = topStories.length;
    if (!count) {
      activeSlide = 0;
      return;
    }
    activeSlide = ((index % count) + count) % count;
  }

  function selectCarouselSlide(index) {
    setSlide(index);
    resetCarouselTimer();
  }

  function carouselPointerDown(event) {
    if (topStories.length < 2) return;
    dragStartX = event.clientX;
    dragDelta = 0;
    carouselPaused = true;
    clearCarouselTimer();
    event.currentTarget?.setPointerCapture?.(event.pointerId);
  }

  function carouselPointerMove(event) {
    if (dragStartX === null) return;
    dragDelta = event.clientX - dragStartX;
  }

  function carouselPointerUp() {
    if (dragStartX === null) return;
    if (Math.abs(dragDelta) >= 44) setSlide(activeSlide + (dragDelta < 0 ? 1 : -1));
    dragStartX = null;
    dragDelta = 0;
    carouselPaused = false;
    resetCarouselTimer();
  }

  function carouselPointerEnter() {
    carouselPaused = true;
    clearCarouselTimer();
  }

  function carouselPointerLeave() {
    if (dragStartX !== null) {
      carouselPointerUp();
      return;
    }
    carouselPaused = false;
    resetCarouselTimer();
  }

  $: requestedSection = $page.url.searchParams.get('section');
  $: if (requestedSection && requestedSection !== activeCategory) {
    activeCategory = requestedSection;
    activeSlide = 0;
  }

  $: sourceHealth = feed?.source_health || {};
  $: hiddenSources = new Set(($userState.hiddenSources || []).map((value) => String(value).toLowerCase()));
  $: readIds = new Set(($userState.readIds || []).map(String));

  $: allStories = feed
    ? sortNewest((feed.stories || [])
        .filter((story) => story?.cluster_representative !== false)
        .map((story) => ({ ...story, scope: scopeForStory(story, sourceHealth) })))
    : [];

  $: discoveredCategories = [...new Set(allStories.map((story) => story.category).filter(Boolean))]
    .filter((category) => !['Local', 'Canada'].includes(category));

  $: orderedCategories = [
    ...preferredCategories.filter((category) => discoveredCategories.includes(category)),
    ...discoveredCategories.filter((category) => !preferredCategories.includes(category)).sort()
  ];

  $: primaryCategories = orderedCategories.slice(0, 4);
  $: moreCategories = orderedCategories.slice(4);

  $: filteredStories = allStories.filter((story) => {
    const sources = Array.isArray(story.cluster_sources) && story.cluster_sources.length
      ? story.cluster_sources
      : [story.source].filter(Boolean);
    const allHidden = sources.length > 0 && sources.every((source) => hiddenSources.has(String(source).toLowerCase()));
    if (allHidden) return false;
    if ($userState.hideRead && readIds.has(String(story.id))) return false;
    if (activeScope !== 'all' && story.scope !== activeScope) return false;
    if (activeCategory !== 'All' && story.category !== activeCategory) return false;
    return true;
  });

  $: topStories = filteredStories.slice(0, 3);
  $: if (activeSlide >= topStories.length && topStories.length > 0) activeSlide = 0;
  $: timelineStories = filteredStories.slice(3, 93);
  $: referenceDate = feed?.generated_at || new Date().toISOString();
  $: dateGroups = ['today', 'yesterday', 'two-days-ago', 'earlier']
    .map((key) => ({
      key,
      label: groupLabels[key],
      stories: timelineStories.filter((story) => groupKeyFor(story.cluster_latest_published || story.published, referenceDate) === key)
    }))
    .filter((group) => group.stories.length > 0);
</script>

<svelte:head>
  <title>Forest City News | London, Ontario</title>
  <meta name="description" content="A fast local news reader for London, Ontario and Canada." />
</svelte:head>

<main class="home-page card-home editorial-home" id="main-content">
  <section class="section-nav-wrap card-filter-wrap" aria-label="News filters">
    <div class="shell section-nav-inner card-filter-inner">
      <div class="feed-scope-row">
        <div class="feed-scope-switch" role="group" aria-label="Choose home feed">
          <button class:active={activeScope === 'local'} class="feed-scope-button" type="button" aria-pressed={activeScope === 'local'} on:click={() => setScope('local')}>Local</button>
          <button class:active={activeScope === 'canada'} class="feed-scope-button" type="button" aria-pressed={activeScope === 'canada'} on:click={() => setScope('canada')}>Canada</button>
          <button class:active={activeScope === 'all'} class="feed-scope-button" type="button" aria-pressed={activeScope === 'all'} on:click={() => setScope('all')}>All</button>
        </div>
      </div>

      <div class="section-tabs" role="group" aria-label="Filter by section">
        <button class:active={activeCategory === 'All'} class="section-tab" type="button" aria-pressed={activeCategory === 'All'} on:click={() => setCategory('All')}>Latest</button>
        {#each primaryCategories as category}
          <button
            class:active={activeCategory === category}
            class={`section-tab ${categoryClass(category)}`}
            type="button"
            aria-pressed={activeCategory === category}
            on:click={() => setCategory(category)}
          >{category}</button>
        {/each}

        {#if moreCategories.length}
          <details class="control-menu section-more">
            <summary>
              <span>{moreCategories.includes(activeCategory) ? activeCategory : 'More'}</span>
              <i class="ph ph-caret-down" aria-hidden="true"></i>
            </summary>
            <div class="control-popover section-popover">
              {#each moreCategories as category}
                <button
                  class:active-filter={activeCategory === category}
                  class={`control-menu-item ${categoryClass(category)}`}
                  type="button"
                  on:click={() => setCategory(category)}
                >
                  <span class="section-color" aria-hidden="true"></span>
                  <span>{category}</span>
                </button>
              {/each}
            </div>
          </details>
        {/if}
      </div>
    </div>
  </section>

  {#if error}
    <div class="shell home-state-wrap"><div class="app-error">{error}</div></div>
  {:else if !feed}
    <div class="app-loading-grid" aria-label="Loading news">
      <div class="app-skeleton"></div>
      <div class="app-skeleton"></div>
      <div class="app-skeleton"></div>
    </div>
  {:else if filteredStories.length === 0}
    <div class="shell home-state-wrap"><div class="app-empty">No stories match these filters right now.</div></div>
  {:else}
    <section class="editorial-front shell" aria-labelledby="today-heading">
      <div class="editorial-home-heading">
        <div><h2 id="today-heading">Today</h2></div>
      </div>

      <div class="editorial-front-grid editorial-carousel-ready">
        <div
          class="editorial-carousel-viewport"
          role="region"
          aria-roledescription="carousel"
          aria-label="Top stories"
          on:pointerdown={carouselPointerDown}
          on:pointermove={carouselPointerMove}
          on:pointerup={carouselPointerUp}
          on:pointercancel={carouselPointerUp}
          on:pointerenter={carouselPointerEnter}
          on:pointerleave={carouselPointerLeave}
        >
          <div class:dragging={dragStartX !== null} class="editorial-carousel-track" style={`transform:translate3d(-${activeSlide * 100}%,0,0);`}>
            {#each topStories as story, index (story.id)}
              <div class="editorial-carousel-slide" aria-hidden={index !== activeSlide}>
                <NewsCard
                  {story}
                  {index}
                  variant="featured"
                  className="editorial-carousel-card"
                  homeLazy={true}
                />
              </div>
            {/each}
          </div>
        </div>

        {#if topStories.length > 1}
          <div class="editorial-carousel-dots" aria-label="Choose top story">
            {#each topStories as story, index (story.id)}
              <button
                class:active={activeSlide === index}
                class="editorial-carousel-dot"
                type="button"
                aria-label={`Show top story ${index + 1} of ${topStories.length}`}
                aria-current={activeSlide === index ? 'true' : undefined}
                on:click={() => selectCarouselSlide(index)}
              ></button>
            {/each}
          </div>
        {/if}
      </div>
    </section>

    {#if timelineStories.length}
      <section class="news-card-section shell editorial-timeline" id="latest" aria-labelledby="latest-heading">
        <header class="news-card-section-header editorial-home-heading">
          <div><h2 id="latest-heading">Latest</h2></div>
        </header>

        <div class="news-card-grid" id="newsCardGrid">
          {#each dateGroups as group}
            <header class="story-date-heading" data-date-heading={group.key}>
              <h2>{group.label}</h2>
            </header>
            {#each group.stories as story, index (story.id)}
              <NewsCard
                {story}
                index={index + 3}
                variant="standard"
                dateGroup={group.key}
                homeLazy={true}
              />
            {/each}
          {/each}
        </div>
      </section>
    {/if}
  {/if}
</main>

<style>
  .home-state-wrap {
    padding-top: 34px;
    padding-bottom: 34px;
  }

  .editorial-carousel-viewport {
    touch-action: pan-y;
  }

  .editorial-carousel-track.dragging {
    transition: none !important;
  }
</style>
