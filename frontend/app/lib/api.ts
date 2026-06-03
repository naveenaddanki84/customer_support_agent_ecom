const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export interface Customer { id: number; name: string; email: string; tier: string }
export interface UserSession {
  id: string; title: string; message_count: number
  last_agent: string | null; last_decision: string | null; updated_at: string
}
export interface AdminSession {
  id: string; user_id: string; message_count: number
  has_escalation: boolean; last_activity: string | null; updated_at: string
}
export interface Escalation {
  id: string; order_id: string; session_id: string | null; amount: number | null
  reason: string; customer_name: string | null; customer_email: string | null
  item: string | null; resolution: string | null; created_at: string
}
export interface ToolCall { tool: string; args: Record<string, unknown>; result: string }
export interface AgentLog {
  id: string; user_message: string; handling_agent: string | null
  router_intent: string | null; router_reasoning: string | null
  refund_decision: string | null; guardrails_score: string | null
  tool_trace: ToolCall[]; final_response: string | null; created_at: string
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`)
  if (!res.ok) throw new Error(`GET ${path} -> ${res.status}`)
  return res.json()
}
async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`POST ${path} -> ${res.status}`)
  return res.json()
}

export const api = {
  customers: () => getJson<Customer[]>(`/api/v1/customers`),
  userSessions: (userId: string) =>
    getJson<UserSession[]>(`/api/v1/users/${encodeURIComponent(userId)}/sessions`),
  createSession: (userId: string) =>
    postJson<{ id: string }>(`/api/v1/sessions`, { user_id: userId, metadata: {} }),
  sessionMessages: (id: string) => getJson<unknown[]>(`/api/v1/sessions/${id}/messages`),
  adminSessions: () => getJson<AdminSession[]>(`/api/v1/admin/sessions?limit=100`),
  adminSession: (id: string) =>
    getJson<{ messages: any[]; logs: AgentLog[] }>(`/api/v1/admin/sessions/${id}`),
  adminCustomer: (id: number) => getJson<any>(`/api/v1/admin/customers/${id}`),
  escalations: () => getJson<Escalation[]>(`/api/v1/admin/escalations`),
  resolveEscalation: (id: string, action: 'approved' | 'rejected', reviewer = 'admin') =>
    postJson<{ resolution: string }>(`/api/v1/admin/escalations/${id}/resolve`, { action, reviewer }),
}
