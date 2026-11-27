// Thin client for the NeuroMetric API (/api). Bearer token kept in sessionStorage only
// (cleared when the tab closes); never in localStorage, cookies or URLs.

const KEY = 'nm.portal.token';

function storageGet() {
  try { return sessionStorage.getItem(KEY); } catch { return null; }
}
function storageSet(v) {
  try { v ? sessionStorage.setItem(KEY, v) : sessionStorage.removeItem(KEY); } catch { /* private mode */ }
}

let token = storageGet();
let unauthorizedHandler = () => {};

export class ApiError extends Error {
  constructor(status, body) {
    super((body && (body.message || body.detail)) || `request failed (${status})`);
    this.status = status;
    this.code = body && body.error;
    this.body = body || {};
  }
  get forbidden() { return this.status === 403; }
}

export function onUnauthorized(fn) { unauthorizedHandler = fn; }
export function hasToken() { return !!token; }
export function setToken(t) { token = t; storageSet(t); }

export async function api(path, { method = 'GET', body, raw = false, query } = {}) {
  const headers = { Accept: raw ? '*/*' : 'application/json' };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  let url = `/api${path}`;
  if (query) {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(query)) if (v !== undefined && v !== null && v !== '') q.set(k, v);
    const s = q.toString();
    if (s) url += `?${s}`;
  }
  let res;
  try {
    res = await fetch(url, {
      method, headers, cache: 'no-store', credentials: 'omit',
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (e) {
    throw new ApiError(0, { error: 'network', message: 'The server could not be reached. Check your connection and try again.' });
  }
  if (!res.ok) {
    let b = {};
    try { b = await res.json(); } catch { /* not json */ }
    const err = new ApiError(res.status, b);
    if (res.status === 401 && path !== '/auth/login' && !path.startsWith('/signatures')) unauthorizedHandler(err);
    throw err;
  }
  return raw ? res : res.json();
}

export const get = (p, query) => api(p, { query });
export const post = (p, body, query) => api(p, { method: 'POST', body, query });
export const put = (p, body) => api(p, { method: 'PUT', body });

/** Human-readable explanation for an error, safe to show to any role. */
export function explain(err, what = 'this information') {
  if (!(err instanceof ApiError)) return `Something went wrong: ${err && err.message ? err.message : err}`;
  switch (err.status) {
    case 0: return err.message;
    case 401: return 'Your session has ended. Please sign in again.';
    case 403: return `Your role does not have permission to see or change ${what}.`;
    case 404: return `Not found: ${err.message}`;
    case 409: return `Conflict: ${err.message}`;
    case 413: return 'That request was too large.';
    case 422: return `Please check the form: ${err.message}`;
    case 429: return 'Too many attempts. Please wait a few minutes and try again.';
    default: return `The server reported a problem (${err.status}): ${err.message}`;
  }
}
