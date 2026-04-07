/**
 * ZugaTheme SDK — injected into every theme iframe.
 *
 * Provides the Zuga global object that themes use to communicate with
 * the parent app through a postMessage bridge.
 *
 * This file is imported as a raw string and prepended to theme code
 * before injection into the iframe srcdoc.
 */

export const THEME_SDK_SOURCE = `
// === ZugaTheme SDK v1 ===
// Available as global \`Zuga\` inside every theme iframe.

const Zuga = {
  _callbacks: new Map(),
  _callId: 0,
  _subscriptions: new Map(),

  /**
   * Read data from the parent studio.
   * @param {string} key - Data key (e.g., 'mood_history', 'habit_list')
   * @param {object} params - Optional params (e.g., { days: 30 })
   * @returns {Promise<any>} The requested data
   */
  async getData(key, params = {}) {
    return this._call('getData', { key, params })
  },

  /**
   * Write data back to the parent studio.
   * @param {string} key - Data key (e.g., 'habit_complete', 'theme_state')
   * @param {*} value - The value to write
   * @returns {Promise<any>} Confirmation
   */
  async setData(key, value) {
    return this._call('setData', { key, value })
  },

  /**
   * Trigger an action in the parent app.
   * @param {string} name - Action name (e.g., 'celebrate', 'navigate')
   * @param {object} params - Action parameters
   * @returns {Promise<any>} Action result
   */
  async action(name, params = {}) {
    return this._call('action', { name, params })
  },

  /**
   * Subscribe to live data updates from the parent.
   * @param {string} key - Data key to watch
   * @param {function} callback - Called with new value on each update
   */
  onUpdate(key, callback) {
    if (!this._subscriptions.has(key)) {
      this._subscriptions.set(key, [])
      this._call('subscribe', { key }).catch(() => {})
    }
    this._subscriptions.get(key).push(callback)
  },

  /**
   * Get theme metadata from the parent.
   * @returns {Promise<{title: string, studio: string, themeId: string}>}
   */
  getMeta() {
    return this._call('getMeta', {})
  },

  // --- Internal RPC ---

  _call(method, payload) {
    return new Promise((resolve, reject) => {
      const id = ++this._callId
      this._callbacks.set(id, { resolve, reject })
      window.parent.postMessage({
        type: 'zugatheme:request',
        id,
        method,
        payload
      }, '*')
      setTimeout(() => {
        if (this._callbacks.has(id)) {
          this._callbacks.delete(id)
          reject(new Error('Bridge timeout — parent did not respond within 10s'))
        }
      }, 10000)
    })
  }
}

// Handle responses and live updates from parent
window.addEventListener('message', (e) => {
  const d = e.data
  if (!d || typeof d !== 'object') return

  // RPC response
  if (d.type === 'zugatheme:response') {
    const cb = Zuga._callbacks.get(d.id)
    if (cb) {
      Zuga._callbacks.delete(d.id)
      if (d.error) cb.reject(new Error(d.error))
      else cb.resolve(d.result)
    }
  }

  // Live data update
  if (d.type === 'zugatheme:update') {
    const subs = Zuga._subscriptions.get(d.key)
    if (subs) {
      subs.forEach(fn => {
        try { fn(d.value) } catch (err) { console.warn('[ZugaTheme] Update handler error:', err) }
      })
    }
  }
})

// Signal to parent that SDK is ready
window.parent.postMessage({ type: 'zugatheme:ready' }, '*')
`
