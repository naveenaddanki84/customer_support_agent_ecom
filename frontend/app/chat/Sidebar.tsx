'use client'

import { useEffect, useState } from 'react'
import { api, Customer, UserSession } from '../lib/api'

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

  useEffect(() => {
    api.customers().then(setCustomers).catch(() => setCustomers([]))
  }, [])

  useEffect(() => {
    if (!selectedEmail) { setSessions([]); return }
    api.userSessions(selectedEmail).then(setSessions).catch(() => setSessions([]))
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
          className="w-full rounded-lg bg-blue-500 px-3 py-2 text-sm text-white hover:bg-blue-600 disabled:opacity-50"
        >
          + New chat
        </button>
      </div>
      <div className="px-3 pb-1 text-xs uppercase tracking-wide text-gray-500">Chat history</div>
      <div className="flex-1 overflow-auto">
        {sessions.length === 0 && (
          <div className="px-3 py-4 text-xs text-gray-400">No chats yet.</div>
        )}
        {sessions.map((s) => {
          const active = s.id === activeSessionId
          return (
            <button
              key={s.id}
              onClick={() => onSelectSession(s.id)}
              className={`block w-full border-l-2 px-3 py-2 text-left text-sm ${
                active ? 'border-blue-500 bg-blue-50' : 'border-transparent hover:bg-gray-100'
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
    </div>
  )
}
