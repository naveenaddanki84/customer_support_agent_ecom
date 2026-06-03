'use client'

import { use, useCallback, useEffect, useState } from 'react'
import { api, AgentLog, PendingEscalation } from '../../../lib/api'

function prettyResult(result: string): string {
  try { return JSON.stringify(JSON.parse(result), null, 2) } catch { return result }
}

function JudgeCard({ esc, onResolved }: { esc: PendingEscalation; onResolved: () => void }) {
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const decide = async (action: 'approved' | 'rejected') => {
    setBusy(true)
    setErr(null)
    try {
      await api.resolveEscalation(esc.id, action, reason.trim())
      onResolved()
    } catch (e) {
      setErr(String(e))
      setBusy(false)
    }
  }

  return (
    <div className="rounded-xl border border-amber-300 bg-amber-50 p-4">
      <div className="mb-2 flex items-center gap-2 text-sm">
        <span className="rounded bg-amber-200 px-2 py-0.5 text-xs font-semibold text-amber-800">escalated</span>
        <span className="font-semibold text-gray-800">{esc.order_id}</span>
        {esc.amount != null && <span className="text-gray-600">${Number(esc.amount).toFixed(2)}</span>}
      </div>
      <div className="mb-3 text-sm text-gray-600">{esc.reason}</div>
      <label className="mb-1 block text-xs font-semibold uppercase text-gray-500">
        Your reason (the assistant will use this in its reply to the customer)
      </label>
      <textarea
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        rows={3}
        placeholder="e.g. Loyal customer and the item arrived damaged, approving as an exception."
        className="mb-3 w-full rounded-lg border border-gray-300 bg-white p-2 text-sm text-gray-800"
      />
      {err && <div className="mb-2 text-xs text-red-600">{err}</div>}
      <div className="flex gap-2">
        <button
          disabled={busy}
          onClick={() => decide('approved')}
          className="rounded-lg bg-green-600 px-4 py-1.5 text-sm text-white hover:bg-green-700 disabled:opacity-50"
        >Approve refund</button>
        <button
          disabled={busy}
          onClick={() => decide('rejected')}
          className="rounded-lg bg-red-600 px-4 py-1.5 text-sm text-white hover:bg-red-700 disabled:opacity-50"
        >Reject refund</button>
      </div>
    </div>
  )
}

export default function SessionTracePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  const [logs, setLogs] = useState<AgentLog[]>([])
  const [messages, setMessages] = useState<any[]>([])
  const [escalations, setEscalations] = useState<PendingEscalation[]>([])
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    api.adminSession(id)
      .then((d) => { setLogs(d.logs); setMessages(d.messages); setEscalations(d.escalations || []) })
      .catch((e) => setError(String(e)))
  }, [id])

  useEffect(() => { load() }, [load])

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <a href="/admin" className="text-sm text-green-600 hover:underline">← Admin</a>
      <h1 className="mb-1 mt-2 text-lg font-bold text-gray-800">Session trace</h1>
      <p className="mb-4 text-xs text-gray-500">{id}</p>
      {error && <div className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}

      {escalations.length > 0 && (
        <div className="mb-6">
          <h2 className="mb-2 text-sm font-semibold uppercase text-amber-700">Pending escalation — your decision</h2>
          <div className="space-y-3">
            {escalations.map((esc) => (
              <JudgeCard key={esc.id} esc={esc} onResolved={load} />
            ))}
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 gap-6">
        <div>
          <h2 className="mb-2 text-sm font-semibold uppercase text-gray-400">Conversation</h2>
          <div className="space-y-2">
            {messages.map((m) => (
              <div key={m.id} className={`rounded-lg p-2 text-sm ${
                m.sender === 'user' ? 'bg-green-50 text-green-900' : 'bg-white border border-gray-200 text-gray-800'
              }`}>
                <div className="text-xs text-gray-400">{m.sender}{m.metadata?.agent ? ` · ${m.metadata.agent}` : ''}</div>
                {m.content}
              </div>
            ))}
          </div>
        </div>
        <div>
          <h2 className="mb-2 text-sm font-semibold uppercase text-gray-400">Reasoning per turn</h2>
          <div className="space-y-3">
            {logs.map((log) => (
              <div key={log.id} className="rounded-lg border border-gray-200 bg-white p-3 text-sm">
                <div className="mb-1 flex items-center gap-2">
                  {log.handling_agent && (
                    <span className="rounded bg-green-100 px-2 py-0.5 text-xs text-green-700">{log.handling_agent}</span>
                  )}
                  {log.refund_decision && (
                    <span className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-700">{log.refund_decision}</span>
                  )}
                  <span className="truncate text-gray-700">{log.user_message}</span>
                </div>
                <div className="text-xs text-gray-500">intent: {log.router_intent || '—'}</div>
                {log.tool_trace?.length > 0 && (
                  <ol className="mt-2 space-y-1">
                    {log.tool_trace.map((t, i) => (
                      <li key={i} className="rounded bg-gray-50 p-2">
                        <div className="font-mono text-xs font-semibold text-green-700">
                          {i + 1}. {t.tool}({JSON.stringify(t.args)})
                        </div>
                        <pre className="mt-1 whitespace-pre-wrap break-words text-xs text-gray-600">{prettyResult(t.result)}</pre>
                      </li>
                    ))}
                  </ol>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
