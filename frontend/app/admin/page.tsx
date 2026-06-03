'use client'

import { useState } from 'react'
import OverviewTab from './OverviewTab'
import EscalationsTab from './EscalationsTab'
import SessionsTab from './SessionsTab'
import CustomersTab from './CustomersTab'

const TABS = ['Overview', 'Escalations', 'Sessions', 'Customers'] as const
type Tab = typeof TABS[number]

export default function AdminPage() {
  const [tab, setTab] = useState<Tab>('Overview')
  return (
    <div className="min-h-screen bg-gray-50">
      <header className="flex items-center justify-between border-b border-gray-200 bg-white px-6 py-4">
        <div>
          <h1 className="text-lg font-bold text-gray-800">Admin Dashboard</h1>
          <p className="text-xs text-gray-500">Agent reasoning, escalations &amp; customers</p>
        </div>
        <a href="/chat" className="text-sm text-blue-600 hover:underline">← Chat</a>
      </header>
      <nav className="flex gap-1 border-b border-gray-200 bg-white px-4">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm ${
              tab === t ? 'border-b-2 border-blue-500 font-medium text-blue-600' : 'text-gray-500'
            }`}
          >
            {t}
          </button>
        ))}
      </nav>
      <main className="mx-auto max-w-5xl p-6">
        {tab === 'Overview' && <OverviewTab />}
        {tab === 'Escalations' && <EscalationsTab />}
        {tab === 'Sessions' && <SessionsTab />}
        {tab === 'Customers' && <CustomersTab />}
      </main>
    </div>
  )
}
