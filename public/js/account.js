import { api, clearSession, saveSession } from './api.js';
import { h, icon, mount, timeAgo } from './dom.js';
import { KINDS } from './levels.js';
import { state } from './state.js';

let gisLoading = null;

function loadGoogle() {
  if (window.google?.accounts?.id) return Promise.resolve();
  gisLoading ??= new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = 'https://accounts.google.com/gsi/client';
    script.async = true;
    script.onload = resolve;
    script.onerror = () => {
      gisLoading = null;
      reject(new Error('Could not load Google sign-in. Check your connection.'));
    };
    document.head.appendChild(script);
  });
  return gisLoading;
}

export function updateAccountButton() {
  const btn = document.getElementById('btn-account');
  if (!btn) return;
  btn.hidden = !state.config?.google_client_id;
  btn.textContent = state.account ? state.account.name : 'Sign in';
  btn.setAttribute('aria-label', state.account ? `Account: ${state.account.name}` : 'Sign in with Google');
}

async function onCredential({ credential }) {
  try {
    const session = await api.signIn(credential);
    saveSession(session.token);
    state.account = { name: session.name };
    updateAccountButton();
    state.toast(`Signed in as ${session.name}`);
    state.show('account');
  } catch (err) {
    state.toast(err.message);
  }
}

function header(title) {
  return [
    h('div', { class: 'head-row', 'data-drag': true },
      h('button', { class: 'icon-btn', type: 'button', 'aria-label': 'Back to places', onclick: () => state.show('list') }, icon('back'))),
    h('h2', { tabindex: '-1', style: 'margin-top:12px' }, title),
  ];
}

function signedOutView(body) {
  const slot = h('div', { class: 'gsi-slot' });
  mount(body,
    ...header('Sign in'),
    h('p', { class: 'sub' }, 'Sign in with Google to keep a history of your reports on any device. Signed-in reports also carry more trust, so fake accounts are harder to use.'),
    slot,
    h('p', { class: 'note' }, 'BiteTrace never stores your email or name. Only an irreversible code from your Google account is kept, and reporting still works without signing in.'),
  );
  loadGoogle()
    .then(() => {
      window.google.accounts.id.initialize({ client_id: state.config.google_client_id, callback: onCredential });
      window.google.accounts.id.renderButton(slot, { theme: 'outline', size: 'large', shape: 'pill', text: 'signin_with' });
    })
    .catch((err) => mount(slot, h('div', { class: 'alert-box', role: 'alert' }, err.message)));
}

async function signedInView(body) {
  mount(body, ...header(`Hi, ${state.account.name}`), h('div', { class: 'skeleton' }));
  let data;
  try {
    data = await api.myReports();
  } catch (err) {
    if (err.status === 401) {
      clearSession();
      state.account = null;
      updateAccountButton();
      signedOutView(body);
      return;
    }
    mount(body, ...header('Your reports'), h('div', { class: 'alert-box', role: 'alert' }, err.message));
    return;
  }
  mount(body,
    ...header(`Hi, ${data.name}`),
    h('p', { class: 'sub' }, 'Your reports, saved to your Google account.'),
    data.reports.length
      ? h('ul', { class: 'list' }, data.reports.map((r) =>
          h('li', {}, h('button', { class: 'row', type: 'button', onclick: () => state.show('detail', r.stall_id) },
            h('span', { class: 'row-main' },
              h('span', { class: 'row-title' }, r.stall_name),
              h('span', { class: 'row-sub' }, `${KINDS[r.kind] || 'Place'} · reported ${timeAgo(r.created_at)}`))))))
      : h('p', { class: 'muted' }, 'No reports yet. When you report an illness it will show up here.'),
    h('button', {
      class: 'btn secondary', type: 'button',
      onclick: () => {
        clearSession();
        state.account = null;
        window.google?.accounts?.id?.disableAutoSelect();
        updateAccountButton();
        state.toast('Signed out');
        state.show('list');
      },
    }, 'Sign out'),
  );
}

export function renderAccount(body) {
  if (!state.config.google_client_id) {
    mount(body, ...header('Sign in'), h('p', { class: 'sub' }, 'Google sign-in is not set up on this server yet.'));
    return;
  }
  if (state.account) signedInView(body);
  else signedOutView(body);
}
