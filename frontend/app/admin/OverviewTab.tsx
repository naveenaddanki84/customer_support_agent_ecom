'use client'

/**
 * Overview tab — displays the agent's internal reasoning logs:
 * router decision, handling agent, refund decision, guardrails score,
 * and the full tool-call trace for every turn.
 */

import { useCallback, useEffect, useState } from 'react'
import { AgentLog } from '../lib/api'

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface Stats {
  total_turns: number
  approved: number
  denied: number
  escalated: number
}

const decisionColor: Record<string, string> = {
  approved: 'bg-green-100 text-green-700 border-green-300',
  denied: 'bg-red-100 text-red-700 border-red-300',
  escalated: 'bg-amber-100 text-amber-700 border-amber-300',
}

const agentColor: Record<string, string> = {
  refund: 'bg-green-100 text-green-700',
  faq: 'bg-purple-100 text-purple-700',
  escalation: 'bg-amber-100 text-amber-700',
}

function prettyResult(result: string): string {
  try {
    return JSON.stringify(JSON.parse(result), null, 2)
  } catch {
    return result
  }
}

function StatCard({ label, value, accent }: { label: string; value: number; accent: string }) {
  return (
    <div className="flex-1 rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <div className={`text-2xl font-bold ${accent}`}>{value}</div>
      <div className="text-xs uppercase tracking-wide text-gray-500">{label}</div>
    </div>
  )
}

function LogRow({ log }: { log: AgentLog }) {
  const [open, setOpen] = useState(false)
  const decision = log.refund_decision

  return (
    <div className="rounded-xl border border-gray-200 bg-white shadow-sm">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-3 p-4 text-left"
      >
        <span className="text-xs text-gray-400 w-16 shrink-0">
          {new Date(log.created_at).toLocaleTimeString()}
        </span>
        {log.handling_agent && (
          <span className={`rounded px-2 py-0.5 text-xs font-medium ${agentColor[log.handling_agent] || 'bg-gray-100 text-gray-600'}`}>
            {log.handling_agent}
          </span>
        )}
        {decision && (
          <span className={`rounded border px-2 py-0.5 text-xs font-semibold ${decisionColor[decision] || 'bg-gray-100 text-gray-600'}`}>
            {decision}
          </span>
        )}
        <span className="flex-1 truncate text-sm text-gray-800">{log.user_message}</span>
        {log.guardrails_score && (
          <span className="text-xs text-gray-400">safety {log.guardrails_score}</span>
        )}
        <span className="text-xs text-gray-400">{log.tool_trace?.length || 0} tools</span>
        <span className="text-gray-400">{open ? '▾' : '▸'}</span>
      </button>

      {open && (
        <div className="space-y-3 border-t border-gray-100 p-4 text-sm">
          <div>
            <div className="text-xs font-semibold uppercase text-gray-400">Router</div>
            <div className="text-gray-700">
              intent: <span className="font-medium">{log.router_intent || '—'}</span>
              {log.router_reasoning ? ` · ${log.router_reasoning}` : ''}
            </div>
          </div>

          {log.tool_trace?.length > 0 && (
            <div>
              <div className="text-xs font-semibold uppercase text-gray-400">Tool calls</div>
              <ol className="mt-1 space-y-2">
                {log.tool_trace.map((call, i) => (
                  <li key={i} className="rounded-lg bg-gray-50 p-3">
                    <div className="font-mono text-xs font-semibold text-green-700">
                      {i + 1}. {call.tool}({JSON.stringify(call.args)})
                    </div>
                    <pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-words text-xs text-gray-600">
                      {prettyResult(call.result)}
                    </pre>
                  </li>
                ))}
              </ol>
            </div>
          )}

          <div>
            <div className="text-xs font-semibold uppercase text-gray-400">Final response</div>
            <div className="whitespace-pre-wrap text-gray-700">{log.final_response}</div>
          </div>
        </div>
      )}
    </div>
  )
}

export default function OverviewTab() {
  const [logs, setLogs] = useState<AgentLog[]>([])
  const [stats, setStats] = useState<Stats | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [auto, setAuto] = useState(true)

  const load = useCallback(async () => {
    try {
      const [logsRes, statsRes] = await Promise.all([
        fetch(`${API_BASE_URL}/api/v1/admin/logs?limit=100`),
        fetch(`${API_BASE_URL}/api/v1/admin/stats`),
      ])
      if (!logsRes.ok || !statsRes.ok) throw new Error('Failed to load admin data')
      setLogs(await logsRes.json())
      setStats(await statsRes.json())
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error')
    }
  }, [])

  useEffect(() => {
    load()
    if (!auto) return
    const t = setInterval(load, 5000)
    return () => clearInterval(t)
  }, [load, auto])

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-end gap-4">
        <label className="flex items-center gap-2 text-xs text-gray-500">
          <input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} />
          Auto-refresh
        </label>
        <button onClick={load} className="rounded-lg bg-green-500 px-3 py-1.5 text-sm text-white hover:bg-green-600">
          Refresh
        </button>
      </div>

      {stats && (
        <div className="flex gap-4">
          <StatCard label="Total turns" value={stats.total_turns} accent="text-gray-800" />
          <StatCard label="Approved" value={stats.approved} accent="text-green-600" />
          <StatCard label="Denied" value={stats.denied} accent="text-red-600" />
          <StatCard label="Escalated" value={stats.escalated} accent="text-amber-600" />
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="space-y-2">
        {logs.length === 0 && !error && (
          <div className="rounded-xl border border-dashed border-gray-300 p-8 text-center text-sm text-gray-400">
            No agent activity yet. Start a conversation in the chat to see reasoning logs here.
          </div>
        )}
        {logs.map((log) => (
          <LogRow key={log.id} log={log} />
        ))}
      </div>
    </div>
  )
}
