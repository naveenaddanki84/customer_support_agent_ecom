'use client'

import { useEffect, useState } from 'react'
import { api, Customer } from '../lib/api'

export default function CustomersTab() {
  const [customers, setCustomers] = useState<Customer[]>([])
  const [detail, setDetail] = useState<any | null>(null)

  useEffect(() => { api.customers().then(setCustomers).catch(() => setCustomers([])) }, [])
  const open = (id: number) => api.adminCustomer(id).then(setDetail).catch(() => setDetail(null))

  return (
    <div className="grid grid-cols-3 gap-6">
      <div className="space-y-1">
        {customers.map((c) => (
          <button
            key={c.id}
            onClick={() => open(c.id)}
            className={`block w-full rounded-lg px-3 py-2 text-left text-sm ${
              detail?.customer?.id === c.id ? 'bg-green-50 text-green-700' : 'hover:bg-gray-100 text-gray-700'
            }`}
          >
            {c.name} <span className="text-xs text-gray-400">· {c.tier}</span>
          </button>
        ))}
      </div>
      <div className="col-span-2">
        {!detail && <div className="text-sm text-gray-400">Select a customer to view orders, refunds, and sessions.</div>}
        {detail && (
          <div className="space-y-4 text-sm">
            <div>
              <div className="text-lg font-semibold text-gray-800">{detail.customer.name}</div>
              <div className="text-gray-500">{detail.customer.email} · {detail.customer.tier}</div>
            </div>
            <div>
              <div className="mb-1 text-xs font-semibold uppercase text-gray-400">Orders ({detail.orders.length})</div>
              {detail.orders.map((o: any) => (
                <div key={o.id} className="flex justify-between border-b border-gray-100 py-1">
                  <span>{o.id} · {o.item}</span>
                  <span className="text-gray-500">${Number(o.amount).toFixed(2)} · {o.status}
                    {o.is_final_sale ? ' · final sale' : ''}{o.already_refunded ? ' · refunded' : ''}</span>
                </div>
              ))}
            </div>
            <div>
              <div className="mb-1 text-xs font-semibold uppercase text-gray-400">Refund decisions ({detail.refund_decisions.length})</div>
              {detail.refund_decisions.map((r: any) => (
                <div key={r.id} className="flex justify-between border-b border-gray-100 py-1">
                  <span>{r.order_id} · {r.decision}{r.resolution ? ` → ${r.resolution}` : ''}</span>
                  <span className="text-gray-400">{new Date(r.created_at).toLocaleDateString()}</span>
                </div>
              ))}
            </div>
            <div>
              <div className="mb-1 text-xs font-semibold uppercase text-gray-400">Sessions ({detail.sessions.length})</div>
              {detail.sessions.map((s: any) => (
                <a key={s.id} href={`/admin/sessions/${s.id}`} target="_blank" rel="noopener noreferrer"
                   className="block text-green-600 hover:underline">{s.id}</a>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
