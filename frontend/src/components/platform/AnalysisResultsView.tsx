"use client";
import React, { useState } from "react";
import ReactMarkdown from "react-markdown";
import { motion, AnimatePresence } from "framer-motion";
import { AlertTriangle, ChevronDown, ShieldAlert, ShieldCheck, Sliders, Sparkles, Target } from "lucide-react";
import type { PlacarMotivo, PredictionResponse, ScorersResponse } from "@/lib/api";
import { onImgError, teamLogoUrl } from "@/lib/api";
import { teamPt } from "@/lib/teamNames";
import InfoTooltip from "@/components/platform/InfoTooltip";
import { MarketCard } from "@/components/platform/MarketCard";
import {
  DuplaChanceCard, HandicapsCard, ParImparCard, FaixaGolsCard, CleanSheetCard,
  VitoriaSemSofrerCard, TimeAMarcarPrimeiroCard, MataMataAgregadoCard,
} from "@/components/platform/DerivedMarkets";
import ScorersCard from "@/components/platform/ScorersCard";
import BetLab from "@/components/platform/BetLab";

// Faixa de odd justa (margem de 7% para menos até 1/prob) a partir de uma prob em %.
export function oddRangeStr(probPct: number): string {
  if (!probPct || probPct <= 0) return '—';
  const odd = 100 / probPct;
  if (odd > 50) return '50+';
  const hi = Math.max(1, odd);
  const lo = Math.max(1, odd * 0.93);
  return lo.toFixed(2) === hi.toFixed(2) ? hi.toFixed(2) : `${lo.toFixed(2)}–${hi.toFixed(2)}`;
}

export function SectionDivider({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-4 mt-8 mb-4">
      <div className="h-px flex-1 bg-gradient-to-r from-transparent to-border" />
      <h3 className="text-lg font-heading font-bold uppercase tracking-wide whitespace-nowrap text-center">{children}</h3>
      <div className="h-px flex-1 bg-gradient-to-l from-transparent to-border" />
    </div>
  );
}

