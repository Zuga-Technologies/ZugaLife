/**
 * ThemeBridge — parent-side postMessage handler for ZugaThemes.
 *
 * Enforces permissions, proxies data requests to ZugaLife APIs,
 * handles rate limiting, and routes actions.
 */

import { api } from '@core/api/client'

// --- Types ---

export interface ThemePermission {
  key: string
  type: 'read' | 'write' | 'action'
  description: string
}

export interface ThemeMeta {
  themeId: string
  title: string
  studio: string
}

interface BridgeRequest {
  type: 'zugatheme:request'
  id: number
  method: string
  payload: Record<string, unknown>
}

// --- Rate Limiter ---

class RateLimiter {
  private counts = new Map<string, { count: number; resetAt: number }>()

  check(method: string, limit: number): boolean {
    const now = Date.now()
    const entry = this.counts.get(method)
    if (!entry || now > entry.resetAt) {
      this.counts.set(method, { count: 1, resetAt: now + 60_000 })
      return true
    }
    if (entry.count >= limit) return false
    entry.count++
    return true
  }
}

const RATE_LIMITS: Record<string, number> = {
  getData: 30,
  setData: 10,
  action: 5,
  subscribe: 10,
  getMeta: 10,
}

// --- ZugaLife Permission Allowlist ---

const LIFE_PERMISSIONS: Record<string, Set<string>> = {
  read: new Set([
    'mood_history', 'mood_current', 'habit_list', 'habit_history',
    'journal_list', 'meditation_stats', 'goals', 'streaks',
    'user_profile', 'theme_state',
  ]),
  write: new Set([
    'habit_complete', 'mood_log', 'goal_progress', 'theme_state',
  ]),
  action: new Set([
    'celebrate', 'navigate', 'notify', 'open_journal', 'start_meditation',
  ]),
}

// --- Bridge Class ---

export class ThemeBridge {
  private iframe: HTMLIFrameElement
  private permissions: Set<string>
  private meta: ThemeMeta
  private rateLimiter = new RateLimiter()
  private subscriptions = new Set<string>()
  private boundHandler: (e: MessageEvent) => void

  constructor(iframe: HTMLIFrameElement, permissions: ThemePermission[], meta: ThemeMeta) {
    this.iframe = iframe
    this.meta = meta
    this.permissions = new Set(permissions.map(p => `${p.type}:${p.key}`))

    this.boundHandler = this.handleMessage.bind(this)
    window.addEventListener('message', this.boundHandler)
  }

  destroy() {
    window.removeEventListener('message', this.boundHandler)
    this.subscriptions.clear()
  }

  /** Push a live update to the theme iframe */
  pushUpdate(key: string, value: unknown) {
    if (!this.subscriptions.has(key)) return
    this.iframe.contentWindow?.postMessage({
      type: 'zugatheme:update',
      key,
      value,
    }, '*')
  }

  // --- Message Handling ---

  private handleMessage(e: MessageEvent) {
    if (e.source !== this.iframe.contentWindow) return
    const data = e.data as BridgeRequest
    if (!data || data.type !== 'zugatheme:request') return

    this.dispatch(data.method, data.payload)
      .then(result => this.respond(data.id, result))
      .catch(err => this.respondError(data.id, err.message))
  }

  private async dispatch(method: string, payload: Record<string, unknown>): Promise<unknown> {
    // Rate limit check
    const limit = RATE_LIMITS[method]
    if (limit && !this.rateLimiter.check(method, limit)) {
      throw new Error(`Rate limit exceeded for ${method}. Max ${limit}/minute.`)
    }

    switch (method) {
      case 'getData':
        return this.handleGetData(payload)
      case 'setData':
        return this.handleSetData(payload)
      case 'action':
        return this.handleAction(payload)
      case 'subscribe':
        return this.handleSubscribe(payload)
      case 'getMeta':
        return this.meta
      default:
        throw new Error(`Unknown method: ${method}`)
    }
  }

  // --- Permission Checks ---

