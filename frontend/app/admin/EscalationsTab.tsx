'use client'

import { useEffect, useState } from 'react'
import { api, Escalation } from '../lib/api'

export default function EscalationsTab() {
  const [items, setItems] = useState<Escalation[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.escalations().then(setItems).catch((e) => setError(String(e)))
  }, [])

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
            {e.session_id ? (
              <a
                href={`/admin/sessions/${e.session_id}`}
                target="_blank"
                rel="noopener noreferrer"
                className="rounded-lg bg-green-600 px-3 py-1.5 text-sm text-white hover:bg-green-700"
              >Review →</a>
            ) : (
              <span className="text-xs text-gray-400">no session</span>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
