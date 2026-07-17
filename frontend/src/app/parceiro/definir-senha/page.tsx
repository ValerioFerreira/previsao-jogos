"use client";
import React, { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Loader2, CheckCircle2 } from "lucide-react";
import { useAuth } from "@/lib/AuthContext";
import { authApi } from "@/lib/authApi";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";

function DefinirSenhaForm() {
  const { setSession } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token") || "";

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    if (!token) { setErr("Link de convite inválido ou incompleto."); return; }
    if (password !== confirm) { setErr("As senhas não coincidem."); return; }
    setBusy(true);
    try {
      const t = await authApi.setPassword(token, password);
      await setSession(t);
      router.push("/parceiro");
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
          <CardTitle className="text-2xl">Bem-vindo(a) ao time de parceiros</CardTitle>
          <CardDescription>Defina sua senha para acessar o portal do parceiro.</CardDescription>
        </CardHeader>
        <CardContent>
          {err && <div className="mb-4 text-sm rounded-md bg-red-500/10 text-red-600 p-3">{err}</div>}
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
              <Input id="pw" type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                placeholder="mín. 8 caracteres, com letras e números" required autoComplete="new-password" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="pw2">Confirmar senha</Label>
              <Input id="pw2" type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required autoComplete="new-password" />
            </div>
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
