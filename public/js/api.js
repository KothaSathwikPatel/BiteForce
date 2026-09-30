const KEY = 'bitetrace.device';
const SESSION_KEY = 'bitetrace.session';
let memoryId = null;

function randomId() {
  if (crypto.randomUUID) return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}

/** Anonymous random ID kept only on this device. The server stores just a salted hash. */
export function deviceId() {
  try {
    let id = localStorage.getItem(KEY);
    if (!id) {
      id = randomId();
      localStorage.setItem(KEY, id);
    }
    return id;
  } catch {
    memoryId = memoryId || randomId();
    return memoryId;
  }
}

export function sessionToken() {
  try {
    return localStorage.getItem(SESSION_KEY);
  } catch {
    return null;
  }
}

export function saveSession(token) {
  try {
    localStorage.setItem(SESSION_KEY, token);
  } catch {
    /* storage unavailable: stay signed in for this page only */
  }
}

export function clearSession() {
  try {
    localStorage.removeItem(SESSION_KEY);
  } catch {
    /* nothing to clear */
  }
}

/** Display name from our own session token (label only; the server re-checks the signature). */
export function savedAccount() {
  const token = sessionToken();
  if (!token) return null;
  try {
    const body = token.split('.')[0].replace(/-/g, '+').replace(/_/g, '/');
    const data = JSON.parse(atob(body + '='.repeat((4 - (body.length % 4)) % 4)));
    return data.e * 1000 > Date.now() ? { name: String(data.n) } : null;
  } catch {
    return null;
  }
}

export class ApiError extends Error {
  constructor(status, data) {
    super((data && data.detail) || 'Something went wrong. Please try again.');
    this.status = status;
    this.code = data && data.error;
    this.reasons = (data && data.reasons) || [];
  }
}

async function request(path, options = {}) {
  let res;
  try {
    const auth = sessionToken();
    res = await fetch(path, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        'X-Device-Id': deviceId(),
        ...(auth ? { Authorization: `Bearer ${auth}` } : {}),
        ...(options.headers || {}),
      },
    });
  } catch {
    throw new ApiError(0, { detail: 'You appear to be offline. Please check your connection.' });
  }
  let data = null;
  try {
    data = await res.json();
  } catch {
    /* non-JSON error page */
  }
  if (!res.ok) throw new ApiError(res.status, data);
  return data;
}

const post = (path, body) => request(path, { method: 'POST', body: JSON.stringify(body ?? {}) });

export const api = {
  config: () => request('/api/config'),
  stalls: () => request('/api/stalls'),
  stall: (id) => request(`/api/stalls/${id}`),
  report: (body) => post('/api/reports', body),
  simulate: (stallId, cases) => post('/api/demo/simulate', { stall_id: stallId, cases }),
  reset: () => post('/api/demo/reset'),
  signIn: (credential) => post('/api/auth/google', { credential }),
  myReports: () => request('/api/me/reports'),
  alerts: (limit = 50) => request(`/api/alerts?limit=${limit}`),
};
