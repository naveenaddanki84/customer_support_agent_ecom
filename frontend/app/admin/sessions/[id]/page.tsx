'use client'

import { use, useEffect, useState } from 'react'
import { api, AgentLog } from '../../../lib/api'

function prettyResult(result: string): string {
  try { return JSON.stringify(JSON.parse(result), null, 2) } catch { return result }
}

export default function SessionTracePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  const [logs, setLogs] = useState<AgentLog[]>([])
  const [messages, setMessages] = useState<any[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.adminSession(id)
      .then((d) => { setLogs(d.logs); setMessages(d.messages) })
      .catch((e) => setError(String(e)))
  }, [id])

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <a href="/admin" className="text-sm text-blue-600 hover:underline">← Admin</a>
      <h1 className="mb-1 mt-2 text-lg font-bold text-gray-800">Session trace</h1>
      <p className="mb-4 text-xs text-gray-500">{id}</p>
      {error && <div className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}

      <div className="grid grid-cols-2 gap-6">
        <div>
          <h2 className="mb-2 text-sm font-semibold uppercase text-gray-400">Conversation</h2>
          <div className="space-y-2">
            {messages.map((m) => (
              <div key={m.id} className={`rounded-lg p-2 text-sm ${
                m.sender === 'user' ? 'bg-blue-50 text-blue-900' : 'bg-white border border-gray-200 text-gray-800'
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
                    <span className="rounded bg-blue-100 px-2 py-0.5 text-xs text-blue-700">{log.handling_agent}</span>
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
                        <div className="font-mono text-xs font-semibold text-blue-700">
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
