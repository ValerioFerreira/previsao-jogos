"use client";
import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Copy, TrendingUp, Users, ShoppingCart, DollarSign } from "lucide-react";
import { useAuth } from "@/lib/AuthContext";
import { affiliatesApi, type AffiliatePortalStats } from "@/lib/affiliatesApi";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export default function AfiliadoPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [stats, setStats] = useState<AffiliatePortalStats | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!loading && !user) router.replace("/entrar");
  }, [loading, user, router]);

  useEffect(() => {
    if (!user) return;
    affiliatesApi.me().then(setStats).catch((e) => setErr((e as Error).message));
  }, [user]);

  if (loading || !user) {
    return <div className="flex justify-center py-20"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>;
  }

  if (err) {
    return <div className="max-w-2xl mx-auto text-sm rounded-md bg-red-500/10 text-red-600 p-4">{err}</div>;
  }

  if (!stats) {
    return <div className="flex justify-center py-20"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>;
  }

  function copyLink() {
    navigator.clipboard.writeText(stats!.link).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold">Portal do Afiliado</h1>

      <Card>
        <CardHeader><CardTitle className="text-lg">Seu link exclusivo</CardTitle></CardHeader>
        <CardContent className="flex items-center gap-2">
          <code className="flex-1 text-sm bg-muted rounded-md px-3 py-2 overflow-x-auto">{stats.link}</code>
          <Button size="sm" variant="outline" onClick={copyLink}>
            <Copy className="w-3.5 h-3.5 mr-1" /> {copied ? "Copiado!" : "Copiar"}
          </Button>
        </CardContent>
      </Card>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Card>
          <CardContent className="pt-6 text-center">
            <TrendingUp className="w-5 h-5 mx-auto text-muted-foreground mb-1" />
            <div className="text-2xl font-bold">{stats.clicks}</div>
            <div className="text-xs text-muted-foreground">Cliques</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6 text-center">
            <Users className="w-5 h-5 mx-auto text-muted-foreground mb-1" />
            <div className="text-2xl font-bold">{stats.signups}</div>
            <div className="text-xs text-muted-foreground">Cadastros</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6 text-center">
            <ShoppingCart className="w-5 h-5 mx-auto text-muted-foreground mb-1" />
            <div className="text-2xl font-bold">{stats.buyers}</div>
            <div className="text-xs text-muted-foreground">Compradores</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6 text-center">
            <DollarSign className="w-5 h-5 mx-auto text-muted-foreground mb-1" />
            <div className="text-2xl font-bold">R$ {Number(stats.revenue_brl).toFixed(0)}</div>
            <div className="text-xs text-muted-foreground">Faturamento gerado</div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Card>
          <CardContent className="pt-6">
            <div className="text-sm text-muted-foreground">Comissão devida</div>
            <div className="text-2xl font-bold text-amber-500">R$ {Number(stats.commission_due_brl).toFixed(2)}</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-sm text-muted-foreground">Comissão já paga</div>
            <div className="text-2xl font-bold text-emerald-600">R$ {Number(stats.commission_paid_brl).toFixed(2)}</div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
