// Rastreamento de parceiro (?ref=código) + solicitação de parceria + portal do parceiro.
// Nomes internos seguem em inglês ("affiliate") — o rótulo em português é só na UI.
import { authFetch } from "@/lib/authApi";

const ANON_KEY = "apostai_anon_id";
const REF_CODE_KEY = "apostai_ref_code";
const API_URL = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000";

function getAnonId(): string {
  if (typeof window === "undefined") return "";
  let id = localStorage.getItem(ANON_KEY);
  if (!id) {
    id = `anon_${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`;
    localStorage.setItem(ANON_KEY, id);
  }
  return id;
}

/** Chamar uma vez ao carregar qualquer página pública: captura ?ref= e registra o clique. */
export function captureReferralFromUrl() {
  if (typeof window === "undefined") return;
  const params = new URLSearchParams(window.location.search);
  const code = params.get("ref");
  if (!code) return;
  // guarda o código para pré-preencher o cupom no checkout (1ª compra); o backend revalida.
  try { localStorage.setItem(REF_CODE_KEY, code); } catch { /* ignora */ }
  const anon_id = getAnonId();
  fetch(`${API_URL}/affiliates/track`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code, anon_id }),
  }).catch(() => { /* silencioso — não deve travar navegação */ });
}

/** Chamar quando uma sessão autenticada é estabelecida (login/cadastro concluído). */
export function attachSignupIfReferred() {
  if (typeof window === "undefined") return;
  const anon_id = localStorage.getItem(ANON_KEY);
  if (!anon_id) return;
  authFetch("/affiliates/attach", { method: "POST", body: JSON.stringify({ anon_id }) }).catch(() => {});
}

export type AffiliatePortalStats = {
  code: string;
  link: string;
  clicks: number;
  signups: number;
  buyers: number;
  revenue_brl: string;
  commission_due_brl: string;
  commission_paid_brl: string;
};

export type TimeseriesPoint = {
  bucket: string;
  clicks: number;
  conversions: number;
  revenue_brl: string;
  commission_brl: string;
};

export type TimeseriesResponse = {
  granularity: string;
  items: TimeseriesPoint[];
};

export type PartnerApplication = {
  full_name: string;
  cpf: string;
  email: string;
  phone: string;
  payment_type: "pf" | "pj";
  discount_pcts: number[];
  code_prefix?: string;
  ref_partner?: string;
};

export type CodeSuggestion = { prefix: string; code: string };

export type CouponRequest = {
  id: string;
  requested_code: string;
  discount_pct: string;
  status: "pending" | "approved" | "rejected";
  limit_type?: "days" | "revenue" | null;
  limit_days?: number | null;
  limit_revenue_brl?: string | null;
  rejection_reason?: string | null;
  coupon_code?: string | null;
  created_at: string;
  decided_at?: string | null;
};

export type ReferredPartner = {
  id: string;
  name: string;
  code: string;
  status: string;
  users_count: number;
  revenue_brl: string;
  override_due_brl: string;
};

export type ReferredPartnersResponse = {
  override_pct: string;
  total_override_due_brl: string;
  items: ReferredPartner[];
};

/** Lê o código de indicação guardado (?ref=) para pré-preencher o cupom no checkout. */
export function getStoredRefCode(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(REF_CODE_KEY);
}

export const affiliatesApi = {
  me: () => authFetch<AffiliatePortalStats>("/affiliates/me"),
  apply: (data: PartnerApplication) =>
    fetch(`${API_URL}/affiliates/apply`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data),
    }).then(async (res) => {
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || `Erro ${res.status}`);
      }
      return res.json() as Promise<{ ok: boolean; message: string }>;
    }),
  suggestCode: (full_name: string) =>
    fetch(`${API_URL}/affiliates/suggest-code?${new URLSearchParams({ full_name, discount_pct: "15" })}`)
      .then(async (res) => {
        if (!res.ok) throw new Error(`Erro ${res.status}`);
        return res.json() as Promise<CodeSuggestion>;
      }),
  portalMe: () => authFetch<AffiliatePortalStats>("/affiliates/portal/me"),
  portalTimeseries: (granularity: "day" | "month" = "day") =>
    authFetch<TimeseriesResponse>(`/affiliates/portal/timeseries?granularity=${granularity}`),
  // Cupom promocional solicitado pelo parceiro
  createCouponRequest: (requested_code: string, discount_pct: number) =>
    authFetch<CouponRequest>("/affiliates/coupon-requests", {
      method: "POST", body: JSON.stringify({ requested_code, discount_pct }),
    }),
  listCouponRequests: () => authFetch<CouponRequest[]>("/affiliates/coupon-requests"),
  // Parceiros indicados por este parceiro
  referredPartners: () => authFetch<ReferredPartnersResponse>("/affiliates/portal/referred-partners"),
  // Resolve o cupom de convite a partir do ?ref= (pré-preenchimento no checkout)
  resolveCoupon: (ref: string) =>
    fetch(`${API_URL}/affiliates/resolve-coupon?ref=${encodeURIComponent(ref)}`)
      .then((res) => (res.ok ? res.json() : { coupon_code: null }))
      .then((b) => b.coupon_code as string | null)
      .catch(() => null),
};
