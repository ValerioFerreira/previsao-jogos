// Cliente de API autenticado da camada de usuários/monetização.
// Guarda os tokens no localStorage, injeta Bearer e faz refresh automático no 401.

const API_URL = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000";

const ACCESS_KEY = "apostai_access";
const REFRESH_KEY = "apostai_refresh";

export type UserPublic = {
  id: string;
  full_name: string;
  email: string;
  cpf: string;
  phone: string;
  status: string;
  role: string;
  referral_code?: string | null;
};

export type ReferralInfo = {
  referral_code: string | null;
  share_link: string | null;
  completed_referrals: number;
  credits_earned: string;
};

export type TokenResponse = {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: UserPublic;
};

export type Wallet = {
  available_balance: string;
  reserved_balance: string;
  currency: string;
};

// ---------------------------------------------------------------- tokens
export const tokens = {
  access: () => (typeof window !== "undefined" ? localStorage.getItem(ACCESS_KEY) : null),
  refresh: () => (typeof window !== "undefined" ? localStorage.getItem(REFRESH_KEY) : null),
  set(t: { access_token: string; refresh_token: string }) {
    localStorage.setItem(ACCESS_KEY, t.access_token);
    localStorage.setItem(REFRESH_KEY, t.refresh_token);
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
};

async function raw<T>(path: string, init?: RequestInit, auth = false): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((init?.headers as Record<string, string>) || {}),
  };
  if (auth) {
    const a = tokens.access();
    if (a) headers["Authorization"] = `Bearer ${a}`;
  }
  const res = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const err = new Error(body?.detail || `Erro ${res.status}`) as Error & { status?: number };
    err.status = res.status;
    throw err;
  }
  return (res.status === 204 ? (null as T) : ((await res.json()) as T));
}

async function tryRefresh(): Promise<boolean> {
  const r = tokens.refresh();
  if (!r) return false;
  try {
    const t = await raw<TokenResponse>("/auth/refresh", {
      method: "POST",
      body: JSON.stringify({ refresh_token: r }),
    });
    tokens.set(t);
    return true;
  } catch (e) {
    // Só limpamos os tokens quando o servidor recusa explicitamente o refresh
    // (401/400 — token inválido/expirado). Erros transitórios (rede, cold start
    // do backend) não devem derrubar a sessão do usuário silenciosamente.
    const status = (e as { status?: number }).status;
    if (status === 401 || status === 400) {
      tokens.clear();
      window.dispatchEvent(new CustomEvent("apostai:session-expired"));
    }
    return false;
  }
}

// fetch autenticado com 1 retry após refresh
export async function authFetch<T>(path: string, init?: RequestInit): Promise<T> {
  try {
    return await raw<T>(path, init, true);
  } catch (e) {
    const status = (e as { status?: number }).status;
    if (status === 401 && (await tryRefresh())) {
      return await raw<T>(path, init, true);
    }
    throw e;
  }
}

// ---------------------------------------------------------------- auth
export const authApi = {
  register: (d: { full_name: string; email: string; cpf: string; phone: string; referral_code?: string; referral_source?: string }) =>
    raw<{ message: string }>("/auth/register", { method: "POST", body: JSON.stringify(d) }),

  resendOtp: (email: string, purpose = "email_verify") =>
    raw<{ message: string }>("/auth/resend-otp", { method: "POST", body: JSON.stringify({ email, purpose }) }),

  verifyEmail: (email: string, code: string) =>
    raw<{ setup_token: string }>("/auth/verify-email", { method: "POST", body: JSON.stringify({ email, code }) }),

  setPassword: (setup_token: string, password: string) =>
    raw<TokenResponse>("/auth/set-password", { method: "POST", body: JSON.stringify({ setup_token, password }) }),

  login: (email: string, password: string) =>
    raw<TokenResponse>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),

  loginDemo: (email: string, password: string, cpf: string) =>
    raw<TokenResponse>("/auth/login-demo", { method: "POST", body: JSON.stringify({ email, password, cpf }) }),

  logout: () => {
    const r = tokens.refresh();
    tokens.clear();
    if (r) raw("/auth/logout", { method: "POST", body: JSON.stringify({ refresh_token: r }) }).catch(() => {});
  },

  me: () => authFetch<UserPublic>("/auth/me"),

  myReferral: () => authFetch<ReferralInfo>("/auth/me/referral"),

  forgotPassword: (email: string) =>
    raw<{ message: string }>("/auth/forgot-password", { method: "POST", body: JSON.stringify({ email }) }),

  resetPassword: (email: string, code: string, password: string) =>
    raw<{ message: string }>("/auth/reset-password", { method: "POST", body: JSON.stringify({ email, code, password }) }),
};

// ---------------------------------------------------------------- wallet
export const walletApi = {
  get: () => authFetch<Wallet>("/wallet"),
};
