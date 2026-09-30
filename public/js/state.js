// Shared UI state. app.js wires the functions in at start-up (avoids circular imports).
export const state = {
  config: null,
  stalls: [],
  account: null, // {name} when signed in with Google
  user: null, // {lat, lng} once the browser grants location
  map: null,
  sheet: null,
  view: 'list',
  selectedId: null,
  filter: 'all',
  query: '',
  show: () => {},
  toast: () => {},
  refresh: async () => {},
};
