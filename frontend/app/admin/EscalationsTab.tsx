'use client'

import { useCallback, useEffect, useState } from 'react'
import { api, Escalation } from '../lib/api'

export default function EscalationsTab() {
  const [items, setItems] = useState<Escalation[]>([])
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    api.escalations().then(setItems).catch((e) => setError(String(e)))
  }, [])
  useEffect(() => { load() }, [load])

  const resolve = async (id: string, action: 'approved' | 'rejected') => {
    setBusy(id)
    try {
      await api.resolveEscalation(id, action)
      load()
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(null)
    }
  }

  return (
    <div>
      {error && <div className="mb-3 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}
      {items.length === 0 && (
        <div className="rounded-xl border border-dashed border-gray-300 p-8 text-center text-sm text-gray-400">
          No pending escalations. Refunds over $500 will appear here for review.
        </div>
      )}
      <div className="space-y-2">
        {items.map((e) => (
          <div key={e.id} className="flex items-center gap-4 rounded-xl border border-gray-200 bg-white p-4">
            <div className="w-24 font-semibold text-gray-800">{e.order_id}</div>
            <div className="w-40 text-sm text-gray-700">{e.customer_name ?? '—'}</div>
            <div className="w-24 text-sm text-gray-700">
              {e.amount != null ? `$${Number(e.amount).toFixed(2)}` : '—'}
            </div>
            <div className="flex-1 text-sm text-gray-500">{e.reason}</div>
            <div className="flex gap-2">
              <button
                disabled={busy === e.id}
                onClick={() => resolve(e.id, 'approved')}
                className="rounded-lg bg-green-600 px-3 py-1.5 text-sm text-white hover:bg-green-700 disabled:opacity-50"
              >Approve</button>
              <button
                disabled={busy === e.id}
                onClick={() => resolve(e.id, 'rejected')}
                className="rounded-lg bg-red-600 px-3 py-1.5 text-sm text-white hover:bg-red-700 disabled:opacity-50"
              >Reject</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
