import { updateAccountButton, renderAccount } from './account.js';
import { api, savedAccount } from './api.js';
import { renderDemo } from './demo.js';
import { renderDetail } from './detail.js';
import { h, mount } from './dom.js';
import { fillList, renderList } from './list.js';
import { MapView } from './mapview.js';
import { renderDone, renderReport } from './report.js';
import { Sheet } from './sheet.js';
import { state } from './state.js';

const $ = (id) => document.getElementById(id);
let toastTimer;

function toast(message) {
  const el = $('toast');
  el.textContent = message;
  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), 3500);
}

function show(view, arg) {
  if (state.cleanup) state.cleanup();
  state.cleanup = null;
  state.view = view;
  const body = $('sheet-body');
  body.scrollTop = 0;

  switch (view) {
    case 'detail': {
      state.selectedId = arg;
      state.map.select(arg);
      const stall = state.stalls.find((s) => s.id === arg);
      state.sheet.setDetent('half');
      if (stall) state.map.focus(stall.lat, stall.lng);
      renderDetail(body, arg);
      return;
    }
    case 'report':
      state.sheet.setDetent('half');
      renderReport(body, arg ?? state.selectedId);
      break;
    case 'done':
      state.sheet.setDetent('half');
      renderDone(body, arg);
      break;
    case 'account':
      state.sheet.setDetent('half');
      renderAccount(body);
      break;
    case 'demo':
      state.sheet.setDetent('half');
      renderDemo(body);
      break;
    default:
      state.view = 'list';
      state.selectedId = null;
      state.map.select(null);
      renderList(body);
  }
  requestAnimationFrame(() => body.querySelector('h1, h2')?.focus({ preventScroll: true }));
}

function locate() {
  if (!navigator.geolocation) {
    toast('Location is not available on this device.');
    return;
  }
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      state.user = { lat: pos.coords.latitude, lng: pos.coords.longitude };
      state.map.setUser(state.user.lat, state.user.lng);
      state.map.focus(state.user.lat, state.user.lng, 16);
    },
    () => toast('Location unavailable. Showing Shamshabad.'),
    { enableHighAccuracy: true, timeout: 8000, maximumAge: 60000 },
  );
}

async function main() {
  const [config, stalls] = await Promise.all([api.config(), api.stalls()]);
  state.config = config;
  state.stalls = stalls;
  state.toast = toast;
  state.show = show;
  state.sheet = new Sheet($('sheet'), $('grabber'));
  state.map = new MapView($('map'), config.center, {
    onSelect: (id) => show('detail', id),
    onPin: (latlng) => state.pinHandler && state.pinHandler(latlng),
    insets: () => state.sheet.insets(),
  });
  state.map.setStalls(stalls);
  state.refresh = async () => {
    state.stalls = await api.stalls();
    state.map.setStalls(state.stalls);
    if (state.view === 'list') fillList();
  };

  state.account = savedAccount();
  updateAccountButton();
  $('btn-account').addEventListener('click', () => show('account'));
  const legend = $('legend');
  legend.open = window.matchMedia('(min-width: 900px)').matches;
  $('legend-demo').hidden = !config.demo_mode;
  $('btn-locate').addEventListener('click', locate);
  $('btn-report').addEventListener('click', () => show('report', state.selectedId));
  if (config.demo_mode) {
    $('btn-demo').hidden = false;
    $('btn-demo').addEventListener('click', () => show('demo'));
  }
  const search = $('search');
  search.addEventListener('input', () => {
    state.query = search.value;
    if (state.view !== 'list') show('list');
    else fillList();
  });
  search.addEventListener('focus', () => {
    if (state.view === 'list' && state.sheet.detent === 'peek') state.sheet.setDetent('half');
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && state.view !== 'list') show('list');
  });

  show('list');
  state.map.fitTown(config.center);
  const deepLink = /^#stall=(\d+)$/.exec(location.hash);
  if (deepLink && state.stalls.some((s) => s.id === Number(deepLink[1]))) show('detail', Number(deepLink[1]));
  setInterval(() => {
    if (!document.hidden && state.view === 'list') state.refresh().catch(() => {});
  }, 30000);
}

main().catch((err) => {
  console.error(err);
  mount($('sheet-body'), 
    h('h1', {}, 'BiteTrace'),
    h('p', { class: 'lead' }, 'Could not load data. Please check your connection and reload the page.'),
  );
});
