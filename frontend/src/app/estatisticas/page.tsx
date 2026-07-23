"use client";
import React, { useState, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { motion } from 'framer-motion';
import { Label } from '@/components/ui/label';
import { BarChart3, TrendingUp, Target, Activity, Gauge } from 'lucide-react';
import { BarChart, Bar, LineChart, Line, ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip as RTooltip, Legend, ResponsiveContainer, ReferenceLine, ReferenceArea } from 'recharts';
import { api, TeamHistoryResponse, H2HResponse, MatchDetail as MatchDetailT } from '@/lib/api';
import InfoTooltip from '@/components/platform/InfoTooltip';
import { usePrediction } from '@/lib/PredictionContext';
import { TeamSelect } from '@/components/platform/TeamSelect';
import { teamPt } from '@/lib/teamNames';
import { MatchDetail } from '@/components/platform/MatchDetail';
import { MatchModePicker } from '@/components/platform/MatchModePicker';
import { MatchHeader } from '@/components/platform/MatchHeader';
import { useAuth } from '@/lib/AuthContext';
import { ArrowLeft, Sparkles, Lock } from 'lucide-react';
import StyleRadar from '@/components/platform/StyleRadar';
import DestaquesRecentes from '@/components/platform/DestaquesRecentes';
import H2HCard from '@/components/platform/H2HCard';
import GoalTiming from '@/components/platform/GoalTiming';
import FatorArbitro from '@/components/platform/FatorArbitro';
import BoletimDesfalques from '@/components/platform/BoletimDesfalques';
import KeyPlayerMatchup from '@/components/platform/KeyPlayerMatchup';
import PmfPreview from '@/components/platform/PmfPreview';
import AutoInsights from '@/components/platform/AutoInsights';
import StyleMatchup from '@/components/platform/StyleMatchup';
import DeepStats from '@/components/platform/DeepStats';
import type { RecentMatch, GoalTimingResponse, InjuriesResponse, ScorersResponse, PmfPreviewResponse, CompetitionBenchmarkResponse } from '@/lib/api';

export default function Estatisticas() {
  const { homeTeamId, setHomeTeamId, awayTeamId, setAwayTeamId, competition, neutralField, analysis, scope } = usePrediction();
  const { user } = useAuth();
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  
  const [homeHistory, setHomeHistory] = useState<TeamHistoryResponse | null>(null);
  const [awayHistory, setAwayHistory] = useState<TeamHistoryResponse | null>(null);
  const [h2h, setH2h] = useState<H2HResponse | null>(null);
  const [homeRecent, setHomeRecent] = useState<RecentMatch[]>([]);
  const [awayRecent, setAwayRecent] = useState<RecentMatch[]>([]);
  const [homeTiming, setHomeTiming] = useState<GoalTimingResponse | null>(null);
  const [awayTiming, setAwayTiming] = useState<GoalTimingResponse | null>(null);
  const [homeInjuries, setHomeInjuries] = useState<InjuriesResponse | null>(null);
  const [awayInjuries, setAwayInjuries] = useState<InjuriesResponse | null>(null);
  const [scorers, setScorers] = useState<ScorersResponse | null>(null);
  const [pmf, setPmf] = useState<PmfPreviewResponse | null>(null);
  const [benchmark, setBenchmark] = useState<CompetitionBenchmarkResponse | null>(null);

  // Detalhe de uma partida específica (via ?home=&away=&date= ou seletor de passadas).
  const [matchParams, setMatchParams] = useState<{ home: string; away: string; date: string } | null>(null);
  const [matchData, setMatchData] = useState<MatchDetailT | null>(null);
  const [matchLoading, setMatchLoading] = useState(false);
  const [pickerMode, setPickerMode] = useState<'futura' | 'passada' | 'independente'>('independente');
  const [teamIds, setTeamIds] = useState<Record<string, number>>({});
  const [matchDate, setMatchDate] = useState<string | undefined>(undefined);
  // Com as duas equipes escolhidas, o card de Configuração recolhe (só o título);
  // "Alterar Confronto" (no cabeçalho flutuante) reabre para trocar — mesmo padrão da Análise.
  const [editingMatch, setEditingMatch] = useState(false);

  const openMatch = (home: string, away: string, date: string) => {
    setMatchParams({ home, away, date });
    setMatchLoading(true);
    api.matchDetail(home, away, date).then(setMatchData).catch(() => setMatchData({ found: false })).finally(() => setMatchLoading(false));
  };

  React.useEffect(() => {
    Promise.all([api.teamIds("selecao"), api.teamIds("clube")])
      .then(([sel, clu]) => setTeamIds({ ...sel, ...clu })).catch(() => {});
    const sp = new URLSearchParams(window.location.search);
    const home = sp.get('home'), away = sp.get('away'), date = sp.get('date');
    if (home && away && date) openMatch(home, away, date);
  }, []);

  const clearMatch = () => {
    setMatchParams(null);
    setMatchData(null);
    window.history.replaceState(null, '', '/estatisticas');
  };

  // Volta para a página Análise. Se não houver uma análise em andamento, pré-seleciona
  // a partida que estava sendo vista; se houver, mantém a análise persistida.
  const backToAnalise = () => {
    if (!analysis && matchParams) {
      setHomeTeamId(matchParams.home);
      setAwayTeamId(matchParams.away);
    }
    router.push('/');
  };

  const bothSelected = homeTeamId && awayTeamId && homeTeamId !== awayTeamId;

  React.useEffect(() => {
    if (bothSelected) {
      setLoading(true);
      Promise.all([
        api.teamHistory(homeTeamId, scope).catch(() => null),
        api.teamHistory(awayTeamId, scope).catch(() => null),
        api.h2h(homeTeamId, awayTeamId, scope).catch(() => null),
        api.recentMatches(homeTeamId, scope).catch(() => null),
        api.recentMatches(awayTeamId, scope).catch(() => null),
        api.goalTiming(homeTeamId, scope).catch(() => null),
        api.goalTiming(awayTeamId, scope).catch(() => null),
        api.competitionBenchmark(competition || 'Copa do Mundo', scope).catch(() => null),
      ]).then(([hHist, aHist, h2hData, hRec, aRec, hTim, aTim, bench]) => {
        setHomeHistory(hHist);
        setAwayHistory(aHist);
        setH2h(h2hData);
        setHomeRecent(hRec?.matches || []);
        setAwayRecent(aRec?.matches || []);
        setHomeTiming(hTim);
        setAwayTiming(aTim);
        setBenchmark(bench);
        setLoading(false);
      }).catch(err => {
        console.error(err);
        setLoading(false);
      });
    }
  }, [homeTeamId, awayTeamId, bothSelected, competition, scope]);

  // Desfalques só no modo Partida Futura (consulta à API com cache diário — evita
  // gastar cota em análises independentes).
  React.useEffect(() => {
    if (!bothSelected || pickerMode !== 'futura') {
      setHomeInjuries(null); setAwayInjuries(null); setScorers(null); setPmf(null);
      return;
    }
    api.injuries(homeTeamId, scope).then(setHomeInjuries).catch(() => setHomeInjuries(null));
    api.injuries(awayTeamId, scope).then(setAwayInjuries).catch(() => setAwayInjuries(null));
    api.scorers(homeTeamId, awayTeamId, scope).then(setScorers).catch(() => setScorers(null));
    api.pmfPreview(homeTeamId, awayTeamId, !!neutralField, competition || 'Copa do Mundo', scope).then(setPmf).catch(() => setPmf(null));
  }, [homeTeamId, awayTeamId, bothSelected, pickerMode, neutralField, competition, scope]);

  // Tendência de gols marcados nos últimos jogos, alinhada por "jogos atrás" (J-N),
  // já que cada seleção tem datas próprias. Compara ataque recente das duas.
  const goalTrendData = useMemo(() => {
    const h = homeHistory?.goal_trend || [];
    const a = awayHistory?.goal_trend || [];
    const n = Math.max(h.length, a.length);
    if (n === 0) return [];
    const rows = [];
    for (let i = 0; i < n; i++) {
      const hi = h.length - n + i;
      const ai = a.length - n + i;
      rows.push({
        jogo: `J-${n - i}`,
        [homeTeamId]: hi >= 0 ? h[hi].scored : null,
        [awayTeamId]: ai >= 0 ? a[ai].scored : null,
      });
    }
    return rows;
  }, [homeHistory, awayHistory, homeTeamId, awayTeamId]);

  // Quadrantes: domínios + zonas (melhor/pior) + cardume da competição, a partir do
  // benchmark (média±desvio de ataque/defesa das seleções da competição analisada).
  const quadrant = useMemo(() => {
    const ha = homeHistory?.attack_avg || 0, hd = homeHistory?.defense_avg || 0;
    const aa = awayHistory?.attack_avg || 0, ad = awayHistory?.defense_avg || 0;
    const am = benchmark?.attack_mean ?? 1.3, dm = benchmark?.defense_mean ?? 1.3;
    const asd = benchmark?.attack_std ?? 0.4, dsd = benchmark?.defense_std ?? 0.4;
    const xMax = Math.max(ha, aa, am + asd, 2.5) * 1.1;
    const yMax = Math.max(hd, ad, dm + dsd, 2.5) * 1.1;
    return {
      xMax: Math.ceil(xMax * 10) / 10, yMax: Math.ceil(yMax * 10) / 10,
      am, dm,
      // cardume (média ± 1 desvio), limitado ao domínio
      cx1: Math.max(0, am - asd), cx2: am + asd,
      cy1: Math.max(0, dm - dsd), cy2: dm + dsd,
    };
  }, [homeHistory, awayHistory, benchmark]);

  const teamRankings = useMemo(() => {
    const showRanking = !!benchmark && benchmark.scope === 'competition' && !!benchmark.team_stats && benchmark.n_teams >= 3;
    let homeAtkRank = "-";
    let homeDefRank = "-";
    let awayAtkRank = "-";
    let awayDefRank = "-";

    if (showRanking && benchmark?.team_stats) {
      const stats = benchmark.team_stats;
      const teams = Object.keys(stats);
      const sortedByAtk = [...teams].sort((a, b) => (stats[b].attack || 0) - (stats[a].attack || 0));
      const sortedByDef = [...teams].sort((a, b) => (stats[a].defense || 0) - (stats[b].defense || 0));
      
      const hIdxAtk = sortedByAtk.indexOf(homeTeamId);
      const hIdxDef = sortedByDef.indexOf(homeTeamId);
      const aIdxAtk = sortedByAtk.indexOf(awayTeamId);
      const aIdxDef = sortedByDef.indexOf(awayTeamId);
      
      if (hIdxAtk !== -1) homeAtkRank = `${hIdxAtk + 1}º`;
      if (hIdxDef !== -1) homeDefRank = `${hIdxDef + 1}º`;
      if (aIdxAtk !== -1) awayAtkRank = `${aIdxAtk + 1}º`;
      if (aIdxDef !== -1) awayDefRank = `${aIdxDef + 1}º`;
    }
    return { showRanking, homeAtkRank, homeDefRank, awayAtkRank, awayDefRank };
  }, [benchmark, homeTeamId, awayTeamId]);

  const eloHistoryData = useMemo(() => {
    const hElo = homeHistory?.elo_history || [];
    const aElo = awayHistory?.elo_history || [];
    if (hElo.length === 0 && aElo.length === 0) return [];
    try {
      // "date" no formato mensal "AAAA-MM" (scripts/build_elo_history.py).
      const months = Array.from(new Set([
        ...hElo.map(e => e.date),
        ...aElo.map(e => e.date)
      ])).sort();

      return months.map(m => {
        const hPoint = hElo.find(e => e.date === m);
        const aPoint = aElo.find(e => e.date === m);
        return {
          month: m,
          [homeTeamId]: hPoint ? hPoint.elo : null,
          [awayTeamId]: aPoint ? aPoint.elo : null
        };
      });
    } catch (e) {
      console.error("Error formatting elo history", e);
      return [];
    }
  }, [homeHistory, awayHistory, homeTeamId, awayTeamId]);

  const cornersChartData = useMemo(() => {
    const hFreq = homeHistory?.corners_freq || [];
    const aFreq = awayHistory?.corners_freq || [];
    const allLabels = Array.from(new Set([...hFreq.map(x => x.label), ...aFreq.map(x => x.label)]))
      .sort((a, b) => Number(a) - Number(b));
    return allLabels.map(lbl => ({
      value: lbl,
      [homeTeamId]: hFreq.find(x => x.label === lbl)?.frequency || 0,
      [awayTeamId]: aFreq.find(x => x.label === lbl)?.frequency || 0,
    }));
  }, [homeHistory, awayHistory, homeTeamId, awayTeamId]);

  const cardsChartData = useMemo(() => {
    const hFreq = homeHistory?.cards_freq || [];
    const aFreq = awayHistory?.cards_freq || [];
    const allLabels = Array.from(new Set([...hFreq.map(x => x.label), ...aFreq.map(x => x.label)]))
      .sort((a, b) => Number(a) - Number(b));
    return allLabels.map(lbl => ({
      value: lbl,
      [homeTeamId]: hFreq.find(x => x.label === lbl)?.frequency || 0,
      [awayTeamId]: aFreq.find(x => x.label === lbl)?.frequency || 0,
    }));
  }, [homeHistory, awayHistory, homeTeamId, awayTeamId]);

  const matrixWinnerLegend = useMemo(() => {
    if (!homeHistory || !awayHistory || !homeTeamId || !awayTeamId) return "";
    const hAtk = homeHistory.attack_avg || 0, hDef = homeHistory.defense_avg || 0;
    const aAtk = awayHistory.attack_avg || 0, aDef = awayHistory.defense_avg || 0;
    const hScore = hAtk - hDef;
    const aScore = aAtk - aDef;
    const best = hScore >= aScore ? teamPt(homeTeamId) : teamPt(awayTeamId);
    const other = hScore >= aScore ? teamPt(awayTeamId) : teamPt(homeTeamId);
    return `* A equipe ${best} apresenta melhor resultado na matriz que a equipe ${other}, equilibrando melhor um ataque eficiente com uma defesa mais sólida.`;
  }, [homeHistory, awayHistory, homeTeamId, awayTeamId]);

  // "AAAA-MM" -> "MM/AA" p/ eixo do gráfico de Elo.
  const fmtEloMonth = (m: string) => {
    const [y, mo] = (m || '').split('-');
    return y && mo ? `${mo}/${y.slice(2)}` : m;
  };

  // Modo "detalhe de partida": acionado ao clicar num jogo recente (Previsões).
  if (matchParams) {
    return (
      <div className="space-y-6">
        <MatchHeader home={matchParams.home} away={matchParams.away} teamIds={teamIds} date={matchParams.date} onEditTeams={clearMatch} />
        <button onClick={backToAnalise} className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors">
          <ArrowLeft className="w-4 h-4" /> Voltar para a página de estatísticas
        </button>
        {matchLoading ? (
          <div className="flex justify-center py-12">
            <div className="w-8 h-8 border-4 border-slate-200 border-t-cyan-500 rounded-full animate-spin"></div>
          </div>
        ) : matchData ? (
          <MatchDetail data={matchData} fallback={matchParams ? { ...matchParams, teamIds } : undefined} />
        ) : null}
      </div>
    );
  }

  return (
    <div className="space-y-6 pb-20">
      {/* CABCALHO FLUTUANTE DA PARTIDA */}
      <MatchHeader home={homeTeamId} away={awayTeamId} teamIds={teamIds} competition={competition} neutral={neutralField} onEditTeams={() => setEditingMatch(true)} />

      {/* SELETOR / CONFIGURAÇÃO DO CONFRONTO (Recolhe quando ambas estão preenchidas; "Alterar Confronto" reabre) */}
      {(editingMatch || !bothSelected) && (
        <div className="bg-card border border-border/50 rounded-xl p-5 shadow-sm space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold uppercase tracking-wider text-muted-foreground">Configurar Confronto</h2>
            {bothSelected && (
              <button onClick={() => setEditingMatch(false)} className="text-xs text-cyan-400 hover:underline">
                Concluir edição
              </button>
            )}
          </div>
          <MatchModePicker
            onModeChange={(m) => { setPickerMode(m); clearMatch(); }}
            onSelectFuture={(fx) => { setMatchDate(fx.date); setEditingMatch(false); }}
            onSelectPast={(fx) => openMatch(fx.home, fx.away, (fx.date || '').slice(0, 10))}
          />
          {pickerMode === 'independente' && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <Label className="text-xs text-muted-foreground mb-1 block">Mandante</Label>
                <TeamSelect value={homeTeamId} onValueChange={setHomeTeamId} teams={[]} placeholder="Selecione o mandante..." searchPlaceholder="Buscar mandante..." />
              </div>
              <div>
                <Label className="text-xs text-muted-foreground mb-1 block">Visitante</Label>
                <TeamSelect value={awayTeamId} onValueChange={setAwayTeamId} teams={[]} placeholder="Selecione o visitante..." searchPlaceholder="Buscar visitante..." />
              </div>
            </div>
          )}
        </div>
      )}

      {bothSelected && loading && (
        <div className="flex justify-center py-12">
          <div className="w-8 h-8 border-4 border-slate-200 border-t-cyan-500 rounded-full animate-spin"></div>
        </div>
      )}

      {bothSelected && !loading && homeHistory && awayHistory && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.4 }}
          className="space-y-6"
        >
          {/* SEÇÃO TOPO: Confronto direto + Radar de Estilo */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-stretch">
            <div className="lg:col-span-7">
              <H2HCard h2hData={h2h?.metrics} home={homeTeamId} away={awayTeamId} teamIds={teamIds} />
            </div>
            <div className="lg:col-span-5">
              <StyleRadar home={homeTeamId} away={awayTeamId} homeMatches={homeRecent} awayMatches={awayRecent} targetCompetition={competition} />
            </div>
          </div>

          {/* USUÁRIO LOGADO: Exibe todas as estatísticas avançadas */}
          {user ? (
            <>
              {/* SEÇÃO INTERMEDIÁRIA: Confronto de Estilos + Posição na Competição + Principais Conclusões */}
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-stretch">
                <div className="lg:col-span-4">
                  <StyleMatchup home={homeTeamId} away={awayTeamId} homeMatches={homeRecent} awayMatches={awayRecent} targetCompetition={competition} />
                </div>
                
                {/* Posição na Competição com design idêntico ao de Confronto de Estilos */}
                <div className="lg:col-span-3">
                  {teamRankings.showRanking ? (
                    <div className="bg-card border border-border/50 rounded-xl p-5 h-full flex flex-col justify-between">
                      <div>
                        <h3 className="text-sm font-semibold mb-3 flex items-center gap-1.5">
                          <Gauge className="w-4 h-4 text-cyan-500" />
                          Posição na Competição
                          <InfoTooltip text={`Ranking entre as ${benchmark!.n_teams} equipes da competição, baseado nas médias reais de gols marcados (Ataque) e sofridos (Defesa).`} />
                        </h3>
                        
                        <div className="grid grid-cols-3 gap-2.5 text-center text-xs mt-3">
                          {/* Header Row */}
                          <div className="text-left font-semibold text-muted-foreground flex items-center">Equipe</div>
                          <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400 font-bold border border-emerald-500/15">Ataque</div>
                          <div className="p-2 rounded-lg bg-orange-500/10 text-orange-400 font-bold border border-orange-500/15">Defesa</div>
                          
                          {/* Row 1: Home */}
                          <div className="text-left font-semibold flex items-center truncate text-[11.5px] py-1">{teamPt(homeTeamId)}</div>
                          <div className="p-3 rounded-xl bg-muted/30 font-mono text-xs font-bold flex flex-col items-center justify-center border border-border/20 shadow-sm">
                            <span className="text-sm text-emerald-400 font-bold">{teamRankings.homeAtkRank} / {benchmark!.n_teams}</span>
                            <span className="text-[8px] text-muted-foreground mt-0.5 uppercase tracking-wider">Ataque</span>
                          </div>
                          <div className="p-3 rounded-xl bg-muted/30 font-mono text-xs font-bold flex flex-col items-center justify-center border border-border/20 shadow-sm">
                            <span className="text-sm text-orange-400 font-bold">{teamRankings.homeDefRank} / {benchmark!.n_teams}</span>
                            <span className="text-[8px] text-muted-foreground mt-0.5 uppercase tracking-wider">Defesa</span>
                          </div>
                          
                          {/* Row 2: Away */}
                          <div className="text-left font-semibold flex items-center truncate text-[11.5px] py-1">{teamPt(awayTeamId)}</div>
                          <div className="p-3 rounded-xl bg-muted/30 font-mono text-xs font-bold flex flex-col items-center justify-center border border-border/20 shadow-sm">
                            <span className="text-sm text-emerald-400 font-bold">{teamRankings.awayAtkRank} / {benchmark!.n_teams}</span>
                            <span className="text-[8px] text-muted-foreground mt-0.5 uppercase tracking-wider">Ataque</span>
                          </div>
                          <div className="p-3 rounded-xl bg-muted/30 font-mono text-xs font-bold flex flex-col items-center justify-center border border-border/20 shadow-sm">
                            <span className="text-sm text-orange-400 font-bold">{teamRankings.awayDefRank} / {benchmark!.n_teams}</span>
                            <span className="text-[8px] text-muted-foreground mt-0.5 uppercase tracking-wider">Defesa</span>
                          </div>
                        </div>
                      </div>
                      
                      <p className="text-[9.5px] text-muted-foreground leading-normal mt-4 pt-3 border-t border-border/25">
                        * Competição analisada: {competition || "Geral"}
                      </p>
                    </div>
                  ) : (
                    <div className="bg-card border border-border/50 rounded-xl p-5 h-full flex flex-col justify-center items-center text-center text-xs text-muted-foreground">
                      <Gauge className="w-6 h-6 text-muted-foreground/40 mb-2" />
                      Ranking indisponível para esta competição.
                    </div>
                  )}
                </div>

                <div className="lg:col-span-5">
                  <AutoInsights home={homeTeamId} away={awayTeamId} homeMatches={homeRecent} awayMatches={awayRecent} homeTiming={homeTiming} awayTiming={awayTiming} targetCompetition={competition} />
                </div>
              </div>

              {/* SEÇÃO INFERIOR: DestaquesRecentes, Minutagem e DeepStats */}
              <DestaquesRecentes home={homeTeamId} away={awayTeamId} homeMatches={homeRecent} awayMatches={awayRecent} teamIds={teamIds} />

              <GoalTiming home={homeTeamId} homeData={homeTiming} away={awayTeamId} awayData={awayTiming} />

              <DeepStats home={homeTeamId} away={awayTeamId} homeMatches={homeRecent} awayMatches={awayRecent} homeHistory={homeHistory} awayHistory={awayHistory} benchmark={benchmark} targetCompetition={competition} />

              {/* Central Pré-Jogo (só Partida Futura) */}
              {pickerMode === 'futura' && (
                <>
                  <PmfPreview data={pmf} />
                  <KeyPlayerMatchup data={scorers} home={homeTeamId} away={awayTeamId} teamIds={teamIds} />
                  <BoletimDesfalques home={homeInjuries} away={awayInjuries} />
                  <FatorArbitro />
                </>
              )}

              {/* Tendência de Gols (últimos jogos) */}
              <div className="bg-card border border-border/50 rounded-xl p-5">
                <h3 className="text-sm font-semibold mb-1 flex items-center gap-1.5">
                  <TrendingUp className="w-4 h-4 text-emerald-500" />
                  Tendência de Gols Marcados
                  <InfoTooltip text="Gols marcados por cada seleção nos jogos recentes, alinhados por 'jogos atrás' (J-1 é o mais recente). Compara a fase ofensiva das duas." />
                </h3>
                <p className="text-xs text-muted-foreground mb-4">Gols marcados nos últimos jogos de cada seleção</p>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={goalTrendData} margin={{ top: 5, right: 20, bottom: 24, left: 8 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.5} />
                      <XAxis dataKey="jogo" tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }}
                        label={{ value: 'Jogos atrás (J-1 = mais recente)', position: 'insideBottom', offset: -12, style: { fontSize: 10, fill: 'hsl(var(--muted-foreground))' } }} />
                      <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }}
                        label={{ value: 'Gols marcados', angle: -90, position: 'insideLeft', style: { fontSize: 10, fill: 'hsl(var(--muted-foreground))', textAnchor: 'middle' } }} />
                      <RTooltip
                        contentStyle={{ backgroundColor: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: '8px', fontSize: '12px' }}
                        labelStyle={{ color: 'hsl(var(--foreground))' }}
                      />
                      <Legend verticalAlign="top" height={28} wrapperStyle={{ fontSize: '12px' }} />
                      <Line type="monotone" dataKey={homeTeamId} name={teamPt(homeTeamId)} stroke="#10b981" strokeWidth={2} dot={{ r: 3 }} connectNulls />
                      <Line type="monotone" dataKey={awayTeamId} name={teamPt(awayTeamId)} stroke="#f97316" strokeWidth={2} dot={{ r: 3 }} connectNulls />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {/* Evolução de Elo com Link explicativo */}
              {eloHistoryData.length > 1 && (
                <div className="bg-card border border-border/50 rounded-xl p-5">
                  <h3 className="text-sm font-semibold mb-1 flex items-center gap-1.5">
                    <Activity className="w-4 h-4 text-cyan-500" />
                    Evolução de Elo
                    <InfoTooltip
                      text="Rating Elo histórico de cada equipe. Mostra a variação de patamar de força ao longo do tempo."
                      href="https://ge.globo.com/futebol/selecao-brasileira/noticia/entenda-como-funciona-o-novo-ranking-da-fifa-baseado-no-metodo-elo.ghtml"
                      linkText="Elo? O que é isso? Saiba mais ->"
                    />
                  </h3>
                  <p className="text-xs text-muted-foreground mb-4">Rating Elo mensal ao longo do tempo</p>
                  <div className="h-64">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={eloHistoryData} margin={{ top: 5, right: 20, bottom: 24, left: 8 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.5} />
                        <XAxis dataKey="month" tickFormatter={fmtEloMonth} tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} />
                        <YAxis domain={['auto', 'auto']} tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }}
                          label={{ value: 'Elo', angle: -90, position: 'insideLeft', style: { fontSize: 10, fill: 'hsl(var(--muted-foreground))', textAnchor: 'middle' } }} />
                        <RTooltip
                          contentStyle={{ backgroundColor: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: '8px', fontSize: '12px' }}
                          labelStyle={{ color: 'hsl(var(--foreground))' }}
                        />
                        <Legend verticalAlign="top" height={28} wrapperStyle={{ fontSize: '12px' }} />
                        <Line type="monotone" dataKey={homeTeamId} name={teamPt(homeTeamId)} stroke="#10b981" strokeWidth={2} dot={false} connectNulls />
                        <Line type="monotone" dataKey={awayTeamId} name={teamPt(awayTeamId)} stroke="#f97316" strokeWidth={2} dot={false} connectNulls />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              )}

              {/* Scatter Plot com Legenda Explicativa do Vencedor */}
              <div className="bg-card border border-border/50 rounded-xl p-5">
                <h3 className="text-sm font-semibold mb-1 flex items-center gap-1.5">
                  <Target className="w-4 h-4 text-amber-500" />
                  Matriz Comparativa de Quadrantes
                  <InfoTooltip text="Ataque (gols/jogo, eixo X) vs defesa (gols sofridos/jogo, eixo Y). A zona VERDE (direita-baixo) é a ideal: marca muito e sofre pouco; a VERMELHA (esquerda-cima) é a pior." />
                </h3>
                <p className="text-xs text-muted-foreground mb-4">
                  Ataque vs Defesa — média de gols nos últimos 20 jogos
                  {benchmark?.scope === 'competition' && <span> · faixa típica de {benchmark.n_teams} seleções da competição</span>}
                </p>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <ScatterChart margin={{ top: 8, right: 24, bottom: 28, left: 16 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.4} />
                      <XAxis type="number" dataKey="attack" name="Ataque" domain={[0, quadrant.xMax]} tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} label={{ value: 'Ataque (gols/jogo) →', position: 'insideBottom', offset: -8, style: { fontSize: 10, fill: 'hsl(var(--muted-foreground))', textAnchor: 'middle' } }} />
                      <YAxis type="number" dataKey="defense" name="Defesa" domain={[0, quadrant.yMax]} tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} label={{ value: '← Defesa (gols sofridos/jogo)', angle: -90, position: 'insideLeft', offset: 6, style: { fontSize: 10, fill: 'hsl(var(--muted-foreground))', textAnchor: 'middle' } }} />
                      <ReferenceArea x1={quadrant.am} x2={quadrant.xMax} y1={0} y2={quadrant.dm} fill="#10b981" fillOpacity={0.10} ifOverflow="hidden" />
                      <ReferenceArea x1={0} x2={quadrant.am} y1={quadrant.dm} y2={quadrant.yMax} fill="#ef4444" fillOpacity={0.10} ifOverflow="hidden" />
                      <ReferenceArea x1={quadrant.cx1} x2={quadrant.cx2} y1={quadrant.cy1} y2={quadrant.cy2} fill="hsl(var(--muted-foreground))" fillOpacity={0.12} stroke="hsl(var(--muted-foreground))" strokeOpacity={0.5} strokeDasharray="4 3" ifOverflow="hidden" />
                      <ReferenceLine x={quadrant.am} stroke="hsl(var(--muted-foreground))" strokeOpacity={0.4} strokeDasharray="2 4" />
                      <ReferenceLine y={quadrant.dm} stroke="hsl(var(--muted-foreground))" strokeOpacity={0.4} strokeDasharray="2 4" />
                      <RTooltip
                        contentStyle={{ backgroundColor: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: '8px', fontSize: '12px' }}
                        formatter={(value: any, name: any) => [Number(value).toFixed(2), name === 'Ataque' ? 'Ataque (gols/jogo)' : 'Defesa (sofridos/jogo)']}
                      />
                      <Legend verticalAlign="top" height={28} wrapperStyle={{ fontSize: '12px' }} />
                      <Scatter name={teamPt(homeTeamId)} data={[{ attack: homeHistory.attack_avg || 0, defense: homeHistory.defense_avg || 0 }]} fill="#10b981" />
                      <Scatter name={teamPt(awayTeamId)} data={[{ attack: awayHistory.attack_avg || 0, defense: awayHistory.defense_avg || 0 }]} fill="#f97316" />
                    </ScatterChart>
                  </ResponsiveContainer>
                </div>
                {matrixWinnerLegend && (
                  <p className="text-[10.5px] text-muted-foreground mt-3 pt-2.5 border-t border-border/25 leading-normal">
                    {matrixWinnerLegend}
                  </p>
                )}
              </div>

              {/* Frequency Distributions */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="bg-card border border-border/50 rounded-xl p-5">
                  <h3 className="text-sm font-semibold mb-1 flex items-center gap-1.5">
                    Distribuição de Escanteios
                    <InfoTooltip text="Frequência histórica de escanteios nos últimos 20 jogos de cada equipe." />
                  </h3>
                  <p className="text-xs text-muted-foreground mb-4">Últimos 20 jogos</p>
                  <div className="h-48">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart margin={{ top: 5, right: 8, bottom: 22, left: 4 }} data={cornersChartData}>
                        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.5} />
                        <XAxis dataKey="value" tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }} label={{ value: 'Escanteios na partida', position: 'insideBottom', offset: -10, style: { fontSize: 9, fill: 'hsl(var(--muted-foreground))' } }} />
                        <YAxis allowDecimals={false} tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }} label={{ value: 'Nº de jogos', angle: -90, position: 'insideLeft', style: { fontSize: 9, fill: 'hsl(var(--muted-foreground))', textAnchor: 'middle' } }} />
                        <RTooltip contentStyle={{ backgroundColor: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: '8px', fontSize: '11px' }} />
                        <Legend verticalAlign="top" height={26} wrapperStyle={{ fontSize: '11px' }} />
                        <Bar dataKey={homeTeamId} name={teamPt(homeTeamId)} fill="#10b981" radius={[2, 2, 0, 0]} />
                        <Bar dataKey={awayTeamId} name={teamPt(awayTeamId)} fill="#f97316" radius={[2, 2, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                <div className="bg-card border border-border/50 rounded-xl p-5">
                  <h3 className="text-sm font-semibold mb-1 flex items-center gap-1.5">
                    Distribuição de Cartões
                    <InfoTooltip text="Frequência histórica de cartões nos últimos 20 jogos de cada equipe." />
                  </h3>
                  <p className="text-xs text-muted-foreground mb-4">Últimos 20 jogos</p>
                  <div className="h-48">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart margin={{ top: 5, right: 8, bottom: 22, left: 4 }} data={cardsChartData}>
                        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.5} />
                        <XAxis dataKey="value" tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }} label={{ value: 'Cartões na partida', position: 'insideBottom', offset: -10, style: { fontSize: 9, fill: 'hsl(var(--muted-foreground))' } }} />
                        <YAxis allowDecimals={false} tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }} label={{ value: 'Nº de jogos', angle: -90, position: 'insideLeft', style: { fontSize: 9, fill: 'hsl(var(--muted-foreground))', textAnchor: 'middle' } }} />
                        <RTooltip contentStyle={{ backgroundColor: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: '8px', fontSize: '11px' }} />
                        <Legend verticalAlign="top" height={26} wrapperStyle={{ fontSize: '11px' }} />
                        <Bar dataKey={homeTeamId} name={teamPt(homeTeamId)} fill="#f59e0b" radius={[2, 2, 0, 0]} />
                        <Bar dataKey={awayTeamId} name={teamPt(awayTeamId)} fill="#ef4444" radius={[2, 2, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              </div>
            </>
          ) : (
            /* USUÁRIO NÃO LOGADO: Blur/fade + MOCK PLACEHOLDERS (Anti-DevTools) + Banner Flutuante de Login */
            <div className="relative mt-4 rounded-2xl border border-border/40 p-6 bg-card/40 overflow-hidden min-h-[420px]">
              {/* Mock Placeholders com blur pesado - SEM NENHUM DADO REAL NO DOM */}
              <div className="backdrop-blur-xl blur-lg select-none pointer-events-none opacity-25 filter grayscale space-y-6">
                <div className="grid grid-cols-3 gap-4">
                  <div className="h-44 bg-muted/60 rounded-xl" />
                  <div className="h-44 bg-muted/60 rounded-xl" />
                  <div className="h-44 bg-muted/60 rounded-xl" />
                </div>
                <div className="h-36 bg-muted/60 rounded-xl" />
                <div className="h-56 bg-muted/60 rounded-xl" />
              </div>

              {/* Overlay central de bloqueio */}
              <div className="absolute inset-0 bg-gradient-to-b from-transparent via-background/95 to-background flex flex-col items-center justify-center text-center p-6 z-20">
                <div className="w-14 h-14 rounded-2xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center mb-3 shadow-xl">
                  <Lock className="w-7 h-7 text-cyan-400" />
                </div>
                <h4 className="text-lg font-bold mb-1.5 text-foreground">Estatísticas Avançadas Protegidas</h4>
                <p className="text-xs text-muted-foreground max-w-md mb-5 leading-relaxed">
                  Faça login para desbloquear o confronto de estilos, minutagem de gols, destaques recentes, profundidade estatística, matriz de quadrantes e a inteligência completa da partida.
                </p>
                <button
                  onClick={() => router.push('/entrar')}
                  className="px-7 py-3 rounded-xl font-bold text-xs bg-gradient-to-r from-emerald-500 via-cyan-500 to-violet-600 text-white shadow-xl hover:brightness-110 transition-all transform hover:scale-[1.03] flex items-center gap-2"
                >
                  <Sparkles className="w-4 h-4" />
                  Faça login para liberar todas as estatísticas →
                </button>
              </div>
            </div>
          )}

          {/* BANNER FLUTUANTE DE LOGIN (Acompanha o scroll quando o usuário não estiver logado) */}
          {!user && (
            <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 w-[92%] max-w-2xl bg-slate-950/95 border border-cyan-500/50 backdrop-blur-md p-3.5 rounded-2xl shadow-2xl flex items-center justify-between gap-3 text-white">
              <div className="flex items-center gap-2.5 min-w-0">
                <div className="w-8 h-8 rounded-xl bg-cyan-500/20 border border-cyan-500/40 flex items-center justify-center shrink-0">
                  <Sparkles className="w-4 h-4 text-cyan-400" />
                </div>
                <span className="text-xs font-semibold leading-tight truncate">
                  Faça login e gere a análise da partida para ter acesso a todas as estatísticas avançadas!
                </span>
              </div>
              <button
                onClick={() => router.push('/entrar')}
                className="shrink-0 px-4 py-2 rounded-xl text-xs font-bold bg-gradient-to-r from-emerald-500 to-cyan-500 text-white shadow-lg hover:scale-105 transition-transform"
              >
                Fazer Login →
              </button>
            </div>
          )}
        </motion.div>
      )}
    </div>
  );
}
