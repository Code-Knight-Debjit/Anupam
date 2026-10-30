// Thin fetch wrapper for /360/api/ — attaches the CSRF header Django's
// CsrfViewMiddleware requires on every unsafe method, never bypasses it.
const API_ROOT = '/360/api/';

function getCookie(name) {
  const match = document.cookie.match('(?:^|; )' + name + '=([^;]*)');
  return match ? decodeURIComponent(match[1]) : null;
}

class ApiError extends Error {
  constructor(status, body) {
    super((body && (body.detail || body.error)) || `Request failed (${status})`);
    this.status = status;
    this.body = body;
  }
}

async function request(method, path, data) {
  const url = path.startsWith('http') ? path : API_ROOT + path.replace(/^\//, '');
  const opts = {
    method,
    headers: { 'X-CSRFToken': getCookie('csrftoken') },
    credentials: 'same-origin',
  };
  if (data instanceof FormData) {
    opts.body = data; // the browser sets the multipart boundary itself
  } else if (data !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(data);
  }
  const resp = await fetch(url, opts);
  const text = await resp.text();
  const body = text ? JSON.parse(text) : null;
  if (!resp.ok) throw new ApiError(resp.status, body);
  return body;
}

export const api = {
  get: (path) => request('GET', path),
  post: (path, data) => request('POST', path, data),
  patch: (path, data) => request('PATCH', path, data),
  delete: (path) => request('DELETE', path),
  upload: (path, file) => { const fd = new FormData(); fd.append('file', file); return request('POST', path, fd); },

  /** Pages through a paginated list endpoint and returns every result —
   * mirrors the original's whole-array-in-memory model for the handful of
   * screens (reports, exports) that need the full collection, not a page. */
  async all(path, params) {
    const sep = path.includes('?') ? '&' : '?';
    let page = 1, out = [];
    for (;;) {
      const qs = new URLSearchParams(Object.assign({}, params, { page, page_size: 200 })).toString();
      const data = await request('GET', `${path}${sep}${qs}`);
      out = out.concat(data.results);
      if (page >= data.num_pages) break;
      page += 1;
    }
    return out;
  },
};

export { ApiError };
