import adapter from '@sveltejs/adapter-static';

const rawBase = process.env.BASE_PATH || '';
const base = rawBase === '/' ? '' : rawBase.replace(/\/$/, '');

export default {
  kit: {
    adapter: adapter({
      pages: 'dist',
      assets: 'dist',
      fallback: '404.html'
    }),
    paths: {
      base
    },
    prerender: {
      handleHttpError: 'warn'
    }
  }
};
