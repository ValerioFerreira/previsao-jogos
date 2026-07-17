"use client";
import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, Loader2, Copy, TrendingUp, Users, ShoppingCart, DollarSign } from "lucide-react";
import { useAuth } from "@/lib/AuthContext";
import { affiliatesApi, type AffiliatePortalStats, type TimeseriesResponse } from "@/lib/affiliatesApi";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

function TimeseriesChart({ ts }: { ts: TimeseriesResponse }) {
  if (ts.items.length === 0) {
    return <p className="text-sm text-muted-foreground">Sem dados no período.</p>;
  }
  const max = Math.max(1, ...ts.items.map((p) => p.clicks));
  return (
    <div className="space-y-2">
      <div className="flex items-end gap-1 h-28">
        {ts.items.map((p) => (
          <div key={p.bucket} className="flex-1 flex flex-col items-center justify-end gap-1 group relative">
            <div
              className="w-full rounded-t bg-primary/70 group-hover:bg-primary transition-colors"
              style={{ height: `${Math.max(4, (p.clicks / max) * 100)}%` }}
              title={`${p.bucket}: ${p.clicks} cliques, ${p.conversions} conversões, R$ ${Number(p.revenue_brl).toFixed(2)}`}
            />
          </div>
        ))}
      </div>
      <div className="flex justify-between text-[10px] text-muted-foreground">
        <span>{ts.items[0].bucket}</span>
        <span>{ts.items[ts.items.length - 1].bucket}</span>
      </div>
    </div>
  );
}

export default function ParceiroDashboardPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [stats, setStats] = useState<AffiliatePortalStats | null>(null);
  const [ts, setTs] = useState<TimeseriesResponse | null>(null);
  const [granularity, setGranularity] = useState<"day" | "month">("day");
  const [err, setErr] = useState<string | null>(null);
  const [copied, setCopied] = useState<"link" | "code" | null>(null);

  useEffect(() => {
    if (!loading && !user) router.replace("/entrar");
  }, [loading, user, router]);

  useEffect(() => {
    if (!user) return;
    affiliatesApi.me().then(setStats).catch((e) => setErr((e as Error).message));
  }, [user]);

  useEffect(() => {
    if (!user) return;
    affiliatesApi.portalTimeseries(granularity).then(setTs).catch(() => setTs(null));
  }, [user, granularity]);

  function copy(value: string, which: "link" | "code") {
    navigator.clipboard.writeText(value).then(() => {
      setCopied(which);
      setTimeout(() => setCopied(null), 2000);
    });
  }

  if (loading || (user && !stats && !err)) {
    return <div className="flex justify-center py-20"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>;
  }

  if (err) {
    return (
      <div className="max-w-2xl mx-auto text-sm rounded-md bg-red-500/10 text-red-600 p-4">
        {err.includes("parceiro") ? "Sua conta não é uma conta de parceiro." : err}
      </div>
    );
  }

  if (!stats) return null;

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <Link href="/parceiro" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="w-3.5 h-3.5" /> Voltar
        </Link>
        <h1 className="text-2xl font-bold mt-1">Dashboard do Parceiro</h1>
      </div>

      <div className="grid sm:grid-cols-2 gap-4">
        <Card>
          <CardHeader><CardTitle className="text-lg">Seu link exclusivo</CardTitle></CardHeader>
          <CardContent className="flex items-center gap-2">
            <code className="flex-1 text-sm bg-muted rounded-md px-3 py-2 overflow-x-auto">{stats.link}</code>
            <Button size="sm" variant="outline" onClick={() => copy(stats.link, "link")}>
              <Copy className="w-3.5 h-3.5 mr-1" /> {copied === "link" ? "Copiado!" : "Copiar"}
            </Button>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-lg">Seu código de desconto</CardTitle></CardHeader>
          <CardContent className="flex items-center gap-2">
            <code className="flex-1 text-sm bg-muted rounded-md px-3 py-2 overflow-x-auto uppercase">{stats.code}</code>
            <Button size="sm" variant="outline" onClick={() => copy(stats.code, "code")}>
              <Copy className="w-3.5 h-3.5 mr-1" /> {copied === "code" ? "Copiado!" : "Copiar"}
            </Button>
          </CardContent>
        </Card>
      </div>

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
            <div className="text-sm text-muted-foreground">Comissão devida (a receber no fim do mês)</div>
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

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-lg">Uso ao longo do tempo</CardTitle>
          <div className="flex gap-1">
            <Button size="sm" variant={granularity === "day" ? "default" : "outline"} onClick={() => setGranularity("day")}>Dia</Button>
            <Button size="sm" variant={granularity === "month" ? "default" : "outline"} onClick={() => setGranularity("month")}>Mês</Button>
          </div>
        </CardHeader>
        <CardContent>
          {ts ? <TimeseriesChart ts={ts} /> : <div className="flex justify-center py-8"><Loader2 className="w-5 h-5 animate-spin text-muted-foreground" /></div>}
        </CardContent>
      </Card>
    </div>
  );
}
