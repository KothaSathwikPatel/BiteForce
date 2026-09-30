import { api } from './api.js';
import { fmtTime, h, mount, timeAgo } from './dom.js';
import { LEVELS } from './levels.js';

const ACTION = {
  sent: ['Report received', 'ok'],
  held: ['Held back by AI review', 'warn'],
  skipped_no_email: ['Not delivered: email not configured', 'warn'],
  error: ['Delivery failed', 'warn'],
};
const REVIEWER = { claude: 'Claude', gemini: 'Gemini', rules: 'Rules engine', 'rules-fallback': 'Rules engine (fallback)' };

function card(e) {
  const level = LEVELS[e.level] || LEVELS.NONE;
  const [label, tone] = ACTION[e.action];
  const verdict = e.ai_source
    ? `${REVIEWER[e.ai_source] || 'Reviewer'}: ${e.ai_send ? 'send' : 'hold back'}, confidence ${Math.round((e.ai_confidence || 0) * 100)}%`
    : null;
  return h('article', { class: `mail lvl-${level.css}` },
    h('div', { class: 'mail-top' },
      h('span', { class: 'badge' }, level.label),
      h('time', { class: 'small muted', datetime: e.created_at, title: fmtTime(e.created_at) }, timeAgo(e.created_at))),
    h('h2', { class: 'mail-title' }, e.stall_name),
    h('p', { class: 'small' }, `${e.n_cases} independent illness reports in the same window`),
    h('p', {}, h('span', { class: `tag ${tone === 'warn' ? 'warn' : ''}` }, label), verdict ? h('span', { class: 'small muted' }, verdict) : null),
    e.ai_reasons && e.ai_reasons.length ? h('ul', { class: 'small muted mail-reasons' }, e.ai_reasons.slice(0, 4).map((r) => h('li', {}, r))) : null,
    h('a', { class: 'small', href: `/#stall=${e.stall_id}` }, 'View on the map'));
}

async function refresh() {
  const live = document.getElementById('live');
  try {
    const events = (await api.alerts(50)).filter((e) => ACTION[e.action]);
    const received = events.filter((e) => e.action === 'sent').length;
    mount(document.getElementById('counts'), `${received} received, ${events.length - received} held or not delivered`);
    mount(document.getElementById('inbox'), events.length
      ? events.map(card)
      : h('p', { class: 'muted' }, 'No alerts yet. When BiteTrace confirms a possible outbreak, the report appears here.'));
    live.classList.remove('is-off');
  } catch {
    live.classList.add('is-off');
  }
}

refresh();
setInterval(() => { if (!document.hidden) refresh(); }, 8000);
