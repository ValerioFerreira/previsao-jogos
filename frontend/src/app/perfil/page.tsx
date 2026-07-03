"use client";
import React, { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Loader2, User as UserIcon, FileText, Ticket, BarChart3, CheckCircle2 } from "lucide-react";
import { useAuth } from "@/lib/AuthContext";
import { analysisApi, betsApi, legalApi, type AnalysisSummary, type BetResponse, type LegalDoc } from "@/lib/monetizationApi";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { teamPt } from "@/lib/teamNames";

const BET_STATUS: Record<string, string> = {
  awaiting_start: "Aguardando início", in_progress: "Em andamento", awaiting_settlement: "Aguardando liquidação",
  won: "Vencedora", lost: "Não vencedora", credit_consumed: "Crédito consumido", credit_refunded: "Crédito estornado", canceled: "Cancelada",
};
const ANALYSIS_STATUS: Record<string, string> = { generated: "Gerada", consumed: "Consumida", reserved: "Reservada" };

function fmt(d: string) { return new Date(d).toLocaleString("pt-BR"); }

export default function PerfilPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [analyses, setAnalyses] = useState<AnalysisSummary[]>([]);
  const [bets, setBets] = useState<BetResponse[]>([]);
  const [docs, setDocs] = useState<LegalDoc[]>([]);
  const [pending, setPending] = useState<LegalDoc[]>([]);

  useEffect(() => { if (!loading && !user) router.replace("/entrar"); }, [loading, user, router]);

  const load = useCallback(async () => {
    const [a, b, d, p] = await Promise.all([
      analysisApi.list(50).catch(() => ({ items: [] })),
      betsApi.list(50).catch(() => ({ items: [] })),
      legalApi.documents().catch(() => []),
      legalApi.pending().catch(() => []),
    ]);
    setAnalyses((a as { items: AnalysisSummary[] }).items);
    setBets((b as { items: BetResponse[] }).items);
    setDocs(d as LegalDoc[]);
    setPending(p as LegalDoc[]);
  }, []);

  useEffect(() => { if (user) load(); }, [user, load]);

  async function accept(id: string) {
    await legalApi.accept([id]);
    await load();
  }

  if (loading || !user) return <div className="flex justify-center py-20"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>;

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold flex items-center gap-2"><UserIcon className="w-6 h-6" /> Meu perfil</h1>

      <Tabs defaultValue="dados">
        <TabsList className="grid grid-cols-4 w-full">
          <TabsTrigger value="dados">Dados</TabsTrigger>
          <TabsTrigger value="analises"><BarChart3 className="w-4 h-4 mr-1" />Análises</TabsTrigger>
          <TabsTrigger value="apostas"><Ticket className="w-4 h-4 mr-1" />Apostas</TabsTrigger>
          <TabsTrigger value="docs"><FileText className="w-4 h-4 mr-1" />Documentos</TabsTrigger>
        </TabsList>

        <TabsContent value="dados">
          <Card>
            <CardHeader><CardTitle className="text-lg">Dados pessoais</CardTitle></CardHeader>
            <CardContent className="space-y-2 text-sm">
              {[["Nome", user.full_name], ["E-mail", user.email], ["CPF", user.cpf], ["Telefone", user.phone]].map(([k, v]) => (
                <div key={k} className="flex justify-between border-b border-border/30 py-2">
                  <span className="text-muted-foreground">{k}</span><span className="font-medium">{v}</span>
                </div>
              ))}
              <div className="pt-3 flex gap-2">
                <Link href="/carteira"><Button variant="outline" size="sm">Carteira</Button></Link>
                {(user.role === "admin" || user.role === "superadmin") && <Link href="/admin"><Button size="sm">Painel admin</Button></Link>}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="analises">
          <Card>
            <CardHeader><CardTitle className="text-lg">Histórico de análises</CardTitle></CardHeader>
            <CardContent>
              {analyses.length === 0 ? <p className="text-sm text-muted-foreground">Nenhuma análise ainda.</p> : (
                <div className="divide-y">
                  {analyses.map((a) => (
                    <div key={a.id} className="flex items-center justify-between py-2.5 text-sm">
                      <div>
                        <div className="font-medium">{teamPt(a.home_team)} × {teamPt(a.away_team)}</div>
                        <div className="text-xs text-muted-foreground">{a.tournament} · {a.type === "future_match" ? "Partida futura" : "Independente"} · {fmt(a.created_at)}</div>
                      </div>
                      <span className="text-xs px-2 py-1 rounded bg-muted">{ANALYSIS_STATUS[a.status] || a.status}</span>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="apostas">
          <Card>
            <CardHeader><CardTitle className="text-lg">Apostas promocionais</CardTitle></CardHeader>
            <CardContent>
              {bets.length === 0 ? <p className="text-sm text-muted-foreground">Nenhuma aposta ainda.</p> : (
                <div className="divide-y">
                  {bets.map((b) => (
                    <div key={b.id} className="py-3 text-sm">
                      <div className="flex items-center justify-between">
                        <span className="font-medium">Aposta #{b.id.slice(0, 8)}</span>
                        <span className="text-xs px-2 py-1 rounded bg-muted">{BET_STATUS[b.status] || b.status}</span>
                      </div>
                      <div className="text-xs text-muted-foreground mt-1">
                        {b.selections.map((s) => s.label).join(" + ")} · odd {Number(b.combined_odd).toFixed(2)} · {fmt(b.created_at)}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="docs">
          <Card>
            <CardHeader><CardTitle className="text-lg">Documentos e termos</CardTitle></CardHeader>
            <CardContent className="space-y-2">
              {pending.length > 0 && (
                <div className="mb-3 text-sm rounded-md bg-amber-500/10 text-amber-600 p-3">
                  Você tem {pending.length} documento(s) pendente(s) de aceite.
                </div>
              )}
              {docs.map((d) => {
                const isPending = pending.some((p) => p.id === d.id);
                return (
                  <div key={d.id} className="flex items-center justify-between border-b border-border/30 py-2.5 text-sm">
                    <Link href={`/documentos/${d.type}`} className="hover:underline">{d.title} <span className="text-xs text-muted-foreground">v{d.version}</span></Link>
                    {isPending
                      ? <Button size="sm" onClick={() => accept(d.id)}>Aceitar</Button>
                      : <span className="text-xs text-emerald-600 flex items-center gap-1"><CheckCircle2 className="w-3.5 h-3.5" /> Aceito</span>}
                  </div>
                );
              })}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
