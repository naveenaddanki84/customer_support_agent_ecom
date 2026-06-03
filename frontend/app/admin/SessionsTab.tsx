'use client'

import { useCallback, useEffect, useState } from 'react'
import { api, AdminSession } from '../lib/api'

export default function SessionsTab() {
  const [sessions, setSessions] = useState<AdminSession[]>([])
  const [busy, setBusy] = useState<string | null>(null)

  const load = useCallback(() => {
    api.adminSessions().then(setSessions).catch(() => setSessions([]))
  }, [])
  useEffect(() => { load() }, [load])

  const close = async (id: string) => {
    setBusy(id)
    try { await api.closeSession(id); load() } catch { /* ignore */ } finally { setBusy(null) }
  }

  return (
    <div className="space-y-2">
      {sessions.map((s) => (
        <div key={s.id} className="flex items-center gap-4 rounded-xl border border-gray-200 bg-white p-3 text-sm">
          <div className="flex-1 truncate text-gray-800">
            {s.user_id}
            {s.has_escalation && (
              <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-700">esc</span>
            )}
            {s.status === 'closed' && (
              <span className="ml-2 rounded bg-gray-200 px-1.5 py-0.5 text-xs text-gray-600">closed</span>
            )}
          </div>
          <div className="w-16 text-gray-500">{s.message_count} msgs</div>
          <div className="w-40 text-gray-400">
            {s.last_activity ? new Date(s.last_activity).toLocaleString() : '—'}
          </div>
          <a
            href={`/admin/sessions/${s.id}`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-green-600 hover:underline"
          >View trace →</a>
          {s.status !== 'closed' && (
            <button
              disabled={busy === s.id}
              onClick={() => close(s.id)}
              className="rounded-lg border border-gray-300 px-2 py-1 text-xs text-gray-600 hover:bg-gray-100 disabled:opacity-50"
            >Close</button>
          )}
        </div>
      ))}
      {sessions.length === 0 && (
        <div className="rounded-xl border border-dashed border-gray-300 p-8 text-center text-sm text-gray-400">
          No sessions yet.
        </div>
      )}
    </div>
  )
}
