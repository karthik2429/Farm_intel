// Static host for the built React app (dist/).
// Every request is answered from the uploaded assets; SPA routing is handled by
// the manifest's `spa: true`, which falls back to index.html for unknown paths.
export default {
  async fetch(request, env) {
    return env.ASSETS.fetch(request);
  },
};
