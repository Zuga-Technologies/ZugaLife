/**
 * TraderThemeBridge — parent-side postMessage handler for ZugaTrader themes.
 *
 * Mirrors the ZugaLife ThemeBridge pattern exactly: permission allowlist,
 * rate limiting, postMessage routing. Maps getData keys to /api/trader/ endpoints.
 *
 * SECURITY: Trader themes are READ-ONLY for trading data.
 * The ONLY writable key is theme_state. No trade execution from themes.
 */

import { api } from '@core/api/client'
import type { ThemePermission, ThemeMeta } from './ThemeBridge'

interface BridgeRequest {
  type: 'zugatheme:request'
  id: number
  method: string
  payload: Record<string, unknown>
}

// --- Rate Limiter (same as ZugaLife) ---

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

// --- ZugaTrader Permission Allowlist ---

const TRADER_PERMISSIONS: Record<string, Set<string>> = {
  read: new Set([
    'positions', 'signals', 'portfolio_value',
    'trade_history', 'pnl', 'market_data',
    'watchlist', 'theme_state',
  ]),
  write: new Set(['theme_state']),  // NO trade execution from themes
  action: new Set(['navigate', 'notify', 'open_chart']),
}

// --- Bridge Class ---

export class TraderThemeBridge {
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
    const allowed = TRADER_PERMISSIONS[type]
    if (allowed && !allowed.has(key)) {
      throw new Error(`Key not available in Trader studio: ${key}`)
    }
  }

  // --- Data Handlers ---

  private async handleGetData(payload: Record<string, unknown>): Promise<unknown> {
    const key = payload.key as string
    const params = (payload.params || {}) as Record<string, unknown>
    this.requirePermission('read', key)

    switch (key) {
      case 'positions':
        return api.get('/api/trader/bets?status=active&page_size=50')
      case 'signals':
        return api.get('/api/trader/signals')
      case 'portfolio_value':
        return api.get('/api/trader/status')
      case 'trade_history': {
        const page = Math.max(1, Number(params.page) || 1)
        const pageSize = Math.min(100, Math.max(1, Number(params.page_size) || 20))
        const status = params.status ? `&status=${params.status}` : ''
        return api.get(`/api/trader/bets?page=${page}&page_size=${pageSize}${status}`)
      }
      case 'pnl': {
        const days = Math.min(90, Math.max(1, Number(params.days) || 30))
        return api.get(`/api/trader/pnl?days=${days}`)
      }
      case 'market_data':
        return api.get('/api/trader/positions/live')
      case 'watchlist':
        return api.get('/api/trader/strategies')
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
      case 'theme_state': {
        const stateStr = JSON.stringify(value)
        if (stateStr.length > 102_400) {
          throw new Error('theme_state exceeds 100KB limit')
        }
        return api.put(`/api/forge/creations/${this.meta.themeId}/state`, { state: value })
      }
      default:
        throw new Error(`Write not allowed for key: ${key}. Only theme_state is writable.`)
    }
  }

  private async handleAction(payload: Record<string, unknown>): Promise<unknown> {
    const name = payload.name as string
    const params = (payload.params || {}) as Record<string, unknown>
    this.requirePermission('action', name)

    switch (name) {
      case 'navigate':
        window.dispatchEvent(new CustomEvent('zugatheme:navigate', { detail: params }))
        return { ok: true }
      case 'notify':
        window.dispatchEvent(new CustomEvent('zugatheme:notify', { detail: params }))
        return { ok: true }
      case 'open_chart':
        window.dispatchEvent(new CustomEvent('zugatheme:navigate', {
          detail: { to: 'trader', chart: params.market, ...params },
        }))
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