// Subseção de mercado com título SEMPRE visível e botão exibir/ocultar ao lado (colapso
// individual — cada mercado secundário abre/fecha por conta própria). Retraído por padrão.
export function CollapsibleMarket({ title, tip, tipHref, defaultOpen = false, children }: {
  title: string; tip?: string; tipHref?: string; defaultOpen?: boolean; children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div>
      <div className="flex items-center justify-center gap-1.5 mb-3">
        <h4 className="text-sm font-bold uppercase text-foreground flex items-center gap-1.5">
          {title}
          {tip && <InfoTooltip text={tip} href={tipHref} />}
        </h4>
        <button
          onClick={() => setOpen(o => !o)}
          className="flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-medium border border-border/60 bg-muted/40 hover:bg-muted transition-colors"
          aria-expanded={open}
        >
          {open ? 'Ocultar' : 'Exibir'}
          <ChevronDown className={`w-3.5 h-3.5 transition-transform ${open ? 'rotate-180' : ''}`} />
        </button>
      </div>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
            {children}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// Recortes por tempo para gols e cartões (Partida inteira / 1º / 2º), por lado.
export function goalPeriods(p: PredictionResponse, side: string) {
  return {
    'Partida inteira': side === 'total' ? (p.gols as any) : p.gols_equipe?.[side],
    '1º tempo': p.tempos?.gols_1t?.[side],
    '2º tempo': p.tempos?.gols_2t?.[side],
  };
}
export function cardPeriods(p: PredictionResponse, side: string) {
  return {
    'Partida inteira': p.cartoes?.[side],
    '1º tempo': p.tempos?.cartoes_1t?.[side],
    '2º tempo': p.tempos?.cartoes_2t?.[side],
  };
}
// Variantes por tipo de cartão (amarelo isolado / ambos / vermelho isolado) para o
// seletor 🟨-Ambos-🟥 do card de Cartões. Amarelo e vermelho isolados não têm recorte
// por tempo, então entram como um único período ("Partida inteira").
export function cardKindsFor(p: PredictionResponse, side: string) {
  const amarelo = p.cartoes_amarelos?.[side];
  const vermelho = p.cartoes_vermelhos?.[side];
  return {
    amarelo: amarelo ? { 'Partida inteira': amarelo } : undefined,
    ambos: cardPeriods(p, side),
    vermelho: vermelho ? { 'Partida inteira': vermelho } : undefined,
  };
}

// Placar Exato: 3 placares mais prováveis + alerta de potencial de desvio (placar
// fora do padrão), no mesmo estilo do Radar de Anomalias.
export function PlacarExatoCard({ data, home, away, teamIds }: {
  data: NonNullable<PredictionResponse['placar_exato']>;
  home: string;
  away: string;
  teamIds: Record<string, number>;
}) {
  const alerta = data.alerta;
  if (alerta.nivel === 'normal') return null;

  const isAlert = true;
  const alertStyles =
    alerta.nivel === 'alto' ? 'bg-amber-500/10 border-amber-500/30'
    : 'bg-amber-500/5 border-amber-500/20';
  // Texto do motivo em PT-BR: o lado favorito vira o nome traduzido (teamPt).
  const motivoTexto = (m: PlacarMotivo): string => {
    if (m.tipo === 'favoritismo') {
      const fav = m.favorito_lado === 'mandante' ? teamPt(home) : teamPt(away);
      return `${fav} é forte favorito: ${m.exp_alto} × ${m.exp_baixo} gols projetados (Elo, forma e ataque/defesa embutidos).`;
    }
    return `Placar alto projetado: ${m.exp_total} gols esperados, P(4+ gols) = ${m.prob_4_mais}%.`;
  };
  return (
    <div className="bg-card border border-border/50 rounded-xl p-5">
      <h4 className="text-sm font-semibold mb-3 flex items-center justify-center gap-1.5">
        <Target className="w-4 h-4 text-purple-500" />
        Placar Exato
        <InfoTooltip text="Os 3 placares mais prováveis segundo a matriz conjunta de gols do modelo (Dixon-Coles). A faixa de odd justa usa 7% de margem até 1/probabilidade." href="/como-funciona#mercado-placar" />
      </h4>
      <div className="grid grid-cols-3 gap-2 mb-4">
        {data.top.map((s, i) => (
          <div key={i} className={`text-center rounded-lg p-2 border ${i === 0 ? 'bg-purple-500/10 border-purple-500/30' : 'bg-muted/30 border-border/30'}`}>
            <div className="flex items-center justify-center gap-1.5 mb-0.5">
              {teamLogoUrl(teamIds[home]) && (
                <img src={teamLogoUrl(teamIds[home])!} alt="" className="w-4 h-4 object-contain" onError={onImgError} />
              )}
              <p className="text-xl font-mono font-bold text-foreground leading-none">{s.mandante}<span className="text-muted-foreground mx-0.5">–</span>{s.visitante}</p>
              {teamLogoUrl(teamIds[away]) && (
                <img src={teamLogoUrl(teamIds[away])!} alt="" className="w-4 h-4 object-contain" onError={onImgError} />
              )}
            </div>
            <p className="text-[11px] font-mono text-cyan-400 mt-0.5">{s.prob.toFixed(1)}%</p>
            <p className="text-[9px] text-muted-foreground mt-0.5">odd {oddRangeStr(s.prob)}</p>
          </div>
        ))}
      </div>
      <div className={`rounded-lg p-3 border ${alertStyles}`}>
        <p className="text-xs font-medium mb-1.5 flex items-center gap-1.5">
          <AlertTriangle className={`w-3.5 h-3.5 ${isAlert ? 'text-amber-400' : 'text-muted-foreground'}`} />
          {isAlert ? `Alerta de desvio: potencial ${alerta.nivel}` : 'Padrão de placar normal'}
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

// Badge de confiabilidade do JOGO pela cobertura de dados refinados (box-score).
export function MatchReliabilityBadge({ confiabilidade }: { confiabilidade: PredictionResponse['confiabilidade'] }) {
  if (!confiabilidade) return null;
  const tier = confiabilidade.tier;
  const styles =
    tier === 'Alta' ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-500'
    : tier === 'Média' ? 'bg-amber-500/10 border-amber-500/30 text-amber-500'
    : 'bg-red-500/10 border-red-500/30 text-red-500';
  return (
    <div className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-medium border ${styles}`}>
      {tier === 'Alta' ? <ShieldCheck className="w-3.5 h-3.5" /> : <ShieldAlert className="w-3.5 h-3.5" />}
      Confiabilidade dos dados: {tier}
      <InfoTooltip text={confiabilidade._resumo} href="/como-funciona#metrica-confiabilidade" />
    </div>
  );
}

// Bloco de resultado de uma análise (Mercados Principais/Secundários + Funções Avançadas),
// reutilizado pela página autenticada (app/page.tsx) e pela página pública de compartilhamento
// (app/compartilhado/[token]/page.tsx). Deliberadamente NÃO inclui "Monte sua Seleção"
// (BetBuilder) -- depende de analysisId/carteira, fora de escopo de uma visão pública/somente-leitura.
export function AnalysisResultsView({ prediction, home, away, teamIds, scorers }: {
  prediction: PredictionResponse;
  home: string;
  away: string;
  teamIds: Record<string, number>;
  scorers: ScorersResponse | null;
}) {
  const [showAdvanced, setShowAdvanced] = useState(false);

  return (
    <div className="space-y-6">
      {/* Badge de confiabilidade do jogo (cobertura de dados refinados) */}
      {prediction.confiabilidade && (
        <div className="flex justify-center">
          <MatchReliabilityBadge confiabilidade={prediction.confiabilidade} />
        </div>
      )}

      {/* ANÁLISE APROFUNDADA (Opcional) */}
      {prediction.deep_analysis && (
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="bg-slate-900 border-2 border-indigo-500/40 rounded-xl overflow-hidden shadow-[0_0_20px_rgba(79,70,229,0.15)]">
          <div className="bg-indigo-500/10 px-5 py-3 border-b border-indigo-500/20 flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-indigo-400" />
            <h3 className="font-heading font-bold text-lg text-indigo-100 tracking-wide uppercase">Análise Aprofundada Detalhada</h3>
          </div>
          <div className="p-5 prose prose-sm dark:prose-invert max-w-none text-slate-300">
            <ReactMarkdown>{(prediction.deep_analysis as any).markdown_content}</ReactMarkdown>
          </div>
          <div className="bg-black/20 px-5 py-2.5 text-right border-t border-white/5">
            <span className="text-xs text-muted-foreground italic">Análise por <strong className="text-indigo-300">{(prediction.deep_analysis as any).analyst_name}</strong></span>
          </div>
        </motion.div>
      )}

      {/* MERCADOS PRINCIPAIS — Resultados | Ambas Marcam / Dupla Chance / Placar Exato / Handicaps */}
      <SectionDivider>MERCADOS PRINCIPAIS</SectionDivider>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-stretch">
        {/* Resultados (1X2) */}
        <div className="bg-card border border-border/50 rounded-xl p-5 flex flex-col justify-center text-center shadow-sm h-full">
          <p className="text-xs text-muted-foreground mb-4 font-semibold uppercase tracking-wider">Resultados</p>
          <div className="flex flex-wrap items-center justify-center gap-3 sm:gap-4">
            <div className="text-center w-[30%] min-w-[82px]">
              {teamLogoUrl(teamIds[home]) && (
                <img src={teamLogoUrl(teamIds[home])!} alt="" className="w-8 h-8 mx-auto mb-1 object-contain" loading="lazy" onError={onImgError} />
              )}
              <p className="text-sm font-medium text-foreground mb-1 truncate">{teamPt(home)}</p>
              <p className="text-3xl font-bold font-mono text-emerald-400">{prediction.vencedor.probabilidades[home]}%</p>
              <p className="text-[10px] text-muted-foreground mt-1">odd justa: {oddRangeStr(prediction.vencedor.probabilidades[home])}</p>
            </div>
            <div className="text-center w-[30%] min-w-[82px] border-x border-border/50">
              <p className="text-sm font-medium text-muted-foreground mb-1">Empate</p>
              <p className="text-2xl font-bold font-mono text-muted-foreground">{prediction.vencedor.probabilidades["Empate"]}%</p>
              <p className="text-[10px] text-muted-foreground mt-1">odd justa: {oddRangeStr(prediction.vencedor.probabilidades["Empate"])}</p>
            </div>
            <div className="text-center w-[30%] min-w-[82px]">
              {teamLogoUrl(teamIds[away]) && (
                <img src={teamLogoUrl(teamIds[away])!} alt="" className="w-8 h-8 mx-auto mb-1 object-contain" loading="lazy" onError={onImgError} />
              )}
              <p className="text-sm font-medium text-foreground mb-1 truncate">{teamPt(away)}</p>
              <p className="text-3xl font-bold font-mono text-cyan-400">{prediction.vencedor.probabilidades[away]}%</p>
              <p className="text-[10px] text-muted-foreground mt-1">odd justa: {oddRangeStr(prediction.vencedor.probabilidades[away])}</p>
            </div>
          </div>
        </div>

        {/* Ambas Marcam (à direita de Resultados) */}
        {prediction.ambas_marcam && (
          <div className="bg-card border border-border/50 rounded-xl p-5 flex flex-col h-full">
            <h4 className="text-sm font-semibold mb-3 flex items-center justify-center gap-1.5">
              Ambas Marcam
              <InfoTooltip text="Probabilidade de as duas equipes marcarem pelo menos um gol na partida." href="/como-funciona#mercado-btts" />
            </h4>
            <div className="flex-1 flex flex-wrap items-center justify-center gap-x-6 gap-y-3 sm:gap-x-8 text-center">
              <div>
                <p className="text-[10px] uppercase tracking-wide text-muted-foreground mb-1">Sim</p>
                <p className="text-2xl font-mono font-bold text-emerald-400">{prediction.ambas_marcam.prob_sim}%</p>
                <p className="text-[10px] text-muted-foreground mt-1">odd justa: {oddRangeStr(prediction.ambas_marcam.prob_sim)}</p>
              </div>
              <div>
                <p className="text-[10px] uppercase tracking-wide text-muted-foreground mb-1">Não</p>
                <p className="text-2xl font-mono font-bold text-blue-400">{(100 - prediction.ambas_marcam.prob_sim).toFixed(1)}%</p>
                <p className="text-[10px] text-muted-foreground mt-1">odd justa: {oddRangeStr(100 - prediction.ambas_marcam.prob_sim)}</p>
              </div>
            </div>
          </div>
        )}

        {/* Dupla Chance e Time a Marcar Primeiro | Handicaps */}
        <div className="flex flex-col gap-4 lg:gap-6">
          {prediction.mercados_derivados && <DuplaChanceCard d={prediction.mercados_derivados} home={home} away={away} />}
          {prediction.time_marca_primeiro && <TimeAMarcarPrimeiroCard d={prediction.time_marca_primeiro} home={home} away={away} />}
        </div>
        {prediction.mercados_derivados && <HandicapsCard d={prediction.mercados_derivados} home={home} away={away} teamIds={teamIds} />}
        {/* Placar Exato — card detalhado em largura total */}
        {prediction.placar_exato && (
          <div className="md:col-span-2">
            <PlacarExatoCard data={prediction.placar_exato} home={home} away={away} teamIds={teamIds} />
          </div>
        )}
      </div>

      {/* MERCADOS SECUNDÁRIOS — cada mercado colapsa individualmente (título sempre visível) */}
      <SectionDivider>MERCADOS SECUNDÁRIOS</SectionDivider>
      <div className="space-y-6">
        {/* Gols (mandante/total/visitante, com seletor de tempo) */}
        {prediction.gols && (
          <CollapsibleMarket title="Gols" tip="Gols marcados na partida. Use o seletor de cada cartão para ver partida inteira, 1º ou 2º tempo." tipHref="/como-funciona#mercado-gols">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              <MarketCard title="Gols" subtitle={teamPt(home)} periods={goalPeriods(prediction, home)} />
              <MarketCard title="Gols" subtitle="Totais (Partida)" periods={goalPeriods(prediction, 'total')} />
              <MarketCard title="Gols" subtitle={teamPt(away)} periods={goalPeriods(prediction, away)} />
            </div>
            {prediction.mercados_derivados && (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mt-4">
                <ParImparCard d={prediction.mercados_derivados} />
                <FaixaGolsCard d={prediction.mercados_derivados} />
                <CleanSheetCard d={prediction.mercados_derivados} home={home} away={away} />
                <VitoriaSemSofrerCard d={prediction.mercados_derivados} home={home} away={away} />
              </div>
            )}
          </CollapsibleMarket>
        )}

        {/* Finalizações */}
        {prediction.chutes && (
          <CollapsibleMarket title="Finalizações" tip="Conta qualquer tentativa de marcar gol, independentemente da direção. Inclui chutes no alvo, para fora, na trave e também os bloqueados pela defesa adversária." tipHref="/como-funciona#mercado-finalizacoes">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {prediction.chutes_equipe && prediction.chutes_equipe[home] && (
                <MarketCard title="Finalizações" subtitle={teamPt(home)} prediction={prediction.chutes_equipe[home]} />
              )}
              <MarketCard title="Finalizações" subtitle="Totais (Partida)" prediction={prediction.chutes as any} />
              {prediction.chutes_equipe && prediction.chutes_equipe[away] && (
                <MarketCard title="Finalizações" subtitle={teamPt(away)} prediction={prediction.chutes_equipe[away]} />
              )}
            </div>
          </CollapsibleMarket>
        )}

        {/* Chutes a Gol */}
        {prediction.chutes_a_gol && prediction.chutes_a_gol.total && (
          <CollapsibleMarket title="Chutes a Gol" tip="Considera apenas os chutes que vão na direção exata da baliza e que seriam gol se não houvesse intervenção do goleiro. Chutes na trave, para fora ou bloqueados não contam." tipHref="/como-funciona#mercado-finalizacoes-gol">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              <MarketCard title="Chutes a Gol" subtitle={teamPt(home)} prediction={prediction.chutes_a_gol[home]} />
              <MarketCard title="Chutes a Gol" subtitle="Totais (Partida)" prediction={prediction.chutes_a_gol.total} />
              <MarketCard title="Chutes a Gol" subtitle={teamPt(away)} prediction={prediction.chutes_a_gol[away]} />
            </div>
          </CollapsibleMarket>
        )}

        {/* Escanteios */}
        {prediction.escanteios && prediction.escanteios.total && (
          <CollapsibleMarket title="Escanteios" tip="Soma dos tiros de canto efetivamente cobrados durante a partida. Escanteios assinalados pelo árbitro, mas não cobrados antes do apito final, geralmente não entram na conta." tipHref="/como-funciona#mercado-escanteios">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              <MarketCard title="Escanteios" subtitle={teamPt(home)} prediction={prediction.escanteios[home]} />
              <MarketCard title="Escanteios" subtitle="Totais (Partida)" prediction={prediction.escanteios.total} />
              <MarketCard title="Escanteios" subtitle={teamPt(away)} prediction={prediction.escanteios[away]} />
            </div>
          </CollapsibleMarket>
        )}

        {/* Cartões (com seletor de tempo + seletor 🟨/Ambos/🟥 por tipo) */}
        {prediction.cartoes && prediction.cartoes.total && (
          <CollapsibleMarket title="Cartões" tip="Contagem de cartões amarelos e vermelhos aplicados aos jogadores ativos em campo. Use o seletor 🟨/Ambos/🟥 em cada card para ver amarelos e vermelhos isolados. Cartões mostrados para jogadores no banco de reservas ou para a comissão técnica não são contabilizados." tipHref="/como-funciona#mercado-cartoes">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              <MarketCard title="Cartões" subtitle={teamPt(home)} cardKinds={cardKindsFor(prediction, home)} />
              <MarketCard title="Cartões" subtitle="Totais (Partida)" cardKinds={cardKindsFor(prediction, 'total')} />
              <MarketCard title="Cartões" subtitle={teamPt(away)} cardKinds={cardKindsFor(prediction, away)} />
            </div>
          </CollapsibleMarket>
        )}

        {/* Impedimentos (mercado novo, exibido cru) */}
        {prediction.impedimentos && prediction.impedimentos.total && (
          <CollapsibleMarket title="Impedimentos" tip="Total de impedimentos assinalados na partida.">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              <MarketCard title="Impedimentos" subtitle={teamPt(home)} prediction={prediction.impedimentos[home]} />
              <MarketCard title="Impedimentos" subtitle="Totais (Partida)" prediction={prediction.impedimentos.total} />
              <MarketCard title="Impedimentos" subtitle={teamPt(away)} prediction={prediction.impedimentos[away]} />
            </div>
          </CollapsibleMarket>
        )}

        {/* Qualificação/agregado (mata-mata ida-volta) — só competições continentais de clube com 2 pernas */}
        {prediction.mata_mata_agregado && (
          <CollapsibleMarket title="Mata-Mata (Ida e Volta)" tip="Probabilidade de classificação no agregado das duas pernas, assumindo mando invertido na volta e pernas independentes (sem regra do gol fora).">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <MataMataAgregadoCard d={prediction.mata_mata_agregado} />
              <MarketCard title="Gols Agregados" subtitle="Total (2 pernas)" prediction={prediction.mata_mata_agregado.gols_agregados} />
            </div>
          </CollapsibleMarket>
        )}

        {/* Jogador — modelo de goleador (dentro dos secundários, colapso individual) */}
        {scorers?.disponivel && (
          <CollapsibleMarket title="Jogador" tip="Por jogador do elenco recente, se jogar: probabilidade de marcar a qualquer momento e de dar ≥ 0,5/1,5/2,5 finalizações — modelos de goleador e de finalizações (forma + defesa do adversário + mando + minutos), calibrados. Odd justa = 1/probabilidade, sem margem de casa.">
            <ScorersCard data={scorers} home={home} away={away} teamIds={teamIds} embedded />
          </CollapsibleMarket>
        )}
      </div>

      {/* FUNÇÕES AVANÇADAS DE ANÁLISE */}
      <SectionDivider>FUNÇÕES AVANÇADAS DE ANÁLISE</SectionDivider>
      <div className="flex justify-center mb-4">
        <button
          onClick={() => setShowAdvanced(s => !s)}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium border border-border/60 bg-muted/40 hover:bg-muted transition-colors"
        >
          <Sliders className="w-4 h-4" />
          {showAdvanced ? 'Ocultar ferramentas' : 'Explorador de Linha e Value Betting'}
          <ChevronDown className={`w-4 h-4 transition-transform ${showAdvanced ? 'rotate-180' : ''}`} />
        </button>
      </div>
      <AnimatePresence initial={false}>
        {showAdvanced && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
            <BetLab prediction={prediction} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
