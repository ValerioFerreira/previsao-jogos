"use client";
import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, LogIn } from "lucide-react";
import { affiliatesApi, affiliateTokens } from "@/lib/affiliatesApi";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";

export default function AfiliadoEntrarPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [cpf, setCpf] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setErr(null);
    try {
      const res = await affiliatesApi.login(email, cpf);
      affiliateTokens.set(res.access_token);
      router.replace("/afiliado");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-sm mx-auto py-12">
      <Card>
        <CardHeader><CardTitle className="text-lg flex items-center gap-2"><LogIn className="w-4 h-4" /> Portal do Afiliado</CardTitle></CardHeader>
        <CardContent>
          <form onSubmit={submit} className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="email">E-mail cadastrado</Label>
              <input
                id="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-md border border-border/50 bg-background px-3 py-2 text-sm"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="cpf">CPF</Label>
              <input
                id="cpf" type="text" required value={cpf} onChange={(e) => setCpf(e.target.value)}
                placeholder="somente números" className="w-full rounded-md border border-border/50 bg-background px-3 py-2 text-sm"
              />
            </div>
            {err && <div className="text-sm rounded-md bg-red-500/10 text-red-600 p-3">{err}</div>}
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Entrar"}
            </Button>
          </form>
          <p className="text-xs text-muted-foreground mt-4">
            O acesso é feito com o e-mail e CPF informados no seu cadastro de afiliado.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
