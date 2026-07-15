"use client";
import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { authApi, walletApi, tokens, type UserPublic, type Wallet, type TokenResponse } from "@/lib/authApi";
import { attachSignupIfReferred } from "@/lib/affiliatesApi";

type AuthState = {
  user: UserPublic | null;
  wallet: Wallet | null;
  loading: boolean;
  isAuthenticated: boolean;
  sessionExpiredMsg: string | null;
  dismissSessionExpiredMsg: () => void;
  login: (email: string, password: string) => Promise<void>;
  setSession: (t: TokenResponse) => Promise<void>;
  logout: () => void;
  refreshWallet: () => Promise<void>;
};

const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserPublic | null>(null);
  const [wallet, setWallet] = useState<Wallet | null>(null);
  const [loading, setLoading] = useState(true);
  const [sessionExpiredMsg, setSessionExpiredMsg] = useState<string | null>(null);

  const refreshWallet = useCallback(async () => {
    try {
      setWallet(await walletApi.get());
    } catch {
      /* silencioso */
    }
  }, []);

  const loadSession = useCallback(async () => {
    if (!tokens.access()) {
      setLoading(false);
      return;
    }
    try {
      const me = await authApi.me();
      setUser(me);
      await refreshWallet();
    } catch (e) {
      // Só derruba a sessão quando o servidor recusa explicitamente o token
      // (401 — inválido/expirado, já sem refresh válido). Erros transitórios
      // (rede instável, backend em cold start) não devem deslogar o usuário
      // silenciosamente — mantemos os tokens para tentar de novo depois.
      const status = (e as { status?: number }).status;
      if (status === 401) {
        tokens.clear();
        setUser(null);
      }
    } finally {
      setLoading(false);
    }
  }, [refreshWallet]);

  useEffect(() => {
    loadSession();
  }, [loadSession]);

  // Disparado pelo authApi quando um refresh de token é recusado pelo servidor
  // em pleno uso — a sessão caiu de verdade, então avisamos o usuário em vez de
  // simplesmente sumir com os dados da tela.
  useEffect(() => {
    const onExpired = () => {
      setUser(null);
      setWallet(null);
      setSessionExpiredMsg("Sua sessão expirou por inatividade. Faça login novamente para continuar.");
    };
    window.addEventListener("apostai:session-expired", onExpired);
    return () => window.removeEventListener("apostai:session-expired", onExpired);
  }, []);

  const dismissSessionExpiredMsg = useCallback(() => setSessionExpiredMsg(null), []);

  const applySession = useCallback(
    async (t: TokenResponse) => {
      tokens.set(t);
      setUser(t.user);
      await refreshWallet();
      attachSignupIfReferred();
    },
    [refreshWallet],
  );

  const login = useCallback(
    async (email: string, password: string) => {
      const t = await authApi.login(email, password);
      await applySession(t);
    },
    [applySession],
  );

  const logout = useCallback(() => {
    authApi.logout();
    setUser(null);
    setWallet(null);
  }, []);

  return (
    <Ctx.Provider
      value={{
        user,
        wallet,
        loading,
        isAuthenticated: !!user,
        sessionExpiredMsg,
        dismissSessionExpiredMsg,
        login,
        setSession: applySession,
        logout,
        refreshWallet,
      }}
    >
      {children}
    </Ctx.Provider>
  );
}

export function useAuth(): AuthState {
  const c = useContext(Ctx);
  if (!c) throw new Error("useAuth deve ser usado dentro de <AuthProvider>.");
  return c;
}
