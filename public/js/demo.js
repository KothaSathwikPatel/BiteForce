import { api } from './api.js';
import { h, icon, mount, oneIn } from './dom.js';
import { ACTION_TEXT, LEVELS } from './levels.js';
import { state } from './state.js';

export function renderDemo(body) {
  const cfg = state.config;
  let selected = state.selectedId ?? (state.stalls.find((s) => s.level === 'NONE') || state.stalls[0] || {}).id;
  const result = h('div', { 'aria-live': 'polite' });
  let busy = false;

  const select = h('select', {
    'aria-label': 'Place to simulate',
    onchange: (e) => { selected = Number(e.target.value); },
  }, state.stalls.map((s) => h('option', { value: s.id, selected: s.id === selected }, `${s.name} (${LEVELS[s.level].label})`)));

  async function run(label, fn, done) {
    if (busy) return;
    busy = true;
    mount(result, h('div', { class: 'skeleton' }));
    try {
      const data = await fn();
      await state.refresh();
      done(data);
    } catch (err) {
      mount(result, h('div', { class: 'alert-box', role: 'alert' }, err.message));
    } finally {
      busy = false;
    }
    state.toast(label);
  }

  const AI_NAME = { claude: 'Claude', gemini: 'Gemini', rules: 'Rules engine', 'rules-fallback': 'Rules engine (AI unavailable)' };

  const showSimulation = (data) => {
    const a = data.alert;
    const level = LEVELS[data.stall.level];
    const ai = AI_NAME[a.ai_source] || 'Reviewer';
    const flagged = a.action !== 'none';
    const chance = data.p_value != null ? `, about ${oneIn(data.p_value)} by chance` : '';
    const steps = [
      ['ok', `${data.simulated_cases} simulated people reported illness after eating at ${data.stall.name}.`],
      ['ok', `Statistics: ${data.stall.n_cases} independent reports${chance}. Level: ${level.label}.`],
      a.ai_source
        ? [a.ai_send ? 'ok' : 'warn', `${ai} review: ${a.ai_send ? 'send the report' : 'hold it back'} (confidence ${Math.round(a.ai_confidence * 100)}%).`]
        : ['skip', 'AI review is only needed at Alert level or above.'],
      !flagged
        ? ['skip', 'No email: this level does not warrant an alert.']
        : a.action === 'sent'
          ? ['ok', 'Evidence report emailed to the food safety officer (demo inbox).']
          : ['warn', a.detail || (ACTION_TEXT[a.action] || [a.action])[0]],
    ];
    mount(result,
      h('div', { class: `card lvl-${level.css}`, style: 'margin-top:14px' },
        h('span', { class: 'badge' }, level.label),
        h('ol', { class: 'chain' }, steps.map(([state, text], i) =>
          h('li', { class: `chain-step is-${state}`, style: `animation-delay:${i * 0.5}s` },
            h('span', { class: 'chain-mark', 'aria-hidden': 'true' }, { ok: '\u2713', warn: '!', skip: '\u2013' }[state]),
            h('span', {}, text)))),
        a.ai_reasons && a.ai_reasons.length ? h('ul', { class: 'small muted', style: 'padding-left:18px;margin:10px 0 0' }, a.ai_reasons.map((r) => h('li', {}, r))) : null,
        h('a', { class: 'btn', href: '/officer.html', target: '_blank', rel: 'noopener' }, 'Open the FSSAI officer inbox'),
        h('button', { class: 'btn secondary', type: 'button', onclick: () => state.show('detail', data.stall.id) }, 'Open this place')),
    );
    result.scrollIntoView({ block: 'start', behavior: 'smooth' });
  };

  mount(body, 
    h('div', { class: 'head-row', 'data-drag': true },
      h('button', { class: 'icon-btn', type: 'button', 'aria-label': 'Back to places', onclick: () => state.show('list') }, icon('back'))),
    h('h2', { tabindex: '-1', style: 'margin-top:12px' }, 'Demo tools'),
    h('p', { class: 'sub' }, 'Simulate an outbreak and watch the automatic pipeline run: detection, AI review, then an emailed evidence report.'),
    h('div', { class: 'card', style: 'margin-top:14px' },
      h('div', { class: 'event' }, h('span', { class: 'muted' }, 'Email delivery: '), h('b', {}, cfg.email_configured ? 'connected (demo inbox)' : 'not configured, will only be logged')),
      h('div', { class: 'event' }, h('span', { class: 'muted' }, 'AI reviewer: '), h('b', {}, { claude: 'Claude', gemini: 'Gemini' }[cfg.ai_mode] || 'rules only (no API key)')),
      h('div', { class: 'event' }, h('span', { class: 'muted' }, 'Auto-send: '), h('b', {}, cfg.auto_send ? 'on' : 'off'))),
    h('div', { class: 'field' }, h('label', {}, 'Place'), select),
    h('button', { class: 'btn', type: 'button', onclick: () => run('Simulation complete', () => api.simulate(selected, 6), showSimulation) }, 'Simulate outbreak (6 people)'),
    result,
    h('button', {
      class: 'btn danger', type: 'button',
      onclick: () => run('Demo data reset', () => api.reset(), () => mount(result, h('p', { class: 'small muted' }, 'Demo data reset. Reports and alert history cleared.'))),
    }, 'Reset demo data'),
    h('p', { class: 'note' }, 'Simulated reports are marked as such in the database. Emails sent from demo mode are labelled DEMO.'),
  );
}
