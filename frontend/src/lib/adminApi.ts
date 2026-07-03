// Chamadas do Painel Administrativo (exigem papel admin).
import { authFetch } from "@/lib/authApi";

export type AdminUser = {
  id: string; full_name: string; email: string; cpf: string; phone: string;
  status: string; role: string; created_at: string; last_login_at: string | null;
  available_balance: string | null; reserved_balance: string | null;
};

export type AuditEntry = {
  id: string; admin_id: string | null; action: string; target_type: string | null;
  target_id: string | null; before: unknown; after: unknown; created_at: string;
};

export const adminApi = {
  users: (q = "", limit = 50, offset = 0) =>
    authFetch<{ items: AdminUser[]; total: number }>(`/admin/users?limit=${limit}&offset=${offset}${q ? `&q=${encodeURIComponent(q)}` : ""}`),
  block: (id: string, reason?: string) =>
    authFetch(`/admin/users/${id}/block`, { method: "POST", body: JSON.stringify({ reason }) }),
  unblock: (id: string) => authFetch(`/admin/users/${id}/unblock`, { method: "POST" }),
  adjustCredits: (id: string, body: { amount: string; kind: string; reason: string }) =>
    authFetch<{ available_balance: string }>(`/admin/users/${id}/credits`, { method: "POST", body: JSON.stringify(body) }),

  payments: (limit = 50) => authFetch<{ items: Record<string, unknown>[]; total: number }>(`/admin/payments?limit=${limit}`),
  analyses: (limit = 50) => authFetch<{ items: Record<string, unknown>[]; total: number }>(`/admin/analyses?limit=${limit}`),
  bets: (limit = 50) => authFetch<{ items: Record<string, unknown>[]; total: number }>(`/admin/bets?limit=${limit}`),

  promotions: () => authFetch<{ items: Record<string, unknown>[] }>("/admin/promotions"),
  createPromotion: (body: { code: string; name: string; type: string; max_odd?: string }) =>
    authFetch("/admin/promotions", { method: "POST", body: JSON.stringify(body) }),
  patchPromotion: (id: string, body: Record<string, unknown>) =>
    authFetch(`/admin/promotions/${id}`, { method: "PATCH", body: JSON.stringify(body) }),

  audit: (limit = 50) => authFetch<{ items: AuditEntry[]; total: number }>(`/admin/audit?limit=${limit}`),
};
