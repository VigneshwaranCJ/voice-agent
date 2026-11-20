const TOKEN_KEY = 'vc_token'
const TENANT_KEY = 'vc_tenant'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export const session = {
  get token() { return localStorage.getItem(TOKEN_KEY) },
  set token(v: string | null) { v ? localStorage.setItem(TOKEN_KEY, v) : localStorage.removeItem(TOKEN_KEY) },
  get tenantId() { return localStorage.getItem(TENANT_KEY) },
  set tenantId(v: string | null) { v ? localStorage.setItem(TENANT_KEY, v) : localStorage.removeItem(TENANT_KEY) },
}

/** `noTenant` sends the request without the selected business (platform-level calls by platform admins). */
export async function api<T = unknown>(path: string,
  { json, noTenant, ...init }: RequestInit & { json?: unknown; noTenant?: boolean } = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (session.token) headers.set('Authorization', `Bearer ${session.token}`)
  if (session.tenantId && !noTenant) headers.set('X-Tenant-ID', session.tenantId)
  let body = init.body
  if (json !== undefined) {
    headers.set('Content-Type', 'application/json')
    body = JSON.stringify(json)
  }
  const res = await fetch(`/api/v1${path}`, { ...init, headers, body })
  if (res.status === 401 && !path.startsWith('/auth/login')) {
    session.token = null
    window.location.href = '/login'
  }
  if (!res.ok) {
    let msg = res.statusText
    try {
      const j = await res.json()
      msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail)
    } catch { /* ignore */ }
    throw new ApiError(res.status, msg)
  }
  return res.status === 204 ? (undefined as T) : res.json()
}
