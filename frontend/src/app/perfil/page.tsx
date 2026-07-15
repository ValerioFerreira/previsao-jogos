"use client";
import React, { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Loader2, User as UserIcon, FileText, Ticket, BarChart3 } from "lucide-react";
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
const BET_STATUS_STYLE: Record<string, string> = {
  awaiting_start: "bg-sky-500/10 text-sky-600",
  in_progress: "bg-cyan-500/10 text-cyan-600",
  awaiting_settlement: "bg-amber-500/10 text-amber-600",
  won: "bg-emerald-500/10 text-emerald-600",
  credit_refunded: "bg-emerald-500/10 text-emerald-600",
  lost: "bg-red-500/10 text-red-600",
  credit_consumed: "bg-muted text-muted-foreground",
  canceled: "bg-muted text-muted-foreground",
};
const ANALYSIS_STATUS: Record<string, string> = { generated: "Gerada", consumed: "Consumida", reserved: "Reservada" };

function fmt(d: string) { return new Date(d).toLocaleString("pt-BR"); }

export default function PerfilPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [analyses, setAnalyses] = useState<AnalysisSummary[]>([]);
  const [bets, setBets] = useState<BetResponse[]>([]);
  const [pending, setPending] = useState<LegalDoc[]>([]);

  useEffect(() => { if (!loading && !user) router.replace("/entrar"); }, [loading, user, router]);

  const load = useCallback(async () => {
    const [a, b, p] = await Promise.all([
      analysisApi.list(50).catch(() => ({ items: [] })),
      betsApi.list(50).catch(() => ({ items: [] })),
      legalApi.pending().catch(() => []),
    ]);
    setAnalyses((a as { items: AnalysisSummary[] }).items);
    setBets((b as { items: BetResponse[] }).items);
    setPending(p as LegalDoc[]);
  }, []);

  useEffect(() => { if (user) load(); }, [user, load]);

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
            <CardHeader><CardTitle className="text-lg">Apostas promocionais (ParcerIA)</CardTitle></CardHeader>
            <CardContent className="px-0 sm:px-6">
              {bets.length === 0 ? (
                <p className="text-sm text-muted-foreground px-6 sm:px-0">Nenhuma aposta ainda.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm border-collapse">
                    <thead>
                      <tr className="text-left text-xs text-muted-foreground border-b border-border/50">
                        <th className="py-2 px-3 font-medium">Partida</th>
                        <th className="py-2 px-3 font-medium">Seleções</th>
                        <th className="py-2 px-3 font-medium text-center">Odd</th>
                        <th className="py-2 px-3 font-medium">Data</th>
                        <th className="py-2 px-3 font-medium text-right">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {bets.map((b) => (
                        <tr key={b.id} className="border-b border-border/30 last:border-0 hover:bg-muted/30 transition-colors">
                          <td className="py-3 px-3 font-medium whitespace-nowrap">
                            {b.home_team && b.away_team
                              ? `${teamPt(b.home_team)} × ${teamPt(b.away_team)}`
                              : `Aposta #${b.id.slice(0, 8)}`}
                          </td>
                          <td className="py-3 px-3 text-xs text-muted-foreground">
                            {b.selections.map((s) => s.label).join(" + ")}
                          </td>
                          <td className="py-3 px-3 text-center font-mono">{Number(b.combined_odd).toFixed(2)}</td>
                          <td className="py-3 px-3 text-xs text-muted-foreground whitespace-nowrap">{fmt(b.created_at)}</td>
                          <td className="py-3 px-3 text-right">
                            <span className={`text-xs px-2 py-1 rounded whitespace-nowrap ${BET_STATUS_STYLE[b.status] || "bg-muted text-muted-foreground"}`}>
                              {BET_STATUS[b.status] || b.status}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="docs">
          <Card>
            <CardHeader><CardTitle className="text-lg">Documentos e termos</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              {pending.length > 0 && (
                <div className="text-sm rounded-md bg-amber-500/10 text-amber-600 p-3">
                  Você tem {pending.length} documento(s) pendente(s) de aceite.
                </div>
              )}
              <p className="text-sm text-muted-foreground">
                Consulte e assine os Termos de Uso, Política de Privacidade, Consentimento LGPD, Política de Créditos e o Regulamento da Promoção ParcerIA.
              </p>
              <Link href="/documentos"><Button size="sm">Ver documentos e termos</Button></Link>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
