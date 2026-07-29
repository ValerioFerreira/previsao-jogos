"use client";
import React, { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Loader2, CheckCircle2, Eye, EyeOff, AlertTriangle } from "lucide-react";
import { useAuth } from "@/lib/AuthContext";
import { authApi } from "@/lib/authApi";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/use-toast";

function DefinirSenhaForm() {
  const { setSession } = useAuth();
  const { toast } = useToast();
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token") || "";

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [capsLockActive, setCapsLockActive] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const handleKeyEvents = (e: React.KeyboardEvent<HTMLInputElement>) => {
    setCapsLockActive(e.getModifierState("CapsLock"));
  };

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    if (!token) {
      const msg = "Link de convite inválido ou incompleto.";
      setErr(msg);
      toast({ variant: "destructive", title: "Erro de Ativação", description: msg });
      return;
    }
    if (password !== confirm) {
      const msg = "As senhas não coincidem.";
      setErr(msg);
      toast({ variant: "destructive", title: "Erro de Validação", description: msg });
      return;
    }
    setBusy(true);
    try {
      const t = await authApi.setPassword(token, password);
      await setSession(t);
      toast({
        title: "Senha cadastrada com sucesso!",
        description: "Bem-vindo(a) ao portal do parceiro!",
      });
      console.log("[Partner] Senha definida com sucesso para token:", token.slice(0, 10) + "...");
      router.push("/parceiro/dashboard");
    } catch (e) {
      const errorMsg = (e as Error).message || "Não foi possível ativar a conta. O convite pode estar expirado.";
      setErr(errorMsg);
      toast({
        variant: "destructive",
        title: "Erro ao ativar conta",
        description: errorMsg,
      });
      console.error("[Partner] Erro ao definir senha com token:", e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-md mx-auto mt-6 sm:mt-12">
      <Card>
        <CardHeader>
          <CardTitle className="text-2xl">Bem-vindo(a) ao time de parceiros</CardTitle>
          <CardDescription>Defina sua senha para acessar o portal do parceiro.</CardDescription>
        </CardHeader>
        <CardContent>
          {err && (
            <div className="mb-4 text-sm rounded-md bg-red-500/10 text-red-600 p-3 space-y-1">
              <div>{err}</div>
              {err.toLowerCase().includes("expirado") && (
                <div className="text-xs text-red-500/80 font-medium">
                  Solicite ao administrador a emissão de um novo convite.
                </div>
              )}
            </div>
          )}
          {!token && (
            <div className="mb-4 text-sm rounded-md bg-amber-500/10 text-amber-600 p-3">
              Este link parece incompleto. Verifique se você abriu o link enviado por e-mail corretamente.
            </div>
          )}
          <form onSubmit={submit} className="space-y-4">
            <div className="flex items-center gap-2 text-sm text-emerald-600">
              <CheckCircle2 className="w-4 h-4" /> Solicitação aprovada — falta só a senha.
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="pw">Senha</Label>
              <div className="relative">
                <Input
                  id="pw"
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  onKeyDown={handleKeyEvents}
                  onKeyUp={handleKeyEvents}
                  placeholder="mín. 8 caracteres"
                  required
                  autoComplete="new-password"
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
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="pw2">Confirmar senha</Label>
              <Input
                id="pw2"
                type={showPassword ? "text" : "password"}
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                onKeyDown={handleKeyEvents}
                onKeyUp={handleKeyEvents}
                required
                autoComplete="new-password"
              />
            </div>
            {capsLockActive && (
              <div className="flex items-center gap-1.5 text-xs text-amber-500 font-medium pt-1">
                <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                Caps Lock está ativado!
              </div>
            )}
            <Button type="submit" className="w-full" disabled={busy || !token}>
              {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : "Definir senha e entrar"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

export default function DefinirSenhaPage() {
  return (
    <Suspense fallback={<div className="flex justify-center py-20"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>}>
      <DefinirSenhaForm />
    </Suspense>
  );
}
