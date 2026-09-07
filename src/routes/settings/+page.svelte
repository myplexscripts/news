<script>
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

<main class="app-page settings-page" id="main-content">
  <section class="shell">
    <header class="app-page-heading">
      <p class="eyebrow">Preferences</p>
      <h1>Settings</h1>
      <p>Choose how Forest City News looks and how stories behave on this device.</p>
    </header>

    <div class="settings-groups">
      <section class="settings-group">
        <h2>Appearance</h2>
        <div class="settings-card">
          <div class="settings-row">
            <div class="settings-row-copy">
              <strong>Theme</strong>
              <span>Choose a light or dark reading experience.</span>
            </div>
            <div class="settings-segmented" aria-label="Theme">
              <button class:selected={$userState.theme === 'light'} type="button" on:click={() => preference('theme', 'light')}>Light</button>
              <button class:selected={$userState.theme === 'dark'} type="button" on:click={() => preference('theme', 'dark')}>Dark</button>
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
                  class={`accent-choice accent-${accent[0]}`}
                  type="button"
                  aria-label={`${accent[1]} accent`}
                  title={accent[1]}
                  on:click={() => preference('accent', accent[0])}
                >
                  {#if $userState.accent === accent[0]}
                    <i class="ph ph-check" aria-hidden="true"></i>
                  {/if}
                </button>
              {/each}
            </div>
          </div>
        </div>
      </section>

      <section class="settings-group">
        <h2>Reading</h2>
        <div class="settings-card">
          <label class="settings-row settings-toggle-row">
            <div class="settings-row-copy">
              <strong>Hide read articles</strong>
              <span>Stories you open will disappear from article lists on this device.</span>
            </div>
            <input
              class="settings-checkbox"
              type="checkbox"
              checked={$userState.hideRead}
              on:change={(event) => preference('hideRead', event.currentTarget.checked)}
            />
          </label>

          <div class="settings-row">
            <div class="settings-row-copy">
              <strong>Read history</strong>
              <span>
                {$userState.readIds.length
                  ? `${$userState.readIds.length} ${$userState.readIds.length === 1 ? 'article' : 'articles'} marked as read.`
                  : 'No articles marked as read.'}
              </span>
            </div>
            <button class="settings-action-button" type="button" disabled={!$userState.readIds.length} on:click={() => clearRead().catch(() => {})}>Clear history</button>
          </div>
        </div>
      </section>

      <section class="settings-group">
        <h2>Data</h2>
        <div class="settings-card">
          <div class="settings-row">
            <div class="settings-row-copy">
              <strong>Clear all data</strong>
              <span>Reset preferences and remove read history, Read Later items and hidden sources.</span>
            </div>
            <button class="settings-action-button" type="button" on:click={clearAll}>Clear all data</button>
          </div>
        </div>
      </section>
    </div>
  </section>
</main>

<style>
  .settings-groups {
    display: grid;
    gap: 30px;
  }

  .settings-group h2 {
    margin: 0 0 10px;
    font-size: 14px;
    color: var(--text-secondary);
  }

  .settings-card {
    border-radius: 18px;
    background: var(--surface-subtle);
    overflow: hidden;
  }

  .settings-row,
  .settings-accent-row {
    min-height: 74px;
    box-sizing: border-box;
    padding: 16px 18px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 20px;
  }

  .settings-row + .settings-row,
  .settings-row + .settings-accent-row,
  .settings-accent-row + .settings-row {
    border-top: 1px solid color-mix(in srgb, var(--text) 9%, transparent);
  }

  .settings-row-copy strong,
  .settings-row-copy span {
    display: block;
  }

  .settings-row-copy strong {
    font-size: 15px;
  }

  .settings-row-copy span {
    margin-top: 3px;
    color: var(--text-tertiary);
    font-size: 12px;
    line-height: 1.35;
  }

  .settings-segmented {
    display: flex;
    padding: 3px;
    border-radius: 10px;
    background: color-mix(in srgb, var(--text) 8%, transparent);
  }

  .settings-segmented button,
  .settings-action-button {
    border: 0;
    border-radius: 8px;
    min-height: 34px;
    padding: 0 13px;
    background: transparent;
    color: var(--text);
    font-weight: 700;
    cursor: pointer;
  }

  .settings-segmented button.selected {
    background: var(--surface);
    box-shadow: 0 1px 5px rgba(0,0,0,.09);
  }

  .settings-action-button {
    color: var(--accent, #34c759);
  }

  .settings-action-button:disabled {
    opacity: .4;
    cursor: default;
  }

  .accent-grid {
    display: grid;
    grid-template-columns: repeat(6, 38px);
    gap: 8px;
  }

  .accent-choice {
    width: 38px;
    height: 38px;
    border: 0;
    border-radius: 50%;
    display: grid;
    place-items: center;
    cursor: pointer;
    color: #000;
    font-size: 17px;
  }

  .accent-choice.selected {
    box-shadow: inset 0 0 0 3px color-mix(in srgb, #fff 85%, transparent);
  }

  .accent-red { background: #ff383c; }
  .accent-orange { background: #ff8d28; }
  .accent-yellow { background: #ffcc00; }
  .accent-green { background: #34c759; }
  .accent-mint { background: #00c8b3; }
  .accent-teal { background: #00c3d0; }
  .accent-cyan { background: #00c0e8; }
  .accent-blue { background: #0088ff; }
  .accent-indigo { background: #6155f5; }
  .accent-purple { background: #cb30e0; }
  .accent-pink { background: #ff2d55; }
  .accent-brown { background: #ac7f5e; }

  .settings-checkbox {
    width: 24px;
    height: 24px;
    accent-color: var(--accent, #34c759);
  }

  @media (max-width: 680px) {
    .settings-row,
    .settings-accent-row {
      align-items: flex-start;
      flex-direction: column;
    }

    .settings-toggle-row {
      flex-direction: row;
      align-items: center;
    }

    .accent-grid {
      grid-template-columns: repeat(6, 36px);
    }

    .accent-choice {
      width: 36px;
      height: 36px;
    }
  }
</style>
