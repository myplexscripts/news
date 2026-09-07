<script>
  import { page } from '$app/stores';
  import { base } from '$app/paths';
</script>

<svelte:head>
  <title>Not found | Forest City News</title>
</svelte:head>

<main class="app-page" id="main-content">
  <div class="shell">
    <div class="app-empty">
      <h1>{$page.status === 404 ? 'Story not found' : 'Something went wrong'}</h1>
      <p>{$page.error?.message || 'This page could not be opened.'}</p>
      <p><a href={`${base}/`}>Return to Forest City News</a></p>
    </div>
  </div>
</main>
