// Rastreamento de afiliado/influenciador (?ref=código) + portal do afiliado.
import { authFetch } from "@/lib/authApi";

const ANON_KEY = "apostai_anon_id";
const AFFILIATE_TOKEN_KEY = "apostai_affiliate_token";
const API_URL = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000";

// Sessão própria do portal do afiliado (login por e-mail+CPF, sem conta de usuário) —
// token guardado à parte do AuthContext normal, sem refresh (TTL de 12h no backend).
export const affiliateTokens = {
  get: () => (typeof window !== "undefined" ? localStorage.getItem(AFFILIATE_TOKEN_KEY) : null),
  set: (t: string) => { if (typeof window !== "undefined") localStorage.setItem(AFFILIATE_TOKEN_KEY, t); },
  clear: () => { if (typeof window !== "undefined") localStorage.removeItem(AFFILIATE_TOKEN_KEY); },
};

async function affiliateFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const token = affiliateTokens.get();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((init?.headers as Record<string, string>) || {}),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail || `Erro ${res.status}`);
  }
  return (res.status === 204 ? (null as T) : ((await res.json()) as T));
}

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

export const affiliatesApi = {
  me: () => authFetch<AffiliatePortalStats>("/affiliates/me"),
  // portal próprio (login por e-mail+CPF, ver affiliateTokens acima)
  login: (email: string, cpf: string) =>
    affiliateFetch<{ access_token: string; token_type: string; expires_in: number }>("/affiliates/login", {
      method: "POST", body: JSON.stringify({ email, cpf }),
    }),
  portalMe: () => affiliateFetch<AffiliatePortalStats>("/affiliates/portal/me"),
  portalTimeseries: (granularity: "day" | "month" = "day") =>
    affiliateFetch<TimeseriesResponse>(`/affiliates/portal/timeseries?granularity=${granularity}`),
};
