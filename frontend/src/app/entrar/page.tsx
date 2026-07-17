"use client";
import React, { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Loader2, LogIn } from "lucide-react";
import { useAuth } from "@/lib/AuthContext";
import { authApi } from "@/lib/authApi";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";

export default function LoginPage() {
  const { isAuthenticated, user, setSession } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [forgot, setForgot] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    if (isAuthenticated) router.replace(user?.role === "partner" ? "/parceiro" : "/");
  }, [isAuthenticated, user, router]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setBusy(true);
    try {
      const t = await authApi.login(email.trim(), password);
      await setSession(t);
      router.push(t.user.role === "partner" ? "/parceiro" : "/");
    } catch (e) {
      setErr((e as Error).message || "Não foi possível entrar.");
    } finally {
      setBusy(false);
    }
  }

  async function sendReset(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setBusy(true);
    try {
      await authApi.forgotPassword(email.trim());
      setMsg("Se o e-mail existir, enviamos um código para redefinir a senha.");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-md mx-auto mt-6 sm:mt-12">
      <Card>
        <CardHeader>
          <CardTitle className="text-2xl">{forgot ? "Recuperar senha" : "Entrar"}</CardTitle>
          <CardDescription>
            {forgot
              ? "Informe seu e-mail para receber um código de redefinição."
              : "Acesse sua conta para gerar análises e usar seus créditos."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {msg && <div className="mb-4 text-sm rounded-md bg-emerald-500/10 text-emerald-600 p-3">{msg}</div>}
          {err && <div className="mb-4 text-sm rounded-md bg-red-500/10 text-red-600 p-3">{err}</div>}

          {forgot ? (
            <form onSubmit={sendReset} className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="email">E-mail</Label>
                <Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
              </div>
              <Button type="submit" className="w-full" disabled={busy}>
                {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : "Enviar código"}
              </Button>
              <button type="button" className="text-sm text-muted-foreground hover:text-foreground w-full" onClick={() => { setForgot(false); setMsg(null); setErr(null); }}>
                Voltar ao login
              </button>
              {msg && (
                <Link href="/redefinir-senha" className="block text-center text-sm text-primary underline">
                  Já tenho o código → redefinir senha
                </Link>
              )}
            </form>
          ) : (
            <form onSubmit={submit} className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="email">E-mail</Label>
                <Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="password">Senha</Label>
                <Input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="current-password" />
              </div>
              <Button type="submit" className="w-full" disabled={busy}>
                {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : (<><LogIn className="w-4 h-4 mr-2" /> Entrar</>)}
              </Button>
              <div className="flex items-center justify-between text-sm">
                <button type="button" className="text-muted-foreground hover:text-foreground" onClick={() => { setForgot(true); setErr(null); }}>
                  Esqueci a senha
                </button>
                <Link href="/cadastro" className="text-primary hover:underline">Criar conta</Link>
              </div>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
