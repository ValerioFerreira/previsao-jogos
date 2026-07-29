"use client";
import React, { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Loader2, LogIn, Eye, EyeOff, AlertTriangle } from "lucide-react";
import { useAuth } from "@/lib/AuthContext";
import { authApi } from "@/lib/authApi";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/use-toast";

export default function LoginPage() {
  const { isAuthenticated, user, setSession } = useAuth();
  const { toast } = useToast();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [capsLockActive, setCapsLockActive] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [forgot, setForgot] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    if (isAuthenticated) router.replace(user?.role === "partner" ? "/parceiro/dashboard" : "/");
  }, [isAuthenticated, user, router]);

  const handleKeyEvents = (e: React.KeyboardEvent<HTMLInputElement>) => {
    setCapsLockActive(e.getModifierState("CapsLock"));
  };

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setBusy(true);
    try {
      const t = await authApi.login(email.trim(), password);
      await setSession(t);
      toast({
        title: "Login realizado com sucesso!",
        description: `Bem-vindo(a) de volta, ${t.user.full_name}!`,
      });
      console.log("[Auth] Login bem-sucedido para:", email);
      router.push(t.user.role === "partner" ? "/parceiro/dashboard" : "/");
    } catch (e) {
      const errorMsg = (e as Error).message || "Não foi possível entrar.";
      setErr(errorMsg);
      toast({
        variant: "destructive",
        title: "Falha no login",
        description: errorMsg,
      });
      console.error("[Auth] Erro ao efetuar login:", e);
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
      const successMsg = "Se o e-mail existir, enviamos um código para redefinir a senha.";
      setMsg(successMsg);
      toast({
        title: "Código enviado",
        description: successMsg,
      });
      console.log("[Auth] Solicitação de redefinição enviada para:", email);
    } catch (e) {
      const errorMsg = (e as Error).message || "Erro ao solicitar redefinição.";
      setErr(errorMsg);
      toast({
        variant: "destructive",
        title: "Erro ao enviar código",
        description: errorMsg,
      });
      console.error("[Auth] Erro ao enviar código de recuperação:", e);
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
                <Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value.toLowerCase().replace(/\s/g, ""))} required />
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
                <Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value.toLowerCase().replace(/\s/g, ""))} required autoComplete="email" />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="password">Senha</Label>
                <div className="relative">
                  <Input
                    id="password"
                    type={showPassword ? "text" : "password"}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    onKeyDown={handleKeyEvents}
                    onKeyUp={handleKeyEvents}
                    required
                    autoComplete="current-password"
                    className="pr-10"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors p-1"
                    title={showPassword ? "Ocultar senha" : "Visualizar senha"}
                  >
                    {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
                {capsLockActive && (
                  <div className="flex items-center gap-1.5 text-xs text-amber-500 font-medium pt-1">
                    <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                    Caps Lock está ativado!
                  </div>
                )}
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
