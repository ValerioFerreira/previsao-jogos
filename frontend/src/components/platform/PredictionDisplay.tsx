"use client";
import React from "react";
import { motion } from "framer-motion";
import { AlertTriangle, CheckCircle2, ShieldAlert, ShieldCheck, Target } from "lucide-react";
import { PredictionResponse, PlacarMotivo, teamLogoUrl } from "@/lib/api";
import InfoTooltip from "@/components/platform/InfoTooltip";
import { MarketCard } from "@/components/platform/MarketCard";
import DerivedMarketsBlock from "@/components/platform/DerivedMarkets";
import { teamPt } from "@/lib/teamNames";

function formatDateBR(s: string): string {
  const d = (s || "").slice(0, 10).split("-");
  return d.length === 3 ? `${d[2]}/${d[1]}/${d[0]}` : s;
}
function oddRangeStr(probPct: number): string {
  if (!probPct || probPct <= 0) return "—";
  const odd = 100 / probPct;
  if (odd > 50) return "50+";
  const hi = Math.max(1, odd);
  const lo = Math.max(1, odd * 0.93);
  return lo.toFixed(2) === hi.toFixed(2) ? hi.toFixed(2) : `${lo.toFixed(2)}–${hi.toFixed(2)}`;
}
function goalPeriods(p: PredictionResponse, side: string) {
  return {
    "Partida inteira": side === "total" ? (p.gols as any) : p.gols_equipe?.[side],
    "1º tempo": p.tempos?.gols_1t?.[side],
    "2º tempo": p.tempos?.gols_2t?.[side],
  };
}
function cardPeriods(p: PredictionResponse, side: string) {
  return {
    "Partida inteira": p.cartoes?.[side],
    "1º tempo": p.tempos?.cartoes_1t?.[side],
    "2º tempo": p.tempos?.cartoes_2t?.[side],
  };
}

