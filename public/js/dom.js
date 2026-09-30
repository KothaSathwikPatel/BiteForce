// Tiny DOM helpers. Everything user-supplied goes through textContent, never innerHTML.
const SVG_NS = 'http://www.w3.org/2000/svg';

export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class') el.className = value;
    else if (key.startsWith('on') && typeof value === 'function') el.addEventListener(key.slice(2).toLowerCase(), value);
    else el.setAttribute(key, value === true ? '' : String(value));
  }
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

export function svg(tag, attrs = {}, ...children) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, String(value));
  for (const child of children) if (child) el.append(child);
  return el;
}

const ICONS = {
  back: 'M15 5l-7 7 7 7',
  close: 'M6 6l12 12M18 6L6 18',
  plus: 'M12 5v14M5 12h14',
  check: 'M5 13l4 4L19 7',
  chevron: 'M9 5l7 7-7 7',
  warning: 'M12 3l10 18H2L12 3z M12 10v4 M12 17.5v.01',
};

export function icon(name, cls = 'icon') {
  return svg('svg', { viewBox: '0 0 24 24', class: cls, 'aria-hidden': 'true' }, svg('path', { d: ICONS[name] }));
}

const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' });

export function timeAgo(iso) {
  const diff = (Date.parse(iso) - Date.now()) / 1000;
  const abs = Math.abs(diff);
  if (abs < 60) return 'just now';
  if (abs < 3600) return rtf.format(Math.round(diff / 60), 'minute');
  if (abs < 86400) return rtf.format(Math.round(diff / 3600), 'hour');
  return rtf.format(Math.round(diff / 86400), 'day');
}

export function fmtTime(isoOrDate) {
  const d = isoOrDate instanceof Date ? isoOrDate : new Date(isoOrDate);
  return new Intl.DateTimeFormat(undefined, { weekday: 'short', hour: 'numeric', minute: '2-digit' }).format(d);
}

export function oneIn(p) {
  if (p === null || p === undefined) return '-';
  if (p >= 0.5) return 'likely';
  const n = Math.round(1 / p);
  if (n >= 1e6) return 'less than 1 in a million';
  return `1 in ${n.toLocaleString()}`;
}

/** Replace an element's children, flattening arrays and skipping null/false (unlike replaceChildren). */
export function mount(el, ...children) {
  const nodes = children
    .flat(Infinity)
    .filter((c) => c !== null && c !== undefined && c !== false)
    .map((c) => (c instanceof Node ? c : document.createTextNode(String(c))));
  el.replaceChildren(...nodes);
}
