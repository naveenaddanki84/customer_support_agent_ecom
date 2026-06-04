'use client'

import { useEffect, useState } from 'react'
import { api, Customer, Order, UserSession } from '../lib/api'

interface SidebarProps {
  selectedEmail: string | null
  activeSessionId: string | null
  onSelectUser: (email: string) => void
  onSelectSession: (sessionId: string) => void
  onNewChat: () => void
  refreshKey: number
}

export default function Sidebar({
  selectedEmail, activeSessionId, onSelectUser, onSelectSession, onNewChat, refreshKey,
}: SidebarProps) {
  const [customers, setCustomers] = useState<Customer[]>([])
  const [sessions, setSessions] = useState<UserSession[]>([])
  const [orders, setOrders] = useState<Order[]>([])

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      // On first boot the backend may not be serving yet; retry with backoff
      // instead of giving up and leaving the customer dropdown empty.
      for (let attempt = 0; attempt < 6; attempt++) {
        if (attempt > 0) await new Promise((r) => setTimeout(r, Math.min(2000 * attempt, 10000)))
        try {
          const data = await api.customers()
          if (!cancelled) setCustomers(data)
          return
        } catch {
          // transient — keep retrying
        }
      }
    }
    load()
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    if (!selectedEmail) { setSessions([]); setOrders([]); return }
    api.userSessions(selectedEmail).then(setSessions).catch(() => setSessions([]))
    api.userOrders(selectedEmail).then(setOrders).catch(() => setOrders([]))
  }, [selectedEmail, refreshKey])

  return (
    <div className="flex h-full w-64 shrink-0 flex-col border-r border-gray-200 bg-gray-50">
      <div className="border-b border-gray-200 p-3">
        <div className="text-xs uppercase tracking-wide text-gray-500">Signed in as</div>
        <select
          value={selectedEmail ?? ''}
          onChange={(e) => onSelectUser(e.target.value)}
          className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-2 py-2 text-sm text-gray-800"
        >
          <option value="" disabled>Select a customer…</option>
          {customers.map((c) => (
            <option key={c.id} value={c.email}>{c.name}</option>
          ))}
        </select>
      </div>
      <div className="p-3">
        <button
          onClick={onNewChat}
          disabled={!selectedEmail}
          className="w-full rounded-lg bg-green-500 px-3 py-2 text-sm text-white hover:bg-green-600 disabled:opacity-50"
        >
          + New chat
        </button>
      </div>

      {/* Chat history */}
      <div className="px-3 pb-1 text-xs uppercase tracking-wide text-gray-500">Chat history</div>
      <div className="max-h-[35%] overflow-auto">
        {sessions.length === 0 && (
          <div className="px-3 py-3 text-xs text-gray-400">No chats yet.</div>
        )}
        {sessions.map((s) => {
          const active = s.id === activeSessionId
          return (
            <button
              key={s.id}
              onClick={() => onSelectSession(s.id)}
              className={`block w-full border-l-2 px-3 py-2 text-left text-sm ${
                active ? 'border-green-500 bg-green-50' : 'border-transparent hover:bg-gray-100'
              }`}
            >
              <div className="truncate text-gray-800">{s.title}</div>
              <div className="text-xs text-gray-500">
                {[s.last_decision || s.last_agent, new Date(s.updated_at).toLocaleString()]
                  .filter(Boolean).join(' · ')}
              </div>
            </button>
          )
        })}
      </div>

      {/* Customer's orders */}
      <div className="mt-1 border-t border-gray-200 px-3 pt-2 pb-1 text-xs uppercase tracking-wide text-gray-500">
        Your orders {selectedEmail && orders.length > 0 ? `(${orders.length})` : ''}
      </div>
      <div className="flex-1 overflow-auto pb-2">
        {!selectedEmail && (
          <div className="px-3 py-3 text-xs text-gray-400">Select a customer to see orders.</div>
        )}
        {selectedEmail && orders.length === 0 && (
          <div className="px-3 py-3 text-xs text-gray-400">No orders.</div>
        )}
        {orders.map((o) => (
          <div key={o.id} className="border-b border-gray-100 px-3 py-2 text-sm">
            <div className="flex items-center justify-between">
              <span className="font-medium text-gray-800">{o.id}</span>
              <span className="text-gray-600">${Number(o.amount).toFixed(2)}</span>
            </div>
            <div className="truncate text-xs text-gray-500">{o.item}</div>
            <div className="mt-0.5 flex flex-wrap gap-1">
              <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] text-gray-600">{o.status}</span>
              {o.is_final_sale && (
                <span className="rounded bg-red-100 px-1.5 py-0.5 text-[10px] text-red-700">final sale</span>
              )}
              {o.already_refunded && (
                <span className="rounded bg-green-100 px-1.5 py-0.5 text-[10px] text-green-700">refunded</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
