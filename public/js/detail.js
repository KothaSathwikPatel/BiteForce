import { api } from './api.js';
import { fmtTime, h, icon, mount, oneIn, svg, timeAgo } from './dom.js';
import { ACTION_TEXT, KINDS, LEVELS, SYMPTOM_LABEL } from './levels.js';
import { state } from './state.js';

function timelineChart(d) {
  const rows = d.timeline;
  if (!rows.length) return null;
  const times = rows.flatMap((r) => [Date.parse(r.eaten_at), Date.parse(r.onset_at)]);
  const min = Math.min(...times);
  const span = Math.max(Math.max(...times) - min, 1);
  const W = 320;
  const pad = 12;
  const rowH = 18;
  const x = (t) => pad + ((t - min) / span) * (W - 2 * pad);
  const parts = rows.flatMap((r, i) => {
    const y = 10 + i * rowH;
    const a = x(Date.parse(r.eaten_at));
    const b = x(Date.parse(r.onset_at));
    return [
      svg('line', { class: 'tl-line', x1: a, y1: y, x2: b, y2: y }),
      svg('circle', { class: 'tl-meal', cx: a, cy: y, r: 4 }),
      svg('circle', { class: 'tl-onset', cx: b, cy: y, r: 5 }),
    ];
  });
  return svg('svg', {
    class: 'tl', viewBox: `0 0 ${W} ${rows.length * rowH + 6}`, role: 'img',
    'aria-label': `Timeline of ${rows.length} cases, each from the meal to the start of symptoms`,
  }, ...parts);
}

function symptomBars(d) {
  const entries = Object.entries(d.symptom_counts).sort((a, b) => b[1] - a[1]);
  if (!entries.length) return null;
  const top = entries[0][1];
  return entries.map(([key, count]) => {
    const fill = h('i');
    fill.style.width = `${(count / top) * 100}%`;
    return h('div', { class: 'bar-row' }, h('span', {}, SYMPTOM_LABEL[key] || key), h('div', { class: 'bar', 'aria-hidden': 'true' }, fill), h('b', {}, count));
  });
}

function eventLog(events) {
  if (!events.length) return null;
  return [
    h('h3', {}, 'Automated escalation'),
    h('div', { class: 'card' },
      events.map((e) => {
        const [label, tone] = ACTION_TEXT[e.action] || [e.action, 'warn'];
        const verdict = e.ai_send ? 'recommended sending' : 'recommended holding back';
        return h('div', { class: 'event' },
          h('span', { class: `tag ${tone}` }, label),
          h('span', { class: 'muted' }, `${timeAgo(e.created_at)} · ${LEVELS[e.level].label}, ${e.n_cases} people`),
          h('div', { class: 'small', style: 'margin-top:6px' },
            `Reviewer (${e.ai_source}): ${verdict}` + (e.ai_confidence != null ? `, confidence ${Math.round(e.ai_confidence * 100)}%.` : '.')),
          e.ai_reasons.length ? h('ul', { class: 'small muted', style: 'margin:6px 0 0;padding-left:18px' }, e.ai_reasons.map((r) => h('li', {}, r))) : null);
      })),
  ];
}

export async function renderDetail(body, id) {
  mount(body, h('div', { class: 'skeleton' }), h('div', { class: 'skeleton' }), h('div', { class: 'skeleton' }));
  let d;
  try {
    d = await api.stall(id);
  } catch (err) {
    mount(body, 
      h('div', { class: 'head-row' }, h('button', { class: 'icon-btn', type: 'button', 'aria-label': 'Back to places', onclick: () => state.show('list') }, icon('back'))),
      h('p', { class: 'lead' }, err.message));
    return;
  }
  if (state.view !== 'detail' || state.selectedId !== id) return; // user navigated away

  const css = LEVELS[d.level].css;
  mount(body, 
    h('div', { class: `head lvl-${css}`, 'data-drag': true },
      h('div', { class: 'head-row' },
        h('button', { class: 'icon-btn', type: 'button', 'aria-label': 'Back to places', onclick: () => state.show('list') }, icon('back')),
        h('span', { class: 'badge' }, LEVELS[d.level].label + (d.level !== 'NONE' && !d.active ? ' (earlier)' : ''))),
      h('h2', { tabindex: '-1', style: 'margin-top:12px' }, d.name),
      h('p', { class: 'sub' }, `${KINDS[d.kind] || 'Place'}${d.verified ? '' : ' · added by a user'}`)),
    h('p', { class: 'lead' }, d.message),
    d.n_cases > 0
      ? h('div', { class: `stats lvl-${css}` },
          h('div', { class: 'stat' }, h('b', {}, d.n_cases), h('span', {}, 'unrelated people')),
          h('div', { class: 'stat' }, h('b', {}, d.median_incubation_hours != null ? `${d.median_incubation_hours} h` : '-'), h('span', {}, 'median time to symptoms')),
          h('div', { class: 'stat' }, h('b', {}, `${d.exposure_span_hours} h`), h('span', {}, 'spread of meal times')),
          h('div', { class: 'stat' }, h('b', {}, oneIn(d.p_value)), h('span', {}, 'chance this is coincidence')))
      : null,
    d.timeline.length
      ? [h('h3', {}, 'Timeline'),
         h('div', { class: `card lvl-${css}` },
           timelineChart(d),
           h('div', { class: 'legend' },
             h('span', {}, h('i', { style: 'background:var(--muted)' }), 'Ate'),
             h('span', {}, h('i', { style: 'background:var(--lvl-color)' }), 'Symptoms began'),
             h('span', {}, `${fmtTime(d.timeline[0].eaten_at)} to ${fmtTime(d.timeline[d.timeline.length - 1].onset_at)}`)))]
      : null,
    Object.keys(d.symptom_counts).length ? [h('h3', {}, 'Symptoms reported'), h('div', { class: 'card' }, symptomBars(d))] : null,
    d.reasons.length
      ? [h('h3', {}, 'Why this level?'),
         h('details', {}, h('summary', {}, 'How BiteTrace decided'), h('ul', {}, d.reasons.map((r) => h('li', {}, r))))]
      : null,
    eventLog(d.events),
    h('button', { class: 'btn', type: 'button', onclick: () => state.show('report', id) }, 'I got sick after eating here'),
    h('p', { class: 'note' },
      'Reports are anonymous. This is a screening signal from crowdsourced data, not a diagnosis or a finding of fault. ',
      'Only a laboratory test can confirm the cause of an outbreak.'),
  );
  body.querySelector('h2')?.focus({ preventScroll: true });
}
