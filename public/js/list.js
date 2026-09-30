import { h, icon, mount } from './dom.js';
import { KINDS, LEVELS } from './levels.js';
import { state } from './state.js';

const FILTERS = [
  ['all', 'All'],
  ['alerts', 'Alerts'],
  ['street_food', 'Street food'],
  ['restaurant', 'Restaurants'],
  ['tea_snack', 'Tea & snacks'],
];

export function visibleStalls() {
  const q = state.query.trim().toLowerCase();
  return state.stalls
    .filter((s) => {
      if (q && !`${s.name} ${KINDS[s.kind] || ''}`.toLowerCase().includes(q)) return false;
      if (state.filter === 'alerts') return s.level_value >= 2;
      if (state.filter !== 'all') return s.kind === state.filter;
      return true;
    })
    .sort((a, b) => b.level_value - a.level_value || a.name.localeCompare(b.name));
}

function statusText(s) {
  if (s.level === 'NONE') return 'No recent reports';
  return `${LEVELS[s.level].label} · ${s.n_cases} ${s.n_cases === 1 ? 'report' : 'reports'}`;
}

let listEl = null;
let summaryEl = null;

export function fillList() {
  if (!listEl) return;
  const rows = visibleStalls();
  mount(listEl, 
    ...(rows.length
      ? rows.map((s) =>
          h('li', {}, h('button', { class: `row lvl-${LEVELS[s.level].css}${s.kind === 'restaurant' ? '' : ' kind-square'}`, type: 'button', onclick: () => state.show('detail', s.id) },
            h('span', { class: 'dot', 'aria-hidden': 'true' }),
            h('span', { class: 'row-main' },
              h('div', { class: 'row-title' }, s.name),
              h('div', { class: 'row-sub' }, `${KINDS[s.kind] || 'Place'} · ${statusText(s)}`)),
            icon('chevron', 'icon chev'))))
      : [h('li', { class: 'muted small', style: 'padding:16px' }, 'No places match.')]),
  );
  const active = state.stalls.filter((s) => s.level_value >= 2).length;
  if (summaryEl) {
    summaryEl.textContent = active
      ? `${active} ${active === 1 ? 'place has' : 'places have'} an active alert`
      : 'No active alerts right now';
  }
}

export function renderList(body) {
  const worst = state.stalls.filter((s) => s.level === 'OUTBREAK' && s.active).sort((a, b) => b.n_cases - a.n_cases)[0];
  summaryEl = h('p', { class: 'sub' });
  listEl = h('ul', { class: 'list', 'aria-label': 'Food places' });

  mount(body, 
    h('div', { class: 'head', 'data-drag': true },
      h('h1', { tabindex: '-1' }, 'Shamshabad'),
      summaryEl),
    worst
      ? h('button', { class: 'banner', type: 'button', onclick: () => state.show('detail', worst.id) },
          icon('warning'), h('span', {}, `Possible outbreak: ${worst.name}`))
      : null,
    h('div', { class: 'chips', role: 'group', 'aria-label': 'Filter places' },
      FILTERS.map(([key, label]) =>
        h('button', {
          class: 'chip', type: 'button', 'aria-pressed': String(state.filter === key),
          onclick: (e) => {
            state.filter = key;
            for (const chip of e.currentTarget.parentElement.children) chip.setAttribute('aria-pressed', String(chip === e.currentTarget));
            fillList();
          },
        }, label))),
    listEl,
    h('p', { class: 'note' },
      'All places shown are fictional demo data. BiteTrace never says a place is safe or guilty. ',
      'It flags patterns: several unrelated people who got sick after eating in the same place. ',
      'Map © OpenStreetMap contributors © CARTO.'),
  );
  fillList();
}
