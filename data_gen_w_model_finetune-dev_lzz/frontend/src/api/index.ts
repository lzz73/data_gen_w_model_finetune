/**
 * API 客户端基础配置
 * 通过 Vite proxy → http://localhost:8000 访问后端
 */

const BASE = '/api'

interface ApiResponse<T = any> {
  code: number
  data: T
  message?: string
}

async function request<T = any>(url: string, options?: RequestInit): Promise<ApiResponse<T>> {
  const ctrl = new AbortController()
  const tid = setTimeout(() => ctrl.abort(), 30000)
  try {
    const res = await fetch(`${BASE}${url}`, {
      headers: { 'Content-Type': 'application/json', ...options?.headers },
      ...options,
      signal: ctrl.signal,
    })
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}: ${res.statusText}`)
    }
    return res.json()
  } catch (e: any) {
    if (e?.name === 'AbortError') {
      throw new Error(`请求超时 (${url})，请检查后端是否启动`)
    }
    throw e
  } finally {
    clearTimeout(tid)
  }
}

export function get<T = any>(url: string) {
  return request<T>(url)
}

export function post<T = any>(url: string, data?: any) {
  return request<T>(url, {
    method: 'POST',
    body: data ? JSON.stringify(data) : undefined,
  })
}

export function del<T = any>(url: string) {
  return request<T>(url, { method: 'DELETE' })
}

/**
 * 上传文件
 */
export async function uploadFile<T = any>(
  url: string,
  file: File,
  extraFields: Record<string, string> = {},
): Promise<ApiResponse<T>> {
  const form = new FormData()
  form.append('file', file)
  Object.entries(extraFields).forEach(([k, v]) => form.append(k, v))

  const res = await fetch(`${BASE}${url}`, {
    method: 'POST',
    body: form,
  })
  return res.json()
}

/**
 * WebSocket 连接工厂
 * @param url ws 路径，如 /api/training/ws/task_001
 */
export function createWebSocket(url: string): WebSocket {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  return new WebSocket(`${protocol}//${location.host}${url}`)
}
