import { api } from './api.js';
import { fmtTime, h, icon, mount } from './dom.js';
import { GI, KINDS, LEVELS, SYMPTOMS, SYMPTOM_LABEL } from './levels.js';
import { state } from './state.js';

const NAME_OK = /^[\w .,'&()/-]{2,60}$/u;
const STEPS = 4;

function metres(a, b) {
  const rad = (d) => (d * Math.PI) / 180;
  const dLat = rad(b.lat - a.lat);
  const dLng = rad(b.lng - a.lng);
  const x = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLng / 2) ** 2;
  return 2 * 6371000 * Math.asin(Math.sqrt(x));
}

export function renderReport(body, preselectId) {
  const w = {
    step: 0,
    stallId: preselectId ?? null,
    pin: null, // {lat, lng, name, kind}
    hoursAgo: 20,
    gap: 8,
    symptoms: new Set(),
    filter: '',
    error: null,
    busy: false,
    hp: '',
    openedAt: Date.now(),
  };
  let nextBtn = null;
  let pickEl = null;

  const maxGap = () => Math.min(72, w.hoursAgo);
  const hasGI = () => [...w.symptoms].some((s) => GI.has(s));
  const canNext = () => {
    if (w.step === 0) return w.stallId !== null || (w.pin !== null && NAME_OK.test(w.pin.name.trim()));
    if (w.step === 2) return hasGI();
    return true;
  };
  const updateNext = () => {
    if (nextBtn) nextBtn.disabled = !canNext() || w.busy;
  };

  function endPinMode() {
    state.map.disablePinDrop();
    document.getElementById('pin-banner').hidden = true;
    state.pinHandler = null;
  }
  state.cleanup = () => {
    endPinMode();
    state.map.clearDrop();
  };

  function startPinDrop() {
    state.map.enablePinDrop();
    document.getElementById('pin-banner').hidden = false;
    document.getElementById('pin-cancel').onclick = () => {
      endPinMode();
      draw();
    };
    state.pinHandler = (latlng) => {
      state.map.dropAt(latlng);
      w.pin = { lat: latlng.lat, lng: latlng.lng, name: w.pin ? w.pin.name : '', kind: w.pin ? w.pin.kind : 'street_food' };
      w.stallId = null;
      endPinMode();
      state.sheet.setDetent('half');
      draw();
    };
    state.sheet.setDetent('peek');
  }

  function sortedStalls() {
    const q = w.filter.trim().toLowerCase();
    const list = state.stalls.filter((s) => !q || s.name.toLowerCase().includes(q));
    if (state.user) return list.sort((a, b) => metres(state.user, a) - metres(state.user, b));
    return list.sort((a, b) => a.name.localeCompare(b.name));
  }

  function fillPick() {
    mount(pickEl, 
      ...sortedStalls().map((s) =>
        h('li', {}, h('button', {
          class: 'row', type: 'button', role: 'radio', 'aria-checked': String(w.stallId === s.id),
          onclick: () => {
            w.stallId = s.id;
            w.pin = null;
            state.map.clearDrop();
            fillPick();
            updateNext();
          },
        },
        h('span', { class: `dot lvl-${LEVELS[s.level].css}`, 'aria-hidden': 'true' }),
        h('span', { class: 'row-main' }, h('div', { class: 'row-title' }, s.name), h('div', { class: 'row-sub' }, KINDS[s.kind] || 'Place')),
        icon('check', 'icon check')))),
    );
  }

  function stepWhere() {
    pickEl = h('ul', { class: 'list pick', role: 'radiogroup', 'aria-label': 'Places' });
    fillPick();
    return [
      h('h2', { tabindex: '-1' }, 'Where did you eat?'),
      h('p', { class: 'sub' }, 'Choose the place, or drop a pin on the map if it is not listed.'),
      h('div', { class: 'field' },
        h('input', {
          type: 'text', placeholder: 'Filter places', 'aria-label': 'Filter places', value: w.filter, maxlength: '40',
          oninput: (e) => { w.filter = e.target.value; fillPick(); },
        })),
      h('div', { class: 'field' }, pickEl),
      w.pin
        ? h('div', { class: 'card field' },
            h('div', { class: 'label' }, 'New place (pin dropped)'),
            h('input', {
              type: 'text', 'aria-label': 'Name of the place', placeholder: 'e.g. Tea cart near the school', maxlength: '60', value: w.pin.name,
              oninput: (e) => { w.pin.name = e.target.value; updateNext(); },
            }),
            h('div', { class: 'field' },
              h('select', { 'aria-label': 'Type of place', onchange: (e) => { w.pin.kind = e.target.value; } },
                Object.entries(KINDS).map(([value, label]) => h('option', { value, selected: value === w.pin.kind }, label)))),
            h('p', { class: 'small muted' }, 'Letters, numbers and . , \' & ( ) / - only.'))
        : h('button', { class: 'btn secondary', type: 'button', onclick: startPinDrop }, 'Drop a pin for a new place'),
    ];
  }

  function stepWhen() {
    const readout = h('div', { class: 'readout' });
    const clock = h('p', { class: 'sub' });
    const paint = () => {
      readout.textContent = `About ${w.hoursAgo} hours ago`;
      clock.textContent = fmtTime(new Date(Date.now() - w.hoursAgo * 3600e3));
    };
    paint();
    const slider = h('input', {
      type: 'range', min: '2', max: '96', step: '1', value: String(w.hoursAgo), 'aria-label': 'Hours since you ate',
      oninput: (e) => {
        w.hoursAgo = Number(e.target.value);
        w.gap = Math.min(w.gap, maxGap());
        paint();
      },
    });
    return [
      h('h2', { tabindex: '-1' }, 'When did you eat?'),
      h('p', { class: 'sub' }, 'A rough time is fine.'),
      h('div', { class: 'field' }, readout, clock, slider),
      h('div', { class: 'chips', role: 'group', 'aria-label': 'Quick choices' },
        [6, 12, 24, 48, 72].map((n) => h('button', {
          class: 'chip', type: 'button',
          onclick: () => { w.hoursAgo = n; w.gap = Math.min(w.gap, maxGap()); slider.value = String(n); paint(); },
        }, `${n} h ago`))),
    ];
  }

  function stepSymptoms() {
    const readout = h('div', { class: 'readout' });
    const paint = () => { readout.textContent = `${w.gap} hours after eating`; };
    paint();
    const hint = h('p', { class: 'small', style: 'color:var(--outbreak-ink)', role: 'alert' });
    const paintHint = () => { hint.textContent = hasGI() ? '' : 'Pick at least one stomach symptom (not fever alone).'; };
    paintHint();
    return [
      h('h2', { tabindex: '-1' }, 'How are you feeling?'),
      h('p', { class: 'sub' }, 'Select everything that applies.'),
      h('div', { class: 'chips', style: 'flex-wrap:wrap', role: 'group', 'aria-label': 'Symptoms' },
        SYMPTOMS.map(([key, label]) => h('button', {
          class: 'chip', type: 'button', 'aria-pressed': String(w.symptoms.has(key)),
          onclick: (e) => {
            if (w.symptoms.has(key)) w.symptoms.delete(key); else w.symptoms.add(key);
            e.currentTarget.setAttribute('aria-pressed', String(w.symptoms.has(key)));
            paintHint();
            updateNext();
          },
        }, label))),
      hint,
      h('div', { class: 'field' },
        h('div', { class: 'label' }, 'Symptoms started'),
        readout,
        h('input', {
          type: 'range', min: '1', max: String(maxGap()), step: '1', value: String(Math.min(w.gap, maxGap())), 'aria-label': 'Hours between eating and first symptoms',
          oninput: (e) => { w.gap = Number(e.target.value); paint(); },
        })),
    ];
  }

  function placeName() {
    if (w.pin) return `${w.pin.name.trim()} (new place)`;
    return (state.stalls.find((s) => s.id === w.stallId) || {}).name || 'Unknown';
  }

  function stepReview() {
    const eaten = new Date(Date.now() - w.hoursAgo * 3600e3);
    const onset = new Date(eaten.getTime() + w.gap * 3600e3);
    const row = (label, value) => h('div', { class: 'event' }, h('span', { class: 'muted' }, `${label}: `), h('b', {}, value));
    return [
      h('h2', { tabindex: '-1' }, 'Review and send'),
      h('div', { class: 'card field' },
        row('Place', placeName()),
        row('Ate', fmtTime(eaten)),
        row('Symptoms', [...w.symptoms].map((s) => SYMPTOM_LABEL[s]).join(', ')),
        row('Started', fmtTime(onset))),
      h('input', { class: 'hp', name: 'website', type: 'text', tabindex: '-1', autocomplete: 'off', 'aria-hidden': 'true', oninput: (e) => { w.hp = e.target.value; } }),
      h('p', { class: 'note' }, state.account
        ? `Signed in as ${state.account.name}. This report is saved to your history. BiteTrace stores no email or phone number. One report never triggers an alert on its own.`
        : 'Your report is anonymous. BiteTrace stores no name or phone number, only a random code from this device. One report never triggers an alert on its own.'),
    ];
  }

  function buildBody() {
    const eaten = new Date(Date.now() - w.hoursAgo * 3600e3);
    const onset = new Date(eaten.getTime() + Math.min(w.gap, maxGap()) * 3600e3);
    const payload = {
      symptoms: [...w.symptoms],
      eaten_at: eaten.toISOString(),
      onset_at: onset.toISOString(),
      hp: w.hp,
      form_ms: Date.now() - w.openedAt,
    };
    if (w.stallId !== null) payload.stall_id = w.stallId;
    else payload.new_stall = { name: w.pin.name.trim(), kind: w.pin.kind, lat: w.pin.lat, lng: w.pin.lng };
    if (state.user) {
      payload.reporter_lat = state.user.lat;
      payload.reporter_lng = state.user.lng;
    }
    return payload;
  }

  async function submit() {
    w.busy = true;
    w.error = null;
    draw();
    try {
      const result = await api.report(buildBody());
      state.selectedId = result.stall_id;
      await state.refresh();
      state.show('done', result);
    } catch (err) {
      w.busy = false;
      w.error = err;
      draw();
    }
  }

  function draw() {
    const content = [stepWhere, stepWhen, stepSymptoms, stepReview][w.step]();
    const last = w.step === STEPS - 1;
    nextBtn = h('button', { class: 'btn', type: 'button', onclick: () => (last ? submit() : (w.step += 1, draw())) }, last ? (w.busy ? 'Sending...' : 'Submit report') : 'Next');
    mount(body, 
      h('div', { class: 'head-row', 'data-drag': true },
        h('button', {
          class: 'icon-btn', type: 'button', 'aria-label': w.step === 0 ? 'Cancel report' : 'Previous step',
          onclick: () => (w.step === 0 ? state.show(state.selectedId ? 'detail' : 'list', state.selectedId) : (w.step -= 1, draw())),
        }, icon(w.step === 0 ? 'close' : 'back')),
        h('span', { class: 'sub', style: 'margin:0' }, `Step ${w.step + 1} of ${STEPS}`)),
      h('div', { class: 'steps', 'aria-hidden': 'true' }, Array.from({ length: STEPS }, (_, i) => h('i', { class: i <= w.step ? 'done' : '' }))),
      content,
      w.error
        ? h('div', { class: 'alert-box', role: 'alert' }, w.error.message,
            w.error.reasons.length > 1 || (w.error.reasons.length === 1 && w.error.reasons[0] !== w.error.message)
              ? h('ul', {}, w.error.reasons.map((r) => h('li', {}, r))) : null)
        : null,
      nextBtn,
    );
    updateNext();
    body.querySelector('h2')?.focus({ preventScroll: true });
  }

  draw();
}

export function renderDone(body, result) {
  const css = LEVELS[result.level].css;
  const sent = result.alert && result.alert.action === 'sent';
  mount(body, 
    h('div', { class: 'ok-mark' }, icon('check')),
    h('h2', { tabindex: '-1' }, 'Thanks, your report is in'),
    h('p', { class: 'lead' }, result.level === 'NONE'
      ? 'One report on its own never triggers an alert. BiteTrace looks for other people who got sick after eating in the same place.'
      : result.message),
    sent
      ? h('div', { class: `card lvl-${css}`, style: 'margin-top:14px' }, h('span', { class: 'tag' }, 'Report sent'),
          'An evidence report was emailed to the food safety inbox after automatic AI review.')
      : null,
    h('h3', {}, 'Take care'),
    h('div', { class: 'card' }, h('ul', { class: 'small', style: 'margin:0;padding-left:18px;line-height:1.5' }, result.care_advice.map((t) => h('li', {}, t)))),
    h('button', { class: 'btn', type: 'button', onclick: () => state.show('detail', result.stall_id) }, 'View this place'),
    h('button', { class: 'btn secondary', type: 'button', onclick: () => state.show('list') }, 'Back to map'),
  );
}
