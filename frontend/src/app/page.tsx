"use client";
import React, { useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { AlertTriangle, Zap, TrendingUp, ShieldAlert, ShieldCheck, ArrowDown, CheckCircle2, Target, ChevronDown, Sliders } from 'lucide-react';
import { api, PredictionResponse, PlacarMotivo, RecentMatch, Anomaly, UpcomingFixture, teamLogoUrl } from '@/lib/api';
import InfoTooltip from '@/components/platform/InfoTooltip';
import { usePrediction } from '@/lib/PredictionContext';
import { TeamSelect } from '@/components/platform/TeamSelect';
import { MarketCard } from '@/components/platform/MarketCard';
import { teamPt } from '@/lib/teamNames';
import { competitionPt } from '@/lib/competitionNames';
import { MatchPickerModal } from '@/components/platform/MatchPickerModal';
import { MatchHeader } from '@/components/platform/MatchHeader';
import Link from 'next/link';
import { Coins, Sparkles } from 'lucide-react';
import { useAuth } from '@/lib/AuthContext';
import { analysisApi } from '@/lib/monetizationApi';
import BetLab from '@/components/platform/BetLab';
import BetBuilder from '@/components/platform/BetBuilder';
import { DuplaChanceCard, HandicapsCard, ParImparCard, FaixaGolsCard, CleanSheetCard, VitoriaSemSofrerCard } from '@/components/platform/DerivedMarkets';
import H2HCard from '@/components/platform/H2HCard';
import ScorersCard from '@/components/platform/ScorersCard';
import type { ScorersResponse } from '@/lib/api';

// Data em dd/mm/aaaa a partir de "aaaa-mm-dd[...]".
function formatDateBR(s: string): string {
  const d = (s || '').slice(0, 10).split('-');
  return d.length === 3 ? `${d[2]}/${d[1]}/${d[0]}` : s;
}

// Faixa de odd justa (margem de 7% para menos até 1/prob) a partir de uma prob em %.
function oddRangeStr(probPct: number): string {
  if (!probPct || probPct <= 0) return '—';
  const odd = 100 / probPct;
  if (odd > 50) return '50+';
  // Odd nunca abaixo de 1.00.
  const hi = Math.max(1, odd);
  const lo = Math.max(1, odd * 0.93);
  return lo.toFixed(2) === hi.toFixed(2) ? hi.toFixed(2) : `${lo.toFixed(2)}–${hi.toFixed(2)}`;
}

// Título de seção centralizado com linhas em degradê preenchendo a horizontal.
function SectionDivider({ children }: { children: React.ReactNode }) {
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
function CollapsibleMarket({ title, tip, tipHref, defaultOpen = false, children }: {
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
function goalPeriods(p: PredictionResponse, side: string) {
  return {
    'Partida inteira': side === 'total' ? (p.gols as any) : p.gols_equipe?.[side],
    '1º tempo': p.tempos?.gols_1t?.[side],
    '2º tempo': p.tempos?.gols_2t?.[side],
  };
}
function cardPeriods(p: PredictionResponse, side: string) {
  return {
    'Partida inteira': p.cartoes?.[side],
    '1º tempo': p.tempos?.cartoes_1t?.[side],
    '2º tempo': p.tempos?.cartoes_2t?.[side],
  };
}

// Placar Exato: 3 placares mais prováveis + alerta de potencial de desvio (placar
// fora do padrão), no mesmo estilo do Radar de Anomalias.
function PlacarExatoCard({ data, home, away }: {
  data: NonNullable<PredictionResponse['placar_exato']>;
  home: string;
  away: string;
}) {
  const alerta = data.alerta;
  const isAlert = alerta.nivel !== 'normal';
  const alertStyles =
    alerta.nivel === 'alto' ? 'bg-amber-500/10 border-amber-500/30'
    : alerta.nivel === 'moderado' ? 'bg-amber-500/5 border-amber-500/20'
    : 'bg-muted/50 border-border/50';
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
      <h4 className="text-sm font-semibold mb-1 flex items-center justify-center gap-1.5">
        <Target className="w-4 h-4 text-purple-500" />
        Placar Exato
        <InfoTooltip text="Os 3 placares mais prováveis segundo a matriz conjunta de gols do modelo (Dixon-Coles). A faixa de odd justa usa 7% de margem até 1/probabilidade." href="/como-funciona#mercado-placar" />
      </h4>
      <p className="text-[10px] text-muted-foreground mb-3">
        {teamPt(home)} <span className="opacity-60">(mandante)</span> × {teamPt(away)} <span className="opacity-60">(visitante)</span>
      </p>
      <div className="grid grid-cols-3 gap-2 mb-4">
        {data.top.map((s, i) => (
          <div key={i} className={`text-center rounded-lg p-2 border ${i === 0 ? 'bg-purple-500/10 border-purple-500/30' : 'bg-muted/30 border-border/30'}`}>
            <p className="text-xl font-mono font-bold text-foreground">{s.mandante}<span className="text-muted-foreground mx-0.5">–</span>{s.visitante}</p>
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
function MatchReliabilityBadge({ confiabilidade }: { confiabilidade: PredictionResponse['confiabilidade'] }) {
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

function DataReliabilityBadge({ totalMatches }: { totalMatches: number }) {
  const isLow = totalMatches < 10;
  return (
    <div className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-[10px] font-medium border ${isLow ? 'bg-amber-500/10 border-amber-500/30 text-amber-500' : 'bg-emerald-500/10 border-emerald-500/30 text-emerald-500'}`}>
      {isLow ? <ShieldAlert className="w-3 h-3" /> : <ShieldCheck className="w-3 h-3" />}
      {isLow ? `Confiabilidade Baixa (${totalMatches} jogos no BD)` : `Confiabilidade Adequada (${totalMatches} jogos)`}
    </div>
  );
}

// Versão em LINHA do jogo recente (para o bloco compacto lateral) — mesmas informações
// do card, clicável, encaminha às estatísticas do jogo.
function RecentMatchRow({ match, onOpen }: { match: RecentMatch; onOpen?: () => void }) {
  const diff = match.goals_scored - match.goals_conceded;
  const result = diff > 0 ? 'V' : diff < 0 ? 'D' : 'E';
  const color = result === 'V' ? 'bg-emerald-500/20 text-emerald-500 border-emerald-500/30' : result === 'D' ? 'bg-red-500/20 text-red-500 border-red-500/30' : 'bg-amber-500/20 text-amber-500 border-amber-500/30';
  const placar = match.is_home ? `${match.goals_scored}-${match.goals_conceded}` : `${match.goals_conceded}-${match.goals_scored}`;
  return (
    <button
      onClick={onOpen}
      className="w-full flex items-center gap-2 p-2 bg-muted/40 border border-border/50 rounded-lg text-left hover:border-cyan-500/40 hover:bg-muted/70 transition-colors cursor-pointer"
      title="Ver estatísticas deste jogo"
    >
      <span className={`flex items-center justify-center w-5 h-5 rounded-[4px] border font-bold text-[11px] shrink-0 ${color}`}>{result}</span>
      <div className="min-w-0 flex-1">
        <p className="text-xs font-semibold truncate">
          {match.is_home ? 'vs' : '@'} {teamPt(match.opponent)}
          <span className="font-mono font-normal text-muted-foreground ml-1.5">{placar}</span>
        </p>
        <p className="text-[9px] text-muted-foreground truncate">
          {formatDateBR(match.date)}{match.competition ? ` · ${competitionPt(match.competition)}` : ''}
        </p>
      </div>
      <div className="flex gap-1.5 text-[10px] text-muted-foreground shrink-0">
        <span title="Chutes">👟{match.sb_shots || 0}</span>
        <span title="Escanteios">🚩{match.sb_corners || 0}</span>
        <span title="Cartões">🟨{match.sb_cards || 0}</span>
      </div>
    </button>
  );
}

// Card compacto da equipe (nome + últimos 5 jogos em linhas + radar de anomalias),
// para empilhar no lado direito do bloco de confronto.
function TeamRecentBlock({ teamId, form, anomalies, label, loading, teamIds, onOpenMatch }: {
  teamId: string; form: { matches: RecentMatch[]; total: number }; anomalies: Anomaly[];
  label: string; loading: boolean; teamIds: Record<string, number>; onOpenMatch: (m: RecentMatch) => void;
}) {
  return (
    <div className="bg-card border border-border/50 rounded-xl p-4 h-full flex flex-col">
      <div className="flex items-center justify-center gap-2 mb-2">
        {teamLogoUrl(teamIds[teamId]) && (
          <img src={teamLogoUrl(teamIds[teamId])!} alt="" className="w-6 h-6 object-contain" loading="lazy" onError={(e) => { e.currentTarget.style.display = 'none'; }} />
        )}
        <div className="text-center">
          <span className="text-[9px] uppercase tracking-wide text-muted-foreground block leading-none">{label}</span>
          <h3 className="text-sm font-semibold leading-tight">{teamPt(teamId)}</h3>
        </div>
      </div>
      {loading ? (
        <div className="flex items-center justify-center gap-2 py-8 text-muted-foreground text-xs">
          <div className="w-4 h-4 border-2 border-muted-foreground/30 border-t-emerald-500 rounded-full animate-spin" /> Buscando…
        </div>
      ) : (<>
        <div className="flex items-center justify-between gap-2 mb-1.5">
          <p className="text-[11px] text-muted-foreground">Últimos {form.matches.length} jogos</p>
          <DataReliabilityBadge totalMatches={form.total} />
        </div>
        <div className="flex gap-2">
          {/* Seta lateral: topo = mais recente, base = mais antigo */}
          <div className="flex flex-col items-center text-[8px] uppercase text-muted-foreground shrink-0 py-0.5">
            <span>Recente</span>
            <div className="flex-1 w-px bg-border my-1" />
            <ArrowDown className="w-3 h-3" />
            <span>Antigo</span>
          </div>
          <div className="flex-1 space-y-1.5 min-w-0">
            {form.matches.map((m, i) => (
              <RecentMatchRow key={i} match={m} onOpen={() => onOpenMatch(m)} />
            ))}
            {form.matches.length === 0 && <p className="text-xs text-muted-foreground italic py-2">Sem jogos recentes.</p>}
          </div>
        </div>
        <div className={`rounded-lg p-2.5 mt-3 ${anomalies.length > 0 ? 'bg-amber-500/5 border border-amber-500/20' : 'bg-muted/50 border border-border/50'}`}>
          <p className="text-[11px] font-medium mb-1 flex items-center gap-1.5">
            <Zap className={`w-3 h-3 ${anomalies.length > 0 ? 'text-amber-400' : 'text-muted-foreground'}`} /> Radar de Anomalias
          </p>
          {anomalies.length > 0 ? (
            <ul className="space-y-0.5">
              {anomalies.map((a, i) => (
                <li key={i} className="text-[11px] text-amber-500/80 flex items-start gap-1"><AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" /><span>{a.message}</span></li>
              ))}
            </ul>
          ) : (
            <p className="text-[11px] text-muted-foreground italic">Nenhum desvio estatístico recente.</p>
          )}
        </div>
      </>)}
    </div>
  );
}

export default function Previsoes() {
  const [teams, setTeams] = React.useState<string[]>([]);
  const [tournaments, setTournaments] = React.useState<string[]>([]);
  
  const router = useRouter();
  const {
    homeTeamId, setHomeTeamId, awayTeamId, setAwayTeamId, competition, setCompetition, neutralField, setNeutralField,
    analysis, setAnalysis, mode, setMode, fixtureId, setFixtureId, matchDate, setMatchDate,
  } = usePrediction();
  const { user, wallet, refreshWallet } = useAuth();

  const [loading, setLoading] = useState(false);
  // projection é derivada da análise persistida no contexto (persiste ao navegar e voltar).
  const projection = analysis ? (analysis.snapshot as unknown as PredictionResponse) : null;
  const setProjection = (_: PredictionResponse | null) => { if (_ === null) setAnalysis(null); };
  const [errMsg, setErrMsg] = useState<string | null>(null);
  const credits = wallet ? Math.floor(Number(wallet.available_balance)) : 0;
  
  const [homeForm, setHomeForm] = useState<{matches: RecentMatch[], total: number}>({matches: [], total: 0});
  const [awayForm, setAwayForm] = useState<{matches: RecentMatch[], total: number}>({matches: [], total: 0});
  const [homeAnomalies, setHomeAnomalies] = useState<Anomaly[]>([]);
  const [awayAnomalies, setAwayAnomalies] = useState<Anomaly[]>([]);
  
  const [h2hData, setH2hData] = useState<any>(null);
  const [scorers, setScorers] = useState<ScorersResponse | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);
  // F5: com as duas equipes escolhidas, o card de Configuração recolhe (só o título);
  // "Alterar Equipes" (no cabeçalho flutuante) reabre para trocar.
  const [editingTeams, setEditingTeams] = useState(false);

  // Prováveis goleadores (modelo de goleador) — busca ao gerar a análise.
  React.useEffect(() => {
    if (analysis && homeTeamId && awayTeamId && homeTeamId !== awayTeamId) {
      api.scorers(homeTeamId, awayTeamId).then(setScorers).catch(() => setScorers(null));
    } else {
      setScorers(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [analysis]);

  // Busca o H2H assim que as duas seleções estão escolhidas — o card de confronto
  // direto fica disponível ANTES de gerar a análise (e persiste ao voltar à página).
  React.useEffect(() => {
    if (homeTeamId && awayTeamId && homeTeamId !== awayTeamId) {
      setLoadingH2H(true);
      api.h2h(homeTeamId, awayTeamId).then(h => setH2hData(h?.metrics ?? null)).catch(() => setH2hData(null)).finally(() => setLoadingH2H(false));
    } else {
      setH2hData(null); setLoadingH2H(false);
    }
  }, [homeTeamId, awayTeamId]);

  // Modo de análise (mode) e data (matchDate) vêm do contexto (persistem ao navegar).
  const [referee, setReferee] = useState('');
  const [referees, setReferees] = useState<string[]>([]);
  const [upcoming, setUpcoming] = useState<UpcomingFixture[]>([]);
  const [teamIds, setTeamIds] = useState<Record<string, number>>({});
  const [modalOpen, setModalOpen] = useState(false);
  const [loadingUpcoming, setLoadingUpcoming] = useState(false);
  const [loadingHome, setLoadingHome] = useState(false);
  const [loadingAway, setLoadingAway] = useState(false);
  const [loadingH2H, setLoadingH2H] = useState(false);

  React.useEffect(() => {
    api.referees().then(r => setReferees(r.referees)).catch(() => {});
    setLoadingUpcoming(true);
    api.upcomingFixtures().then(r => setUpcoming(r.fixtures)).catch(() => {}).finally(() => setLoadingUpcoming(false));
    api.teamIds().then(setTeamIds).catch(() => {});
  }, []);

  const selectFutureFixture = (fid: string) => {
    const fx = upcoming.find(f => f.fixture_id === fid);
    if (!fx) return;
    setHomeTeamId(fx.home);
    setAwayTeamId(fx.away);
    setCompetition(fx.tournament);
    setNeutralField(fx.neutral);
    setMatchDate(fx.date);
    setFixtureId(Number(fx.fixture_id));
    setProjection(null);
    setEditingTeams(false); // recolhe o card de configuração após escolher a partida
  };

  React.useEffect(() => {
    api.teams().then(res => {
      setTeams(res.teams);
      setTournaments(res.tournaments);
    }).catch(console.error);
  }, []);

  React.useEffect(() => {
    if (homeTeamId) {
      setLoadingHome(true);
      Promise.all([
        api.recentMatches(homeTeamId).then(res => setHomeForm({matches: res.matches, total: res.total_matches})),
        api.teamAnomalies(homeTeamId).then(res => setHomeAnomalies(res.anomalies)),
      ]).catch(() => {}).finally(() => setLoadingHome(false));
    } else {
      setHomeForm({matches: [], total: 0});
      setHomeAnomalies([]);
    }
  }, [homeTeamId]);

  React.useEffect(() => {
    if (awayTeamId) {
      setLoadingAway(true);
      Promise.all([
        api.recentMatches(awayTeamId).then(res => setAwayForm({matches: res.matches, total: res.total_matches})),
        api.teamAnomalies(awayTeamId).then(res => setAwayAnomalies(res.anomalies)),
      ]).catch(() => {}).finally(() => setLoadingAway(false));
    } else {
      setAwayForm({matches: [], total: 0});
      setAwayAnomalies([]);
    }
  }, [awayTeamId]);

  const canGenerate = homeTeamId && awayTeamId && homeTeamId !== awayTeamId;

  const handleGenerate = useCallback(async () => {
    if (!canGenerate) return;
    if (!user) { router.push('/entrar'); return; }
    setLoading(true);
    setErrMsg(null);
    setAnalysis(null);

    try {
      const a = await analysisApi.create({
        home_team: homeTeamId,
        away_team: awayTeamId,
        tournament: competition,
        neutral: neutralField,
        type: mode === 'futura' ? 'future_match' : 'independent',
        fixture_id: mode === 'futura' ? fixtureId : null,
      });
      setAnalysis(a); // persiste no contexto — não some ao navegar e voltar
      await refreshWallet();
    } catch (e) {
      setErrMsg((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [canGenerate, user, homeTeamId, awayTeamId, competition, neutralField, mode, fixtureId, refreshWallet, router, setAnalysis]);

  return (
    <div className="space-y-6">
      {homeTeamId && awayTeamId && (
        <MatchHeader home={homeTeamId} away={awayTeamId} teamIds={teamIds} competition={competition} date={matchDate} referee={referee} neutral={neutralField} onEditTeams={() => setEditingTeams(true)} />
      )}
      {(canGenerate && !editingTeams) ? (
        /* F5: recolhido — só o título; trocar equipes é feito pelo botão flutuante "Alterar Equipes" */
        <motion.div layout initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="bg-card border border-border/50 rounded-xl px-5 py-3 mx-auto max-w-full w-full flex items-center justify-center gap-2">
          <TrendingUp className="w-4 h-4 text-emerald-500" />
          <h2 className="text-sm font-heading font-bold">Configuração do Confronto</h2>
        </motion.div>
      ) : (
      <motion.div
        layout
        transition={{ layout: { duration: 0.4, ease: 'easeInOut' } }}
        initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
        className={`bg-card border border-border/50 rounded-xl p-5 mx-auto max-w-full ${mode === 'independente' ? 'w-full' : 'w-fit'}`}
      >
        <div className="flex items-center justify-between gap-2 mb-4">
          <h2 className="text-lg font-heading font-bold flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-emerald-500" /> Configuração do Confronto
          </h2>
          {canGenerate && editingTeams && (
            <button onClick={() => setEditingTeams(false)} className="text-xs font-medium text-muted-foreground hover:text-foreground border border-border/60 rounded-md px-3 py-1.5">
              Concluir
            </button>
          )}
        </div>

        {/* Modo de análise: partida futura agendada x análise independente */}
        <div className="inline-flex p-1 mb-4 rounded-lg bg-muted text-xs font-medium">
          <button
            onClick={() => setMode('futura')}
            className={`px-3 py-1.5 rounded-md transition-colors ${mode === 'futura' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
          >Selecionar Partida Agendada</button>
          <button
            onClick={() => { setMode('independente'); setMatchDate(undefined); }}
            className={`px-3 py-1.5 rounded-md transition-colors ${mode === 'independente' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
          >Análise Independente</button>
          <InfoTooltip
            text={'Selecionar Partida Agendada: selecione uma partida agendada e reserve um crédito para gerar a análise — elegível para a Oferta "ParcerIA". Análise Independente: escolha duas equipes quaisquer, sem necessariamente haver um jogo marcado entre elas, e utilize um crédito para gerar a análise — não elegível para a Oferta "ParcerIA".'}
            href="/como-funciona#promocao"
            linkText='Clique para conhecer a Oferta "ParcerIA" →'
          />
        </div>

        {mode === 'futura' && (
          <div className="mb-2">
            <button onClick={() => !loadingUpcoming && setModalOpen(true)} disabled={loadingUpcoming}
              className="px-4 py-2 rounded-lg text-sm font-medium border border-cyan-500/40 bg-cyan-500/10 text-foreground hover:bg-cyan-500/20 transition-colors disabled:opacity-60 inline-flex items-center gap-2">
              {loadingUpcoming && <span className="w-3.5 h-3.5 border-2 border-current/30 border-t-current rounded-full animate-spin" />}
              {loadingUpcoming
                ? 'Buscando partidas agendadas…'
                : (homeTeamId && awayTeamId ? `${teamPt(homeTeamId)} x ${teamPt(awayTeamId)} — trocar partida` : 'Escolher partida agendada')}
            </button>
            {homeTeamId && awayTeamId && (
              <p className="text-[11px] text-muted-foreground mt-2">Competição: {competition} · {neutralField ? 'Campo neutro' : 'Com mando'}</p>
            )}
          </div>
        )}

        {mode === 'independente' && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
            <div>
              <Label className="text-xs text-muted-foreground mb-1.5 block">Time Mandante</Label>
              <TeamSelect value={homeTeamId} onValueChange={v => { setHomeTeamId(v); setProjection(null); }} teams={teams.filter(t => t !== awayTeamId)} />
            </div>
            <div>
              <Label className="text-xs text-muted-foreground mb-1.5 block">Time Visitante</Label>
              <TeamSelect value={awayTeamId} onValueChange={v => { setAwayTeamId(v); setProjection(null); }} teams={teams.filter(t => t !== homeTeamId)} />
            </div>
            <div>
              <Label className="text-xs text-muted-foreground mb-1.5 block">Competição</Label>
              <Select value={competition} onValueChange={setCompetition}>
                <SelectTrigger className="h-10"><SelectValue placeholder="Selecione..." /></SelectTrigger>
                <SelectContent>{tournaments.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs text-muted-foreground mb-1.5 block flex items-center gap-1">
                Árbitro (opcional)
                <InfoTooltip text="Você pode informar o árbitro da partida. No momento não influencia os cálculos; ficará disponível para análises futuras." />
              </Label>
              <TeamSelect value={referee} onValueChange={setReferee} teams={referees} labelFn={(s) => s} placeholder="Buscar árbitro..." searchPlaceholder="Buscar árbitro..." />
            </div>
            <div className="flex items-end pb-2">
              <div className="flex items-center gap-2">
                <Switch id="neutral" checked={neutralField} onCheckedChange={setNeutralField} />
                <Label htmlFor="neutral" className="text-sm cursor-pointer">Campo Neutro</Label>
                <InfoTooltip text="Remove a vantagem de mando de campo do modelo preditivo." />
              </div>
            </div>
          </div>
        )}
      </motion.div>
      )}

      <MatchPickerModal
        open={modalOpen}
        onOpenChange={setModalOpen}
        fixtures={upcoming}
        teamIds={teamIds}
        onSelect={(fx) => selectFutureFixture(fx.fixture_id)}
        title="Selecionar Partida Agendada"
      />

      <AnimatePresence>
        {(homeTeamId || awayTeamId) && (() => {
          const both = homeTeamId && awayTeamId && homeTeamId !== awayTeamId;
          const openMatch = (teamId: string) => (m: RecentMatch) => {
            const mh = m.is_home ? teamId : m.opponent;
            const ma = m.is_home ? m.opponent : teamId;
            router.push(`/estatisticas?home=${encodeURIComponent(mh)}&away=${encodeURIComponent(ma)}&date=${encodeURIComponent(m.date.slice(0, 10))}`);
          };
          if (both) {
            return (
              <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-stretch">
                {/* ESQUERDA: Resumo do Confronto Direto */}
                <div className="min-w-0">
                  {loadingH2H && !h2hData ? (
                    <div className="bg-card border border-border/50 rounded-xl p-5 h-full flex items-center justify-center gap-2 text-muted-foreground text-sm">
                      <div className="w-4 h-4 border-2 border-muted-foreground/30 border-t-emerald-500 rounded-full animate-spin" />
                      Buscando confronto direto…
                    </div>
                  ) : h2hData ? (
                    <H2HCard h2hData={h2hData} home={homeTeamId} away={awayTeamId} teamIds={teamIds} />
                  ) : (
                    <div className="bg-card border border-border/50 rounded-xl p-5 h-full flex items-center justify-center text-sm text-muted-foreground italic text-center">
                      Sem confrontos diretos no histórico entre as seleções.
                    </div>
                  )}
                </div>
                {/* DIREITA: equipes lado a lado (últimos 5 jogos em linhas, cards mais estreitos) */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 items-stretch">
                  <TeamRecentBlock teamId={homeTeamId} form={homeForm} anomalies={homeAnomalies} label="Mandante" loading={loadingHome} teamIds={teamIds} onOpenMatch={openMatch(homeTeamId)} />
                  <TeamRecentBlock teamId={awayTeamId} form={awayForm} anomalies={awayAnomalies} label="Visitante" loading={loadingAway} teamIds={teamIds} onOpenMatch={openMatch(awayTeamId)} />
                </div>
              </motion.div>
            );
          }
          // Só uma equipe selecionada — card único centralizado
          const s = homeTeamId
            ? { teamId: homeTeamId, form: homeForm, anomalies: homeAnomalies, label: 'Mandante', loading: loadingHome }
            : { teamId: awayTeamId, form: awayForm, anomalies: awayAnomalies, label: 'Visitante', loading: loadingAway };
          return (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="max-w-md mx-auto">
              <TeamRecentBlock teamId={s.teamId} form={s.form} anomalies={s.anomalies} label={s.label} loading={s.loading} teamIds={teamIds} onOpenMatch={openMatch(s.teamId)} />
            </motion.div>
          );
        })()}
      </AnimatePresence>

      <div className="flex flex-col items-center gap-2">
        {errMsg && (
          <div className="text-sm rounded-md bg-red-500/10 text-red-600 p-3 max-w-md text-center">
            {errMsg}{errMsg.toLowerCase().includes('insuficiente') && <> <Link href="/carteira" className="underline font-medium">Comprar créditos</Link>.</>}
          </div>
        )}
        <motion.button
          whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
          onClick={handleGenerate} disabled={!canGenerate || loading || (!!user && credits < 1)}
          className="px-8 py-3 rounded-xl font-semibold text-sm transition-all disabled:opacity-40 disabled:cursor-not-allowed bg-gradient-to-r from-emerald-500 to-cyan-500 text-white shadow-lg shadow-emerald-500/20 hover:shadow-emerald-500/30"
        >
          {loading
            ? <span className="flex items-center gap-2"><div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> Processando...</span>
            : <span className="flex items-center gap-2"><Sparkles className="w-4 h-4" /> {user ? 'Gerar análise (1 crédito)' : 'Entrar para gerar análise'}</span>}
        </motion.button>
        {user && (
          <p className="text-xs text-muted-foreground flex items-center gap-1">
            <Coins className="w-3.5 h-3.5 text-emerald-500" /> {credits} créditos · <Link href="/carteira" className="underline font-medium text-primary">Ir para a Carteira ➜</Link>
          </p>
        )}
      </div>

      <AnimatePresence>
        {projection && !loading && (
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="space-y-6">

            {/* Badge de confiabilidade do jogo (cobertura de dados refinados) */}
            {projection.confiabilidade && (
              <div className="flex justify-center">
                <MatchReliabilityBadge confiabilidade={projection.confiabilidade} />
              </div>
            )}

            {/* MERCADOS PRINCIPAIS — Resultados | Ambas Marcam / Dupla Chance | Empate Anula / Placar Exato | Handicaps */}
            <SectionDivider>MERCADOS PRINCIPAIS</SectionDivider>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-stretch">
              {/* Resultados (1X2) */}
              <div className="bg-card border border-border/50 rounded-xl p-5 flex flex-col justify-center text-center shadow-sm h-full">
                <p className="text-xs text-muted-foreground mb-4 font-semibold uppercase tracking-wider">Resultados</p>
                <div className="flex flex-wrap items-center justify-center gap-3 sm:gap-4">
                  <div className="text-center w-[30%] min-w-[82px]">
                    {teamLogoUrl(teamIds[homeTeamId]) && (
                      <img src={teamLogoUrl(teamIds[homeTeamId])!} alt="" className="w-8 h-8 mx-auto mb-1 object-contain" loading="lazy" onError={(e) => { e.currentTarget.style.display = 'none'; }} />
                    )}
                    <p className="text-sm font-medium text-foreground mb-1 truncate">{teamPt(homeTeamId)}</p>
                    <p className="text-3xl font-bold font-mono text-emerald-400">{projection.vencedor.probabilidades[homeTeamId]}%</p>
                    <p className="text-[10px] text-muted-foreground mt-1">odd justa: {oddRangeStr(projection.vencedor.probabilidades[homeTeamId])}</p>
                  </div>
                  <div className="text-center w-[30%] min-w-[82px] border-x border-border/50">
                    <p className="text-sm font-medium text-muted-foreground mb-1">Empate</p>
                    <p className="text-2xl font-bold font-mono text-muted-foreground">{projection.vencedor.probabilidades["Empate"]}%</p>
                    <p className="text-[10px] text-muted-foreground mt-1">odd justa: {oddRangeStr(projection.vencedor.probabilidades["Empate"])}</p>
                  </div>
                  <div className="text-center w-[30%] min-w-[82px]">
                    {teamLogoUrl(teamIds[awayTeamId]) && (
                      <img src={teamLogoUrl(teamIds[awayTeamId])!} alt="" className="w-8 h-8 mx-auto mb-1 object-contain" loading="lazy" onError={(e) => { e.currentTarget.style.display = 'none'; }} />
                    )}
                    <p className="text-sm font-medium text-foreground mb-1 truncate">{teamPt(awayTeamId)}</p>
                    <p className="text-3xl font-bold font-mono text-cyan-400">{projection.vencedor.probabilidades[awayTeamId]}%</p>
                    <p className="text-[10px] text-muted-foreground mt-1">odd justa: {oddRangeStr(projection.vencedor.probabilidades[awayTeamId])}</p>
                  </div>
                </div>
              </div>

              {/* Ambas Marcam (à direita de Resultados) */}
              {projection.ambas_marcam && (
                <div className="bg-card border border-border/50 rounded-xl p-5 flex flex-col h-full">
                  <h4 className="text-sm font-semibold mb-3 flex items-center justify-center gap-1.5">
                    Ambas Marcam
                    <InfoTooltip text="Probabilidade de as duas equipes marcarem pelo menos um gol na partida." href="/como-funciona#mercado-btts" />
                  </h4>
                  <div className="flex-1 flex flex-wrap items-center justify-center gap-x-6 gap-y-3 sm:gap-x-8 text-center">
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
              )}

              {/* Dupla Chance | Handicaps */}
              {projection.mercados_derivados && <DuplaChanceCard d={projection.mercados_derivados} home={homeTeamId} away={awayTeamId} />}
              {projection.mercados_derivados && <HandicapsCard d={projection.mercados_derivados} home={homeTeamId} away={awayTeamId} teamIds={teamIds} />}
              {/* Placar Exato — card detalhado em largura total */}
              {projection.placar_exato && (
                <div className="md:col-span-2">
                  <PlacarExatoCard data={projection.placar_exato} home={homeTeamId} away={awayTeamId} />
                </div>
              )}
            </div>

            {/* MERCADOS SECUNDÁRIOS — cada mercado colapsa individualmente (título sempre visível) */}
            <SectionDivider>MERCADOS SECUNDÁRIOS</SectionDivider>
            <div className="space-y-6">
              {/* Gols (mandante/total/visitante, com seletor de tempo) */}
              {projection.gols && (
                <CollapsibleMarket title="Gols" tip="Gols marcados na partida. Use o seletor de cada cartão para ver partida inteira, 1º ou 2º tempo." tipHref="/como-funciona#mercado-gols">
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                    <MarketCard title="Gols" subtitle={teamPt(homeTeamId)} periods={goalPeriods(projection, homeTeamId)} />
                    <MarketCard title="Gols" subtitle="Totais (Partida)" periods={goalPeriods(projection, 'total')} />
                    <MarketCard title="Gols" subtitle={teamPt(awayTeamId)} periods={goalPeriods(projection, awayTeamId)} />
                  </div>
                  {projection.mercados_derivados && (
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mt-4">
                      <ParImparCard d={projection.mercados_derivados} />
                      <FaixaGolsCard d={projection.mercados_derivados} />
                      <CleanSheetCard d={projection.mercados_derivados} home={homeTeamId} away={awayTeamId} />
                      <VitoriaSemSofrerCard d={projection.mercados_derivados} home={homeTeamId} away={awayTeamId} />
                    </div>
                  )}
                </CollapsibleMarket>
              )}

              {/* Finalizações */}
              {projection.chutes && (
                <CollapsibleMarket title="Finalizações" tip="Conta qualquer tentativa de marcar gol, independentemente da direção. Inclui chutes no alvo, para fora, na trave e também os bloqueados pela defesa adversária." tipHref="/como-funciona#mercado-finalizacoes">
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                    {projection.chutes_equipe && projection.chutes_equipe[homeTeamId] && (
                      <MarketCard title="Finalizações" subtitle={teamPt(homeTeamId)} prediction={projection.chutes_equipe[homeTeamId]} />
                    )}
                    <MarketCard title="Finalizações" subtitle="Totais (Partida)" prediction={projection.chutes as any} />
                    {projection.chutes_equipe && projection.chutes_equipe[awayTeamId] && (
                      <MarketCard title="Finalizações" subtitle={teamPt(awayTeamId)} prediction={projection.chutes_equipe[awayTeamId]} />
                    )}
                  </div>
                </CollapsibleMarket>
              )}

              {/* Chutes a Gol */}
              {projection.chutes_a_gol && projection.chutes_a_gol.total && (
                <CollapsibleMarket title="Chutes a Gol" tip="Considera apenas os chutes que vão na direção exata da baliza e que seriam gol se não houvesse intervenção do goleiro. Chutes na trave, para fora ou bloqueados não contam." tipHref="/como-funciona#mercado-finalizacoes-gol">
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                    <MarketCard title="Chutes a Gol" subtitle={teamPt(homeTeamId)} prediction={projection.chutes_a_gol[homeTeamId]} />
                    <MarketCard title="Chutes a Gol" subtitle="Totais (Partida)" prediction={projection.chutes_a_gol.total} />
                    <MarketCard title="Chutes a Gol" subtitle={teamPt(awayTeamId)} prediction={projection.chutes_a_gol[awayTeamId]} />
                  </div>
                </CollapsibleMarket>
              )}

              {/* Escanteios */}
              {projection.escanteios && projection.escanteios.total && (
                <CollapsibleMarket title="Escanteios" tip="Soma dos tiros de canto efetivamente cobrados durante a partida. Escanteios assinalados pelo árbitro, mas não cobrados antes do apito final, geralmente não entram na conta." tipHref="/como-funciona#mercado-escanteios">
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                    <MarketCard title="Escanteios" subtitle={teamPt(homeTeamId)} prediction={projection.escanteios[homeTeamId]} />
                    <MarketCard title="Escanteios" subtitle="Totais (Partida)" prediction={projection.escanteios.total} />
                    <MarketCard title="Escanteios" subtitle={teamPt(awayTeamId)} prediction={projection.escanteios[awayTeamId]} />
                  </div>
                </CollapsibleMarket>
              )}

              {/* Cartões (com seletor de tempo) */}
              {projection.cartoes && projection.cartoes.total && (
                <CollapsibleMarket title="Cartões" tip="Contagem de cartões amarelos e vermelhos aplicados aos jogadores ativos em campo. Cartões mostrados para jogadores no banco de reservas ou para a comissão técnica não são contabilizados." tipHref="/como-funciona#mercado-cartoes">
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                    <MarketCard title="Cartões" subtitle={teamPt(homeTeamId)} periods={cardPeriods(projection, homeTeamId)} />
                    <MarketCard title="Cartões" subtitle="Totais (Partida)" periods={cardPeriods(projection, 'total')} />
                    <MarketCard title="Cartões" subtitle={teamPt(awayTeamId)} periods={cardPeriods(projection, awayTeamId)} />
                  </div>
                </CollapsibleMarket>
              )}

              {/* Impedimentos (mercado novo, exibido cru) */}
              {projection.impedimentos && projection.impedimentos.total && (
                <CollapsibleMarket title="Impedimentos" tip="Total de impedimentos assinalados na partida.">
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                    <MarketCard title="Impedimentos" subtitle={teamPt(homeTeamId)} prediction={projection.impedimentos[homeTeamId]} />
                    <MarketCard title="Impedimentos" subtitle="Totais (Partida)" prediction={projection.impedimentos.total} />
                    <MarketCard title="Impedimentos" subtitle={teamPt(awayTeamId)} prediction={projection.impedimentos[awayTeamId]} />
                  </div>
                </CollapsibleMarket>
              )}

              {/* Jogador — modelo de goleador (dentro dos secundários, colapso individual) */}
              {scorers?.disponivel && (
                <CollapsibleMarket title="Jogador a Marcar" tip="Probabilidade de cada jogador marcar a qualquer momento, se jogar (modelo de goleador: forma recente + defesa do adversário + mando). Candidatos = elenco recente da seleção; refina com a escalação confirmada. Odd justa = 1/probabilidade, sem margem de casa.">
                  <ScorersCard data={scorers} home={homeTeamId} away={awayTeamId} teamIds={teamIds} embedded />
                </CollapsibleMarket>
              )}
            </div>

            {/* FUNÇÕES AVANÇADAS DE ANÁLISE (acima do Monte sua Aposta, abaixo dos secundários) */}
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
                  <BetLab prediction={projection} />
                </motion.div>
              )}
            </AnimatePresence>

            {/* MONTE SUA APOSTA — oferta "ParcerIA" (Só Paga se Acertar) */}
            <SectionDivider>MONTE SUA APOSTA</SectionDivider>
            {analysis?.type === 'future_match' ? (
              <div className="max-w-3xl mx-auto mb-2">
                <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-4 mb-4 text-sm text-muted-foreground leading-relaxed">
                  <p className="mb-2">
                    <b className="text-foreground">Como funciona:</b> esta é uma <b>partida agendada</b>, então você tem <b>1 crédito
                    reservado</b> para montar uma aposta na oferta <b>&quot;ParcerIA&quot;</b>.
                  </p>
                  <p className="mb-2">
                    Escolha abaixo alguns palpites desta análise — por exemplo, <i>{teamPt(homeTeamId)} não perde</i> combinado com
                    <i> mais de 2,5 gols</i>. O sistema junta tudo numa aposta única com odd de até 2,00. <b>Se acertar, o crédito é
                    usado normalmente; se errar, ele volta para a sua conta</b> — por isso o nome &quot;só paga se acertar&quot;.
                  </p>
                  <Link href="/como-funciona#promocao" className="text-primary font-medium inline-flex items-center gap-1">
                    Ver a explicação completa da oferta ParcerIA →
                  </Link>
                </div>
                <BetBuilder analysisId={analysis.id} home={homeTeamId} away={awayTeamId} onConfirmed={() => refreshWallet()} />
              </div>
            ) : (
              <p className="text-sm text-muted-foreground text-center max-w-2xl mx-auto">
                A oferta <b>&quot;ParcerIA&quot;</b> (só paga se acertar) vale apenas para <b>análises de partidas agendadas</b>. Esta é
                uma <b>análise independente</b>, então não é elegível.{' '}
                <Link href="/como-funciona#promocao" className="text-primary font-medium">Saiba mais</Link>.
              </p>
            )}

          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