  private requirePermission(type: string, key: string) {
    // theme_state is always allowed for the theme's own state
    if (key === 'theme_state') return

    const permKey = `${type}:${key}`
    if (!this.permissions.has(permKey)) {
      throw new Error(`Permission denied: ${permKey}`)
    }
    // Also check studio allowlist
    const allowed = LIFE_PERMISSIONS[type]
    if (allowed && !allowed.has(key)) {
      throw new Error(`Key not available in this studio: ${key}`)
    }
  }

  // --- Data Handlers ---

  private async handleGetData(payload: Record<string, unknown>): Promise<unknown> {
    const key = payload.key as string
    const params = (payload.params || {}) as Record<string, unknown>
    this.requirePermission('read', key)

    switch (key) {
      case 'mood_history': {
        const days = Math.min(Number(params.days) || 30, 90)
        return api.get(`/api/life/mood?days=${days}`)
      }
      case 'mood_current':
        return api.get('/api/life/mood?days=1')
      case 'habit_list':
        return api.get('/api/life/habits')
      case 'habit_history': {
        const habitId = params.habit_id || ''
        const days = Math.min(Number(params.days) || 30, 90)
        return api.get(`/api/life/habits/history?habit_id=${habitId}&days=${days}`)
      }
      case 'journal_list': {
        const days = Math.min(Number(params.days) || 30, 90)
        return api.get(`/api/life/journal?days=${days}`)
      }
      case 'meditation_stats':
        return api.get('/api/life/meditation/stats')
      case 'goals':
        return api.get('/api/life/goals')
      case 'streaks':
        return api.get('/api/life/dashboard')
      case 'user_profile':
        return api.get('/api/life/settings')
      case 'theme_state':
        return api.get(`/api/forge/creations/${this.meta.themeId}/state`)
      default:
        throw new Error(`Unknown data key: ${key}`)
    }
  }

  private async handleSetData(payload: Record<string, unknown>): Promise<unknown> {
    const key = payload.key as string
    const value = payload.value
    this.requirePermission('write', key)

    switch (key) {
      case 'habit_complete':
        return api.post('/api/life/habits/log', value)
      case 'mood_log':
        return api.post('/api/life/mood', value)
      case 'goal_progress':
        return api.patch(`/api/life/goals/${(value as Record<string, unknown>).goal_id}/progress`, value)
      case 'theme_state': {
        const stateStr = JSON.stringify(value)
        if (stateStr.length > 102_400) {
          throw new Error('theme_state exceeds 100KB limit')
        }
        return api.put(`/api/forge/creations/${this.meta.themeId}/state`, { state: value })
      }
      default:
        throw new Error(`Unknown write key: ${key}`)
    }
  }

  private async handleAction(payload: Record<string, unknown>): Promise<unknown> {
    const name = payload.name as string
    const params = (payload.params || {}) as Record<string, unknown>
    this.requirePermission('action', name)

    switch (name) {
      case 'celebrate':
        window.dispatchEvent(new CustomEvent('zugatheme:celebrate', { detail: params }))
        return { ok: true }
      case 'navigate':
        window.dispatchEvent(new CustomEvent('zugatheme:navigate', { detail: params }))
        return { ok: true }
      case 'notify':
        window.dispatchEvent(new CustomEvent('zugatheme:notify', { detail: params }))
        return { ok: true }
      case 'open_journal':
        window.dispatchEvent(new CustomEvent('zugatheme:navigate', { detail: { to: 'journal', ...params } }))
        return { ok: true }
      case 'start_meditation':
        window.dispatchEvent(new CustomEvent('zugatheme:navigate', { detail: { to: 'meditate', ...params } }))
        return { ok: true }
      default:
        throw new Error(`Unknown action: ${name}`)
    }
  }

  private handleSubscribe(payload: Record<string, unknown>): { ok: boolean } {
    const key = payload.key as string
    this.requirePermission('read', key)
    this.subscriptions.add(key)
    return { ok: true }
  }

  // --- Response Helpers ---

  private respond(id: number, result: unknown) {
    this.iframe.contentWindow?.postMessage({
      type: 'zugatheme:response',
      id,
      result,
    }, '*')
  }

  private respondError(id: number, error: string) {
    this.iframe.contentWindow?.postMessage({
      type: 'zugatheme:response',
      id,
      error,
    }, '*')
  }
}
