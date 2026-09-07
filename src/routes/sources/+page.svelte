<script>
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { base } from '$app/paths';

  onMount(() => {
    goto(`${base}/sections/`, { replaceState: true });
  });
</script>

<svelte:head>
  <title>Sources | Forest City News</title>
</svelte:head>

<main class="app-page" id="main-content">
  <div class="shell">
    <div class="app-empty">Opening Sections…</div>
  </div>
</main>
