<script>
  import { base } from '$app/paths';
  import { navigating } from '$app/stores';
  export let currentPath = '/';

  const tabs = [
    { path: '/', label: 'Home', icon: 'house' },
    { path: '/sections/', label: 'Sections', icon: 'hard-drives' },
    { path: '/read-later/', label: 'Saved', icon: 'bookmark-simple' },
    { path: '/search/', label: 'Search', icon: 'magnifying-glass' },
    { path: '/settings/', label: 'Settings', icon: 'gear-six' }
  ];
  function indexFor(path) {
    if (/^\/(sections|sources)(\/|$)/.test(path)) return 1;
    return Math.max(0, tabs.findIndex((tab) => tab.path !== '/' && path.startsWith(tab.path.replace(/\/$/, ''))));
  }
  $: destination = $navigating?.to?.url.pathname;
  $: selected = indexFor(destination ? destination.slice(base.length) || '/' : currentPath);

  function repeatTab(event, path) {
    if (currentPath !== path || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    window.scrollTo({ top: 0, behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
  }
</script>

<nav class="app-navigation" aria-label="Primary navigation" data-sveltekit-preload-code="viewport" data-sveltekit-preload-data="hover">
  <span class="selection" style:transform={`translateX(${selected * 100}%)`} aria-hidden="true"></span>
  {#each tabs as tab, index}
    <a href={`${base}${tab.path}`} class:selected={selected === index} aria-current={indexFor(currentPath) === index ? 'page' : undefined} on:click={(event) => repeatTab(event, tab.path)}>
      <i class={`${selected === index ? 'ph-fill' : 'ph'} ph-${tab.icon}`} aria-hidden="true"></i>
      <span>{tab.label}</span>
    </a>
  {/each}
</nav>

<style>
  .app-navigation {
    position: fixed;
    z-index: 110;
    inset: auto max(12px, env(safe-area-inset-right)) calc(10px + env(safe-area-inset-bottom)) max(12px, env(safe-area-inset-left));
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    height: 68px;
    padding: 5px;
    border: 1px solid color-mix(in srgb, var(--ink) 10%, transparent);
    border-radius: 26px;
    background: var(--surface);
    isolation: isolate;
  }
  @supports (backdrop-filter: blur(1px)) {
    .app-navigation {
      background: color-mix(in srgb, var(--surface) 92%, transparent);
      backdrop-filter: blur(20px);
      -webkit-backdrop-filter: blur(20px);
    }
  }
  .selection {
    position: absolute;
    z-index: -1;
    inset: 5px auto 5px 5px;
    width: calc((100% - 10px) / 5);
    border-radius: 21px;
    background: color-mix(in srgb, var(--accent) 12%, var(--surface));
    transition: transform var(--motion-navigation) var(--ease-app);
    pointer-events: none;
  }
  a {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 3px;
    min-width: 0;
    min-height: 44px;
    border-radius: 21px;
    color: var(--muted);
    text-decoration: none;
    font-size: 14px;
    font-weight: 600;
    line-height: 1.1;
    -webkit-tap-highlight-color: transparent;
    transition: color var(--motion-fast) ease;
    touch-action: manipulation;
  }
  a.selected { color: color-mix(in srgb, var(--accent) 45%, black); }
  :global(html[data-theme='dark']) a.selected { color: color-mix(in srgb, var(--accent) 60%, white); }
  i { font-size: 23px; transition: transform var(--motion-fast) var(--ease-app); }
  a:active i { transform: scale(.9); }
  a:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  @media (min-width: 761px) {
    .app-navigation { inset: auto auto 20px 50%; width: 520px; transform: translateX(-50%); }
    a { flex-direction: row; gap: 7px; }
    i { font-size: 21px; }
  }
  @media (prefers-reduced-motion: reduce) {
    .selection, a, i { transition: none; }
    a:active i { transform: none; }
  }
</style>
