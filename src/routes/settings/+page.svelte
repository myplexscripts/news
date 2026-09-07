<script>
  import Icon from '$lib/components/Icon.svelte';
  import {
    clearEverything,
    clearRead,
    setAppPreference,
    userState
  } from '$lib/appState';

  const accents = [
    ['red', 'Red'],
    ['orange', 'Orange'],
    ['yellow', 'Yellow'],
    ['green', 'Green'],
    ['mint', 'Mint'],
    ['teal', 'Teal'],
    ['cyan', 'Cyan'],
    ['blue', 'Blue'],
    ['indigo', 'Indigo'],
    ['purple', 'Purple'],
    ['pink', 'Pink'],
    ['brown', 'Brown']
  ];

  async function preference(key, value) {
    await setAppPreference(key, value).catch(() => {});
  }

  async function clearAll() {
    if (!confirm('Clear all Forest City News data from this device? This cannot be undone.')) return;
    await clearEverything().catch(() => {});
  }
</script>

<svelte:head>
  <title>Settings | Forest City News</title>
  <meta name="description" content="Customize Forest City News appearance and reading preferences." />
</svelte:head>

<main class="settings-page" id="main-content">
  <section class="settings-shell shell">
    <header class="page-heading settings-heading directory-heading">
      <div class="page-heading-copy">
        <p class="masthead-label">Preferences</p>
        <h1>Settings</h1>
        <p class="page-heading-description">Choose how Forest City News looks and how stories behave on this device.</p>
      </div>
    </header>

    <div class="settings-groups">
      <section class="settings-group" aria-labelledby="appearance-heading">
        <h2 id="appearance-heading">Appearance</h2>
        <div class="settings-card">
          <div class="settings-row">
            <div class="settings-row-copy">
              <strong>Theme</strong>
              <span>Choose a light or dark reading experience.</span>
            </div>
            <div class="settings-segmented" aria-label="Theme">
              <button class:selected={$userState.theme === 'light'} type="button" aria-pressed={$userState.theme === 'light'} on:click={() => preference('theme', 'light')}>Light</button>
              <button class:selected={$userState.theme === 'dark'} type="button" aria-pressed={$userState.theme === 'dark'} on:click={() => preference('theme', 'dark')}>Dark</button>
            </div>
          </div>

          <div class="settings-accent-row">
            <div class="settings-row-copy">
              <strong>Accent colour</strong>
              <span>Used for controls, publisher names and interface highlights.</span>
            </div>
            <div class="accent-grid" aria-label="Accent colour">
              {#each accents as accent}
                <button
                  class:selected={$userState.accent === accent[0]}
                  class="accent-choice"
                  type="button"
                  aria-label={`${accent[1]} accent`}
                  aria-pressed={$userState.accent === accent[0]}
                  title={accent[1]}
                  style={`--swatch:var(--${accent[0]});`}
                  on:click={() => preference('accent', accent[0])}
                >
                  <Icon name="check" size={22} strokeWidth={2.5} />
                </button>
              {/each}
            </div>
          </div>
        </div>
      </section>

      <section class="settings-group" aria-labelledby="reading-heading">
        <h2 id="reading-heading">Reading</h2>
        <div class="settings-card">
          <div class="settings-row settings-toggle-row">
            <div class="settings-row-copy">
              <strong>Hide read articles</strong>
              <span>Stories you open will disappear from article lists on this device.</span>
            </div>
            <label class="settings-switch">
              <span class="visually-hidden">Hide read articles</span>
              <input
                type="checkbox"
                checked={$userState.hideRead}
                on:change={(event) => preference('hideRead', event.currentTarget.checked)}
              />
              <span class="settings-switch-track" aria-hidden="true"></span>
            </label>
          </div>

          <div class="settings-row">
            <div class="settings-row-copy">
              <strong>Read history</strong>
              <span>
                {$userState.readIds.length
                  ? `${$userState.readIds.length} ${$userState.readIds.length === 1 ? 'article' : 'articles'} marked as read on this device.`
                  : 'No articles marked as read.'}
              </span>
            </div>
            <button class="settings-action-button" type="button" disabled={!$userState.readIds.length} on:click={() => clearRead().catch(() => {})}>Clear history</button>
          </div>
        </div>
        <p class="settings-footnote">Reading history and these preferences are stored only in this browser. They are not tied to an account.</p>
      </section>

      <section class="settings-group" aria-labelledby="data-heading">
        <h2 id="data-heading">Data</h2>
        <div class="settings-card">
          <div class="settings-row">
            <div class="settings-row-copy">
              <strong>Clear all data</strong>
              <span>Reset preferences and remove read history, Read Later items and hidden sources from this device.</span>
            </div>
            <button class="settings-action-button" type="button" on:click={clearAll}>Clear all data</button>
          </div>
        </div>
      </section>
    </div>
  </section>
</main>

<style>
  .settings-page .accent-choice,
  :global(html[data-theme='dark']) .settings-page .accent-choice {
    width: 48px !important;
    min-width: 48px !important;
    max-width: 48px !important;
    height: 48px !important;
    min-height: 48px !important;
    padding: 0 !important;
    border: 0 !important;
    border-radius: 50% !important;
    background: var(--swatch) !important;
    box-shadow: none !important;
    display: grid !important;
    place-items: center !important;
    justify-self: center !important;
    aspect-ratio: 1 / 1;
  }

  .settings-page .accent-choice::before,
  .settings-page .accent-choice::after {
    content: none !important;
    display: none !important;
  }

  .settings-page .accent-choice :global(.lucide-icon) {
    opacity: 0;
    color: #000 !important;
    transition: opacity 160ms ease, transform 180ms cubic-bezier(0.22, 1, 0.36, 1);
    transform: scale(0.8);
  }

  .settings-page .accent-choice.selected,
  :global(html[data-theme='dark']) .settings-page .accent-choice.selected {
    outline: 0 !important;
    box-shadow: 0 0 0 3px var(--surface), 0 0 0 5px var(--swatch) !important;
  }

  .settings-page .accent-choice.selected :global(.lucide-icon) {
    opacity: 1;
    transform: scale(1);
  }

  @media (max-width: 760px) {
    .settings-page .accent-grid {
      display: grid !important;
      grid-template-columns: repeat(6, minmax(44px, 1fr)) !important;
      grid-template-rows: repeat(2, 48px) !important;
      gap: 14px 8px !important;
      width: 100% !important;
      align-items: center !important;
      justify-items: center !important;
    }

    .settings-page .accent-choice,
    :global(html[data-theme='dark']) .settings-page .accent-choice {
      width: 44px !important;
      min-width: 44px !important;
      max-width: 44px !important;
      height: 44px !important;
      min-height: 44px !important;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .settings-page .accent-choice :global(.lucide-icon) {
      transition: none !important;
    }
  }
</style>
