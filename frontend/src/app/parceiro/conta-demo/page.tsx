"use client";
import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Sparkles } from "lucide-react";
import { useAuth } from "@/lib/AuthContext";
import { authApi } from "@/lib/authApi";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";

export default function ContaDemoPage() {
  const { setSession } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [cpf, setCpf] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setBusy(true);
    try {
      const t = await authApi.loginDemo(email.trim(), password, cpf.replace(/\D/g, ""));
      await setSession(t);
      router.push("/");
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
          <CardTitle className="text-2xl flex items-center gap-2"><Sparkles className="w-5 h-5 text-primary" /> Conta demo</CardTitle>
          <CardDescription>
            Use as credenciais da conta demo fornecidas pelo time ApostAI, junto do seu próprio CPF
            (usamos o CPF só para controlar quem tem acesso à conta compartilhada).
          </CardDescription>
        </CardHeader>
        <CardContent>
          {err && <div className="mb-4 text-sm rounded-md bg-red-500/10 text-red-600 p-3">{err}</div>}
          <form onSubmit={submit} className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="email">E-mail da conta demo</Label>
              <Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="password">Senha da conta demo</Label>
              <Input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="off" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="cpf">Seu CPF (de parceiro)</Label>
              <Input id="cpf" value={cpf} onChange={(e) => setCpf(e.target.value)} placeholder="000.000.000-00" required />
            </div>
            <Button type="submit" className="w-full" disabled={busy}>
              {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : "Entrar na conta demo"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