function PlacarExatoCard({ data, home, away, teamIds }: { data: NonNullable<PredictionResponse["placar_exato"]>; home: string; away: string; teamIds: Record<string, number> }) {
  const alerta = data.alerta;
  const isAlert = alerta.nivel !== "normal";
  const alertStyles =
    alerta.nivel === "alto" ? "bg-amber-500/10 border-amber-500/30"
    : alerta.nivel === "moderado" ? "bg-amber-500/5 border-amber-500/20"
    : "bg-muted/50 border-border/50";
  const motivoTexto = (m: PlacarMotivo): string => {
    if (m.tipo === "favoritismo") {
      const fav = m.favorito_lado === "mandante" ? teamPt(home) : teamPt(away);
      return `${fav} é forte favorito: ${m.exp_alto} × ${m.exp_baixo} gols projetados (Elo, forma e ataque/defesa embutidos).`;
    }
    return `Placar alto projetado: ${m.exp_total} gols esperados, P(4+ gols) = ${m.prob_4_mais}%.`;
  };
  return (
    <div className="bg-card border border-border/50 rounded-xl p-5">
      <h4 className="text-sm font-semibold mb-1 flex items-center gap-1.5">
        <Target className="w-4 h-4 text-purple-500" /> Placar Exato
        <InfoTooltip text="Os 3 placares mais prováveis segundo a matriz conjunta de gols (Dixon-Coles)." />
      </h4>
      <div className="flex items-center justify-center gap-2 mb-3">
        {teamLogoUrl(teamIds[home]) && (
          <img src={teamLogoUrl(teamIds[home])!} alt="" className="w-5 h-5 object-contain" loading="lazy" onError={(e) => { e.currentTarget.style.display = "none"; }} />
        )}
        <p className="text-[10px] text-muted-foreground">{teamPt(home)}</p>
        <span className="text-[10px] text-muted-foreground">×</span>
        <p className="text-[10px] text-muted-foreground">{teamPt(away)}</p>
        {teamLogoUrl(teamIds[away]) && (
          <img src={teamLogoUrl(teamIds[away])!} alt="" className="w-5 h-5 object-contain" loading="lazy" onError={(e) => { e.currentTarget.style.display = "none"; }} />
        )}
      </div>
      <div className="grid grid-cols-3 gap-2 mb-4">
        {data.top.map((s, i) => (
          <div key={i} className={`text-center rounded-lg p-2 border ${i === 0 ? "bg-purple-500/10 border-purple-500/30" : "bg-muted/30 border-border/30"}`}>
            <p className="text-xl font-mono font-bold text-foreground">{s.mandante}<span className="text-muted-foreground mx-0.5">–</span>{s.visitante}</p>
            <p className="text-[11px] font-mono text-cyan-400 mt-0.5">{s.prob.toFixed(1)}%</p>
            <p className="text-[9px] text-muted-foreground mt-0.5">odd {oddRangeStr(s.prob)}</p>
          </div>
        ))}
      </div>
      <div className={`rounded-lg p-3 border ${alertStyles}`}>
        <p className="text-xs font-medium mb-1.5 flex items-center gap-1.5">
          <AlertTriangle className={`w-3.5 h-3.5 ${isAlert ? "text-amber-400" : "text-muted-foreground"}`} />
          {isAlert ? `Alerta de desvio: potencial ${alerta.nivel}` : "Padrão de placar normal"}
        </p>
        {isAlert ? (
          <ul className="space-y-1">
            {alerta.motivos.map((m, i) => (
              <li key={i} className="text-xs text-amber-500/80 flex items-start gap-1.5">
                <span className="mt-1.5 w-1 h-1 rounded-full bg-amber-400 shrink-0" /><span>{motivoTexto(m)}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-muted-foreground italic">
            Gols esperados equilibrados ({alerta.exp_mandante} x {alerta.exp_visitante}); sem indícios de placar fora do padrão.
          </p>
        )}
      </div>
    </div>
  );
}

function MatchReliabilityBadge({ confiabilidade }: { confiabilidade: PredictionResponse["confiabilidade"] }) {
  if (!confiabilidade) return null;
  const tier = confiabilidade.tier;
  const styles =
    tier === "Alta" ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-500"
    : tier === "Média" ? "bg-amber-500/10 border-amber-500/30 text-amber-500"
    : "bg-red-500/10 border-red-500/30 text-red-500";
  return (
    <div className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-medium border ${styles}`}>
      {tier === "Alta" ? <ShieldCheck className="w-3.5 h-3.5" /> : <ShieldAlert className="w-3.5 h-3.5" />}
      Confiabilidade dos dados: {tier}
      <InfoTooltip text={confiabilidade._resumo} />
    </div>
  );
}

export default function PredictionDisplay({
  projection, home, away, teamIds, h2hData,
}: {
  projection: PredictionResponse;
  home: string;
  away: string;
  teamIds: Record<string, number>;
  h2hData?: any;
}) {
  const hasH2H = h2hData && (h2hData.h2h_played ?? 0) > 0;
  return (
    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
      {projection.confiabilidade && (
        <div className="flex justify-center"><MatchReliabilityBadge confiabilidade={projection.confiabilidade} /></div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4 items-stretch">
        {hasH2H && (
          <div className="lg:col-span-2 bg-card border border-border/50 rounded-xl p-5 shadow-sm text-center flex flex-col justify-center">
            <h3 className="text-sm font-bold uppercase mb-1">Resumo do Confronto Direto</h3>
            <p className="text-[10px] text-muted-foreground mb-4">
              {h2hData.h2h_played} {h2hData.h2h_played === 1 ? "jogo" : "jogos"}
              {h2hData.last_date ? ` · último em ${formatDateBR(h2hData.last_date)}` : ""}
            </p>
            <div className="flex items-start justify-center gap-4 sm:gap-6 mb-5">
              {[{ id: home, w: h2hData.home_wins }, null, { id: away, w: h2hData.away_wins }].map((side) =>
                side === null ? (
                  <div key="draw" className="flex flex-col items-center justify-center pt-7">
                    <span className="text-[10px] uppercase tracking-wide text-muted-foreground">Empates</span>
                    <span className="text-2xl font-mono font-bold text-muted-foreground">{h2hData.draws}</span>
                  </div>
                ) : (
                  <div key={side.id} className="flex flex-col items-center w-24">
                    {teamLogoUrl(teamIds[side.id]) && (
                      <img src={teamLogoUrl(teamIds[side.id])!} alt="" className="w-9 h-9 object-contain mb-1" loading="lazy" onError={(e) => { e.currentTarget.style.display = "none"; }} />
                    )}
                    <span className="text-xs font-semibold leading-tight">{teamPt(side.id)}</span>
                    <span className="text-[10px] uppercase tracking-wide text-muted-foreground mt-1">Vitórias</span>
                    <span className="flex items-center gap-1 text-lg font-mono font-bold"><CheckCircle2 className="w-4 h-4 text-emerald-500" /> {side.w}</span>
                  </div>
                )
              )}
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-wide text-muted-foreground mb-1.5">Médias no confronto direto</p>
              {[["Gols", "goals"], ["Chutes", "shots"], ["Chutes a gol", "shots_on_target"], ["Escanteios", "corners"], ["Cartões", "cards"]].map(([label, key]) => (
                <div key={key} className="grid grid-cols-3 items-center text-xs py-1 border-t border-border/20">
                  <span className="font-mono font-semibold text-emerald-400">{h2hData.home_avgs?.[key] ?? "—"}</span>
                  <span className="text-muted-foreground">{label}</span>
                  <span className="font-mono font-semibold text-cyan-400">{h2hData.away_avgs?.[key] ?? "—"}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className={`${hasH2H ? "lg:col-span-3" : "lg:col-span-5"} space-y-4`}>
          <div className="bg-card border border-border/50 rounded-xl p-6 text-center shadow-sm">
            <p className="text-xs text-muted-foreground mb-4 font-semibold uppercase tracking-wider">RESULTADOS</p>
            <div className="flex flex-wrap items-center justify-center gap-4 sm:gap-8">
              <div className="text-center w-full sm:w-1/4">
                {teamLogoUrl(teamIds[home]) && <img src={teamLogoUrl(teamIds[home])!} alt="" className="w-8 h-8 mx-auto mb-1 object-contain" loading="lazy" onError={(e) => { e.currentTarget.style.display = "none"; }} />}
                <p className="text-sm font-medium text-foreground mb-1 truncate">{teamPt(home)}</p>
                <p className="text-3xl font-bold font-mono text-emerald-400">{projection.vencedor.probabilidades[home]}%</p>
                <p className="text-[10px] text-muted-foreground mt-1">Faixa de odd justa: {oddRangeStr(projection.vencedor.probabilidades[home])}</p>
              </div>
              <div className="text-center w-full sm:w-1/4 border-y sm:border-y-0 sm:border-x border-border/50 py-4 sm:py-0">
                <p className="text-sm font-medium text-muted-foreground mb-1">Empate</p>
                <p className="text-2xl font-bold font-mono text-muted-foreground">{projection.vencedor.probabilidades["Empate"]}%</p>
                <p className="text-[10px] text-muted-foreground mt-1">Faixa de odd justa: {oddRangeStr(projection.vencedor.probabilidades["Empate"])}</p>
              </div>
              <div className="text-center w-full sm:w-1/4">
                {teamLogoUrl(teamIds[away]) && <img src={teamLogoUrl(teamIds[away])!} alt="" className="w-8 h-8 mx-auto mb-1 object-contain" loading="lazy" onError={(e) => { e.currentTarget.style.display = "none"; }} />}
                <p className="text-sm font-medium text-foreground mb-1 truncate">{teamPt(away)}</p>
                <p className="text-3xl font-bold font-mono text-cyan-400">{projection.vencedor.probabilidades[away]}%</p>
                <p className="text-[10px] text-muted-foreground mt-1">Faixa de odd justa: {oddRangeStr(projection.vencedor.probabilidades[away])}</p>
              </div>
            </div>
          </div>

          {projection.ambas_marcam && (
            <div className={projection.placar_exato ? "grid grid-cols-1 md:grid-cols-2 gap-4 items-stretch" : ""}>
              {projection.placar_exato && <PlacarExatoCard data={projection.placar_exato} home={home} away={away} teamIds={teamIds} />}
              <div className="bg-card border border-border/50 rounded-xl p-5 flex flex-col">
                <h4 className="text-sm font-semibold mb-3 flex items-center gap-1.5">Ambas Marcam
                  <InfoTooltip text="Probabilidade de as duas equipes marcarem pelo menos um gol." /></h4>
                <div className="flex-1 flex flex-wrap items-center justify-center gap-8 text-center">
                  <div>
                    <p className="text-[10px] uppercase tracking-wide text-muted-foreground mb-1">Sim</p>
                    <p className="text-2xl font-mono font-bold text-emerald-400">{projection.ambas_marcam.prob_sim}%</p>
                    <p className="text-[10px] text-muted-foreground mt-1">odd justa: {oddRangeStr(projection.ambas_marcam.prob_sim)}</p>
                  </div>
                  <div>
                    <p className="text-[10px] uppercase tracking-wide text-muted-foreground mb-1">Não</p>
                    <p className="text-2xl font-mono font-bold text-blue-400">{(100 - projection.ambas_marcam.prob_sim).toFixed(1)}%</p>
                    <p className="text-[10px] text-muted-foreground mt-1">odd justa: {oddRangeStr(100 - projection.ambas_marcam.prob_sim)}</p>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      <h3 className="text-lg font-heading font-bold mt-8 mb-4 border-b border-border/50 pb-2">MERCADOS</h3>
      <div className="space-y-8">
        {projection.gols && (
          <MarketSection title="Gols" tip="Gols marcados na partida. Cada cartão permite ver partida inteira, 1º ou 2º tempo.">
            <MarketCard title="Gols" subtitle={`Mandante (${teamPt(home)})`} periods={goalPeriods(projection, home)} />
            <MarketCard title="Gols" subtitle="Totais (Partida)" periods={goalPeriods(projection, "total")} />
            <MarketCard title="Gols" subtitle={`Visitante (${teamPt(away)})`} periods={goalPeriods(projection, away)} />
          </MarketSection>
        )}
        {projection.chutes && (
          <MarketSection title="Finalizações" tip="Qualquer tentativa de marcar gol (no alvo, para fora, na trave ou bloqueada).">
            {projection.chutes_equipe?.[home] && <MarketCard title="Finalizações" subtitle={`Mandante (${teamPt(home)})`} prediction={projection.chutes_equipe[home]} />}
            <MarketCard title="Finalizações" subtitle="Totais (Partida)" prediction={projection.chutes as any} />
            {projection.chutes_equipe?.[away] && <MarketCard title="Finalizações" subtitle={`Visitante (${teamPt(away)})`} prediction={projection.chutes_equipe[away]} />}
          </MarketSection>
        )}
        {projection.chutes_a_gol?.total && (
          <MarketSection title="Chutes a Gol" tip="Apenas os chutes na direção da baliza que seriam gol sem intervenção do goleiro.">
            <MarketCard title="Chutes a Gol" subtitle={`Mandante (${teamPt(home)})`} prediction={projection.chutes_a_gol[home]} />
            <MarketCard title="Chutes a Gol" subtitle="Totais (Partida)" prediction={projection.chutes_a_gol.total} />
            <MarketCard title="Chutes a Gol" subtitle={`Visitante (${teamPt(away)})`} prediction={projection.chutes_a_gol[away]} />
          </MarketSection>
        )}
        {projection.escanteios?.total && (
          <MarketSection title="Escanteios" tip="Soma dos tiros de canto efetivamente cobrados durante a partida.">
            <MarketCard title="Escanteios" subtitle={`Mandante (${teamPt(home)})`} prediction={projection.escanteios[home]} />
            <MarketCard title="Escanteios" subtitle="Totais (Partida)" prediction={projection.escanteios.total} />
            <MarketCard title="Escanteios" subtitle={`Visitante (${teamPt(away)})`} prediction={projection.escanteios[away]} />
          </MarketSection>
        )}
        {projection.cartoes?.total && (
          <MarketSection title="Cartões" tip="Cartões amarelos e vermelhos dos jogadores em campo.">
            <MarketCard title="Cartões" subtitle={`Mandante (${teamPt(home)})`} periods={cardPeriods(projection, home)} />
            <MarketCard title="Cartões" subtitle="Totais (Partida)" periods={cardPeriods(projection, "total")} />
            <MarketCard title="Cartões" subtitle={`Visitante (${teamPt(away)})`} periods={cardPeriods(projection, away)} />
          </MarketSection>
        )}
        {projection.impedimentos?.total && (
          <MarketSection title="Impedimentos" tip="Total de impedimentos assinalados pela arbitragem. Mercado novo — exibido sem calibração (a arbitragem de vídeo alterou o padrão histórico).">
            <MarketCard title="Impedimentos" subtitle={`Mandante (${teamPt(home)})`} prediction={projection.impedimentos[home]} />
            <MarketCard title="Impedimentos" subtitle="Totais (Partida)" prediction={projection.impedimentos.total} />
            <MarketCard title="Impedimentos" subtitle={`Visitante (${teamPt(away)})`} prediction={projection.impedimentos[away]} />
          </MarketSection>
        )}
      </div>

      {projection.mercados_derivados && (
        <DerivedMarketsBlock d={projection.mercados_derivados} home={home} away={away} />
      )}
    </motion.div>
  );
}

function MarketSection({ title, tip, children }: { title: string; tip: string; children: React.ReactNode }) {
  return (
    <div>
      <h4 className="text-sm font-bold uppercase text-foreground mb-3 flex items-center justify-center gap-1.5">
        {title} <InfoTooltip text={tip} />
      </h4>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">{children}</div>
    </div>
  );
}
