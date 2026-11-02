import { createRoot } from 'react-dom/client';
import App from './App.tsx';
import './index.css';

createRoot(document.getElementById('root')!).render(<App />);

// Service worker: production only, so the dev server keeps its fast HMR and
// never serves a stale shell. `?sw=1` forces registration for local testing.
const wantsSW =
  import.meta.env.PROD || new URLSearchParams(window.location.search).has('sw');

if ('serviceWorker' in navigator && wantsSW) {
  window.addEventListener('load', () => {
    navigator.serviceWorker
      .register('/sw.js')
      .catch((err) => console.warn('[pwa] service worker registration failed', err));
  });
}
