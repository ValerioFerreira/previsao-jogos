// Chamadas do Painel Administrativo (exigem papel admin).
import { authFetch } from "@/lib/authApi";

export type AdminUser = {
  id: string; full_name: string; email: string; cpf: string; phone: string;
  status: string; role: string; created_at: string; last_login_at: string | null;
  available_balance: string | null; reserved_balance: string | null;
};

export type AuditEntry = {
  id: string; admin_id: string | null; admin_name: string | null; admin_email: string | null;
  action: string; target_type: string | null;
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

  dashboard: () => authFetch<Record<string, unknown>>("/admin/analytics/dashboard"),

  coupons: () => authFetch<{ items: Record<string, unknown>[] }>("/admin/coupons"),
  createCoupon: (body: Record<string, unknown>) =>
    authFetch("/admin/coupons", { method: "POST", body: JSON.stringify(body) }),
  patchCoupon: (id: string, body: Record<string, unknown>) =>
    authFetch(`/admin/coupons/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteCoupon: (id: string) => authFetch(`/admin/coupons/${id}`, { method: "DELETE" }),
  couponAnalytics: () => authFetch<{ items: Record<string, unknown>[] }>("/admin/coupons/analytics"),

  packages: () => authFetch<{ items: Record<string, unknown>[] }>("/admin/packages"),
  createPackage: (body: Record<string, unknown>) =>
    authFetch("/admin/packages", { method: "POST", body: JSON.stringify(body) }),
  patchPackage: (id: string, body: Record<string, unknown>) =>
    authFetch(`/admin/packages/${id}`, { method: "PATCH", body: JSON.stringify(body) }),

  affiliates: (status?: string) =>
    authFetch<{ items: Record<string, unknown>[] }>(`/admin/affiliates${status ? `?status=${status}` : ""}`),
  affiliateDetail: (id: string) => authFetch<Record<string, unknown>>(`/admin/affiliates/${id}`),
  createAffiliate: (body: Record<string, unknown>) =>
    authFetch("/admin/affiliates", { method: "POST", body: JSON.stringify(body) }),
  patchAffiliate: (id: string, body: Record<string, unknown>) =>
    authFetch(`/admin/affiliates/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  approveAffiliate: (id: string, code?: string) =>
    authFetch(`/admin/affiliates/${id}/approve`, { method: "POST", body: JSON.stringify({ code: code || undefined }) }),
  rejectAffiliate: (id: string, reason?: string) =>
    authFetch(`/admin/affiliates/${id}/reject`, { method: "POST", body: JSON.stringify({ reason }) }),
  resendAffiliateInvite: (id: string) => authFetch(`/admin/affiliates/${id}/resend-invite`, { method: "POST" }),
  setAffiliateDemoAccess: (id: string, enabled: boolean) =>
    authFetch(`/admin/affiliates/${id}/demo-access`, { method: "PATCH", body: JSON.stringify({ enabled }) }),
  deleteAffiliate: (id: string) => authFetch(`/admin/affiliates/${id}`, { method: "DELETE" }),
  affiliatePayments: (affiliateId: string) =>
    authFetch<{ items: Record<string, unknown>[] }>(`/admin/affiliates/${affiliateId}/payments`),
  createAffiliatePayment: (affiliateId: string, body: Record<string, unknown>) =>
    authFetch(`/admin/affiliates/${affiliateId}/payments`, { method: "POST", body: JSON.stringify(body) }),
  demoUsage: () =>
    authFetch<{ items: { cpf: string; affiliate_name: string | null; logins: number; analyses: number; last_login_at: string }[] }>("/admin/demo-usage"),

  banners: () => authFetch<{ items: Record<string, unknown>[] }>("/admin/banners"),
  createBanner: (body: Record<string, unknown>) =>
    authFetch("/admin/banners", { method: "POST", body: JSON.stringify(body) }),
  patchBanner: (id: string, body: Record<string, unknown>) =>
    authFetch(`/admin/banners/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteBanner: (id: string) => authFetch(`/admin/banners/${id}`, { method: "DELETE" }),

  deepAnalyses: () => authFetch<{ items: Record<string, unknown>[] }>("/admin/deep-analyses"),
  upsertDeepAnalysis: (body: Record<string, unknown>) =>
    authFetch("/admin/deep-analyses", { method: "POST", body: JSON.stringify(body) }),
  deleteDeepAnalysis: (fixtureId: number) => authFetch(`/admin/deep-analyses/${fixtureId}`, { method: "DELETE" }),

  campaigns: () => authFetch<{ items: Record<string, unknown>[] }>("/admin/campaigns"),
  createCampaign: (body: Record<string, unknown>) =>
    authFetch("/admin/campaigns", { method: "POST", body: JSON.stringify(body) }),
  patchCampaign: (id: string, body: Record<string, unknown>) =>
    authFetch(`/admin/campaigns/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteCampaign: (id: string) => authFetch(`/admin/campaigns/${id}`, { method: "DELETE" }),
  campaignDashboard: (id: string) => authFetch<Record<string, unknown>>(`/admin/campaigns/${id}/dashboard`),
  addCampaignPackage: (id: string, packageId: string) =>
    authFetch(`/admin/campaigns/${id}/packages/${packageId}`, { method: "POST" }),
  removeCampaignPackage: (id: string, packageId: string) =>
    authFetch(`/admin/campaigns/${id}/packages/${packageId}`, { method: "DELETE" }),
  addCampaignCoupon: (id: string, couponId: string) =>
    authFetch(`/admin/campaigns/${id}/coupons/${couponId}`, { method: "POST" }),
  removeCampaignCoupon: (id: string, couponId: string) =>
    authFetch(`/admin/campaigns/${id}/coupons/${couponId}`, { method: "DELETE" }),
  addCampaignAffiliate: (id: string, affiliateId: string) =>
    authFetch(`/admin/campaigns/${id}/affiliates/${affiliateId}`, { method: "POST" }),
  removeCampaignAffiliate: (id: string, affiliateId: string) =>
    authFetch(`/admin/campaigns/${id}/affiliates/${affiliateId}`, { method: "DELETE" }),

  settings: () => authFetch<{ items: Record<string, unknown>[] }>("/admin/settings"),
  setSetting: (key: string, body: { value: Record<string, unknown>; description?: string }) =>
    authFetch(`/admin/settings/${key}`, { method: "PUT", body: JSON.stringify(body) }),

  publishLegal: (body: { type: string; title: string; body_md: string }) =>
    authFetch("/admin/legal/publish", { method: "POST", body: JSON.stringify(body) }),
};
