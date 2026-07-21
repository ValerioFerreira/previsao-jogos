"use client";
import React, { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Loader2, User as UserIcon, FileText, Ticket, BarChart3, ChevronDown, CheckCircle2, AlertTriangle } from "lucide-react";
import { useAuth } from "@/lib/AuthContext";
import { analysisApi, betsApi, legalApi, type AnalysisSummary, type BetResponse, type LegalDoc } from "@/lib/monetizationApi";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import InfoTooltip from "@/components/platform/InfoTooltip";
import { teamPt } from "@/lib/teamNames";

const BET_STATUS: Record<string, string> = {
  awaiting_start: "Aguardando início", in_progress: "Em andamento", awaiting_settlement: "Processando resultado",
  won: "Validada", lost: "Não validada", credit_consumed: "Crédito consumido", credit_refunded: "Crédito estornado", canceled: "Cancelada",
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

function formatCPF(cpf?: string): string {
  if (!cpf) return "";
  const clean = cpf.replace(/\D/g, "");
  if (clean.length !== 11) return cpf;
  return `${clean.slice(0, 3)}.${clean.slice(3, 6)}.${clean.slice(6, 9)}-${clean.slice(9)}`;
}

function formatPhone(phone?: string): string {
  if (!phone) return "";
  const clean = phone.replace(/\D/g, "");
  if (clean.length === 11) {
    return `(${clean.slice(0, 2)}) ${clean.slice(2, 7)}-${clean.slice(7)}`;
  } else if (clean.length === 10) {
    return `(${clean.slice(0, 2)}) ${clean.slice(2, 6)}-${clean.slice(6)}`;
  }
  return phone;
}

function formatMatchDate(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "—";
  const p = (n: number) => String(n).padStart(2, '0');
  return `${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()}`;
}

function renderBody(body_md: string) {
  return body_md.split("\n").map((line, i) => {
    if (line.startsWith("## ")) return <h2 key={i} className="text-base font-semibold mt-3 mb-1.5">{line.slice(3)}</h2>;
    if (line.startsWith("# ")) return <h1 key={i} className="text-lg font-bold mt-2 mb-2">{line.slice(2)}</h1>;
    if (!line.trim()) return <div key={i} className="h-2" />;
    return <p key={i} className="text-sm text-muted-foreground leading-relaxed">{line}</p>;
  });
}

export default function PerfilPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [analyses, setAnalyses] = useState<AnalysisSummary[]>([]);
  const [bets, setBets] = useState<BetResponse[]>([]);
  const [pending, setPending] = useState<LegalDoc[]>([]);
  const [docs, setDocs] = useState<LegalDoc[]>([]);
  const [activeTab, setActiveTab] = useState("dados");
  const [analysisFilter, setAnalysisFilter] = useState("all");
  const [betFilter, setBetFilter] = useState("all");

  const [openType, setOpenType] = useState<string | null>(null);
  const [bodies, setBodies] = useState<Record<string, { id: string; title: string; version: number; body_md: string }>>({});
  const [loadingBody, setLoadingBody] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => { if (!loading && !user) router.replace("/entrar"); }, [loading, user, router]);

  const load = useCallback(async () => {
    const [a, b, p, d] = await Promise.all([
      analysisApi.list(50).catch(() => ({ items: [] })),
      betsApi.list(50).catch(() => ({ items: [] })),
      legalApi.pending().catch(() => []),
      legalApi.documents().catch(() => []),
    ]);
    setAnalyses((a as { items: AnalysisSummary[] }).items);
    setBets((b as { items: BetResponse[] }).items);
    setPending(p as LegalDoc[]);
    setDocs(d as LegalDoc[]);
  }, []);

  useEffect(() => { if (user) load(); }, [user, load]);

  useEffect(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      const tabParam = params.get("tab");
      if (tabParam === "selecoes" || tabParam === "apostas") {
        setActiveTab("apostas");
      } else if (tabParam === "analises") {
        setActiveTab("analises");
      } else if (tabParam === "docs") {
        setActiveTab("docs");
      }
    }
  }, []);

  async function toggleDoc(type: string) {
    if (openType === type) {
      setOpenType(null);
      return;
    }
    setOpenType(type);
    if (!bodies[type]) {
      setLoadingBody(type);
      try {
        const doc = await legalApi.document(type);
        setBodies((prev) => ({ ...prev, [type]: doc }));
      } finally {
        setLoadingBody(null);
      }
    }
  }

  async function acceptDoc(id: string) {
    setBusyId(id);
    try {
      await legalApi.accept([id]);
      await load();
    } finally {
      setBusyId(null);
    }
  }

  const filteredAnalyses = React.useMemo(() => {
    if (analysisFilter === "all") return analyses;
    return analyses.filter((a) => a.status === analysisFilter);
  }, [analyses, analysisFilter]);

  const filteredBets = React.useMemo(() => {
    if (betFilter === "all") return bets;
    return bets.filter((b) => b.status === betFilter);
  }, [bets, betFilter]);

  if (loading || !user) return <div className="flex justify-center py-20"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>;

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold flex items-center gap-2"><UserIcon className="w-6 h-6" /> Meu perfil</h1>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="grid grid-cols-4 w-full">
          <TabsTrigger value="dados">Dados</TabsTrigger>
          <TabsTrigger value="analises"><BarChart3 className="w-4 h-4 mr-1" />Análises</TabsTrigger>
          <TabsTrigger value="apostas"><Ticket className="w-4 h-4 mr-1" />Seleções</TabsTrigger>
          <TabsTrigger value="docs"><FileText className="w-4 h-4 mr-1" />Documentos</TabsTrigger>
        </TabsList>

        <TabsContent value="dados">
          <Card>
            <CardHeader><CardTitle className="text-lg">Dados pessoais</CardTitle></CardHeader>
            <CardContent className="space-y-2 text-sm">
              {[
                ["Nome", user.full_name],
                ["E-mail", user.email],
                ["CPF", formatCPF(user.cpf)],
                ["Telefone", formatPhone(user.phone)]
              ].map(([k, v]) => (
                <div key={k} className="flex justify-between border-b border-border/30 py-2">
                  <span className="text-muted-foreground">{k}</span>
                  <span className="font-medium">{v}</span>
                </div>
              ))}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="analises">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
              <CardTitle className="text-lg">Histórico de análises</CardTitle>
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground flex items-center gap-1">
                  Filtrar situação:
                  <InfoTooltip text="Gerada: Análise processada com sucesso. Consumida: Crédito permanentemente debitado após a conclusão. Reservada: Crédito temporariamente retido aguardando o confronto." />
                </span>
                <Select value={analysisFilter} onValueChange={setAnalysisFilter}>
                  <SelectTrigger className="w-32 h-8 text-xs">
                    <SelectValue placeholder="Situação" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todas</SelectItem>
                    <SelectItem value="generated">Geradas</SelectItem>
                    <SelectItem value="consumed">Consumidas</SelectItem>
                    <SelectItem value="reserved">Reservadas</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </CardHeader>
            <CardContent>
              {filteredAnalyses.length === 0 ? (
                <p className="text-sm text-muted-foreground">Nenhuma análise encontrada.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm border-collapse">
                    <thead>
                      <tr className="text-left text-xs text-muted-foreground border-b border-border/50">
                        <th className="py-2 px-3 font-semibold">Partida</th>
                        <th className="py-2 px-3 font-semibold">Competição</th>
                        <th className="py-2 px-3 font-semibold">Tipo</th>
                        <th className="py-2 px-3 font-semibold">Criada em</th>
                        <th className="py-2 px-3 font-semibold text-right">Situação</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredAnalyses.map((a) => (
                        <tr key={a.id} className="border-b border-border/30 last:border-0 hover:bg-muted/30 transition-colors">
                          <td className="py-3 px-3 font-medium whitespace-nowrap">
                            {teamPt(a.home_team)} × {teamPt(a.away_team)}
                          </td>
                          <td className="py-3 px-3 text-xs text-muted-foreground whitespace-nowrap">
                            {a.tournament}
                          </td>
                          <td className="py-3 px-3 text-xs text-muted-foreground whitespace-nowrap">
                            {a.type === "future_match" ? "Partida futura" : "Independente"}
                          </td>
                          <td className="py-3 px-3 text-xs text-muted-foreground whitespace-nowrap">
                            {fmt(a.created_at)}
                          </td>
                          <td className="py-3 px-3 text-right">
                            <span className="text-xs px-2 py-1 rounded bg-muted whitespace-nowrap">
                              {ANALYSIS_STATUS[a.status] || a.status}
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

        <TabsContent value="apostas">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
              <CardTitle className="text-lg">Seleções promocionais (ParcerIA)</CardTitle>
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">Filtrar status:</span>
                <Select value={betFilter} onValueChange={setBetFilter}>
                  <SelectTrigger className="w-40 h-8 text-xs">
                    <SelectValue placeholder="Status" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todos</SelectItem>
                    <SelectItem value="awaiting_start">Aguardando início</SelectItem>
                    <SelectItem value="in_progress">Em andamento</SelectItem>
                    <SelectItem value="awaiting_settlement">Processando resultado</SelectItem>
                    <SelectItem value="won">Validadas</SelectItem>
                    <SelectItem value="lost">Não validadas</SelectItem>
                    <SelectItem value="credit_consumed">Crédito consumido</SelectItem>
                    <SelectItem value="credit_refunded">Crédito estornado</SelectItem>
                    <SelectItem value="canceled">Canceladas</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </CardHeader>
            <CardContent className="px-0 sm:px-6">
              {filteredBets.length === 0 ? (
                <p className="text-sm text-muted-foreground px-6 sm:px-0">Nenhuma seleção encontrada.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm border-collapse">
                    <thead>
                      <tr className="text-left text-xs text-muted-foreground border-b border-border/50">
                        <th className="py-2 px-3 font-medium">Partida</th>
                        <th className="py-2 px-3 font-medium">Seleções</th>
                        <th className="py-2 px-3 font-medium text-center">Odd</th>
                        <th className="py-2 px-3 font-medium">Data de Criação</th>
                        <th className="py-2 px-3 font-medium text-right">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredBets.map((b) => (
                        <tr key={b.id} className="border-b border-border/30 last:border-0 hover:bg-muted/30 transition-colors">
                          <td className="py-3 px-3 font-medium whitespace-nowrap">
                            <div>
                              {b.home_team && b.away_team
                                ? `${teamPt(b.home_team)} × ${teamPt(b.away_team)}`
                                : `Seleção #${b.id.slice(0, 8)}`}
                            </div>
                            <div className="text-[11px] text-muted-foreground mt-0.5 font-normal">
                              Jogo: {formatMatchDate(b.match_datetime)}
                            </div>
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
            <CardHeader><CardTitle className="text-lg">Documentos e termos vigentes</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              {pending.length > 0 && (
                <div className="text-sm rounded-md bg-amber-500/10 text-amber-600 p-3 flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 shrink-0" />
                  <span>Você tem {pending.length} documento(s) pendente(s) de aceite. É necessário aceitar todos antes de realizar compras de créditos.</span>
                </div>
              )}

              <div className="space-y-2">
                {docs.length === 0 ? (
                  <div className="flex justify-center py-8"><Loader2 className="w-5 h-5 animate-spin text-muted-foreground" /></div>
                ) : (
                  docs.map((d) => {
                    const isPending = pending.some((p) => p.id === d.id);
                    const isOpen = openType === d.type;
                    const body = bodies[d.type];
                    return (
                      <div key={d.id} className="border-b border-border/30 last:border-b-0">
                        <div className="w-full flex items-center justify-between gap-3 py-3 text-sm">
                          <button
                            onClick={() => toggleDoc(d.type)}
                            className="flex items-center gap-2 min-w-0 text-left hover:text-primary transition-colors font-medium"
                          >
                            <ChevronDown className={`w-4 h-4 shrink-0 transition-transform text-muted-foreground ${isOpen ? "rotate-180 text-foreground" : ""}`} />
                            <span className="truncate">{d.title}</span>
                            <span className="text-[10px] text-muted-foreground shrink-0 bg-muted px-1.5 py-0.5 rounded">v{d.version}</span>
                          </button>
                          <div className="shrink-0">
                            {isPending ? (
                              <Button size="sm" variant="outline" className="h-7 text-xs border-amber-500/50 hover:bg-amber-500/10 text-amber-500" disabled={busyId === d.id} onClick={() => acceptDoc(d.id)}>
                                {busyId === d.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : "Assinar"}
                              </Button>
                            ) : (
                              <span className="text-xs text-emerald-500 bg-emerald-500/10 px-2 py-0.5 rounded font-medium flex items-center gap-1"><CheckCircle2 className="w-3.5 h-3.5" /> Aceito</span>
                            )}
                          </div>
                        </div>
                        {isOpen && (
                          <div className="pb-4 pl-6 pr-2 border-t border-border/10 mt-1 pt-3">
                            {loadingBody === d.type ? (
                              <div className="flex justify-center py-6"><Loader2 className="w-4 h-4 animate-spin text-muted-foreground" /></div>
                            ) : body ? (
                              <div className="prose prose-sm dark:prose-invert max-w-none bg-muted/30 p-4 rounded-lg border border-border/40">
                                {renderBody(body.body_md)}
                                <div className="not-prose border-t border-border/50 mt-4 pt-3 flex items-center justify-between gap-3 flex-wrap">
                                  {isPending ? (
                                    <>
                                      <p className="text-xs text-muted-foreground">Ao clicar em "Assinar", você confirma que leu e concorda com este documento.</p>
                                      <Button size="sm" disabled={busyId === d.id} onClick={() => acceptDoc(d.id)}>
                                        {busyId === d.id ? <Loader2 className="w-4 h-4 animate-spin" /> : "Assinar"}
                                      </Button>
                                    </>
                                  ) : (
                                    <span className="text-xs text-emerald-500 flex items-center gap-1.5 font-medium"><CheckCircle2 className="w-4 h-4" /> Você já aceitou esta versão do documento.</span>
                                  )}
                                </div>
                              </div>
                            ) : null}
                          </div>
                        )}
                      </div>
                    );
                  })
                )}
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
