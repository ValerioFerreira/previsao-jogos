"use client";
import React, { useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { AlertTriangle, Zap, TrendingUp, ShieldAlert, ShieldCheck } from 'lucide-react';
import { api, PredictionResponse, RecentMatch, Anomaly, UpcomingFixture, teamLogoUrl } from '@/lib/api';
import InfoTooltip from '@/components/platform/InfoTooltip';
import { usePrediction } from '@/lib/PredictionContext';
import { TeamSelect } from '@/components/platform/TeamSelect';
import { MarketCard } from '@/components/platform/MarketCard';
import { teamPt } from '@/lib/teamNames';
import { competitionPt } from '@/lib/competitionNames';
import { MatchPickerModal } from '@/components/platform/MatchPickerModal';

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
  return `${(odd * 0.93).toFixed(2)}–${odd.toFixed(2)}`;
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
      <InfoTooltip text={confiabilidade._resumo} />
    </div>
  );
}

function DataReliabilityBadge({ totalMatches }: { totalMatches: number }) {
  const isLow = totalMatches < 10;
  return (
    <div className={`mt-2 inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-[10px] font-medium border ${isLow ? 'bg-amber-500/10 border-amber-500/30 text-amber-500' : 'bg-emerald-500/10 border-emerald-500/30 text-emerald-500'}`}>
      {isLow ? <ShieldAlert className="w-3 h-3" /> : <ShieldCheck className="w-3 h-3" />}
      {isLow ? `Confiabilidade Baixa (${totalMatches} jogos no BD)` : `Confiabilidade Adequada (${totalMatches} jogos)`}
    </div>
  );
}

function RecentMatchCard({ match, onOpen }: { match: RecentMatch; onOpen?: () => void }) {
  const diff = match.goals_scored - match.goals_conceded;
  const result = diff > 0 ? 'V' : diff < 0 ? 'D' : 'E';
  const color = result === 'V' ? 'bg-emerald-500/20 text-emerald-500 border-emerald-500/30' : result === 'D' ? 'bg-red-500/20 text-red-500 border-red-500/30' : 'bg-amber-500/20 text-amber-500 border-amber-500/30';

  return (
    <button
      onClick={onOpen}
      className="flex flex-col p-2 bg-muted/40 border border-border/50 rounded-lg text-xs min-w-[150px] shrink-0 text-left hover:border-cyan-500/40 hover:bg-muted/70 transition-colors cursor-pointer"
      title="Ver estatísticas deste jogo"
    >
      <div className="flex justify-between items-center mb-1 border-b border-border/30 pb-1">
        <span className="text-[10px] text-muted-foreground">{formatDateBR(match.date)}</span>
        <div className={`flex items-center justify-center w-5 h-5 rounded-[4px] border font-bold ${color}`}>
          {result}
        </div>
      </div>
      <p className="font-semibold truncate max-w-[130px]" title={teamPt(match.opponent)}>
        {match.is_home ? 'Mandante' : 'Fora'} vs {teamPt(match.opponent)}
      </p>
      {match.competition && (
        <p className="text-[10px] text-muted-foreground truncate max-w-[130px]" title={competitionPt(match.competition)}>{competitionPt(match.competition)}</p>
      )}
      <p className="text-[11px] font-mono mt-1 text-muted-foreground">
        Placar: <span className="text-foreground">{match.is_home ? `${match.goals_scored}-${match.goals_conceded}` : `${match.goals_conceded}-${match.goals_scored}`}</span>
      </p>
      <div className="flex gap-2 mt-1.5 text-[10px] text-muted-foreground">
        <span title="Chutes">👟 {match.sb_shots || 0}</span>
        <span title="Escanteios">🚩 {match.sb_corners || 0}</span>
        <span title="Cartões">🟨 {match.sb_cards || 0}</span>
      </div>
    </button>
  );
}

export default function Previsoes() {
  const [teams, setTeams] = React.useState<string[]>([]);
  const [tournaments, setTournaments] = React.useState<string[]>([]);
  
  const router = useRouter();
  const { homeTeamId, setHomeTeamId, awayTeamId, setAwayTeamId, competition, setCompetition, neutralField, setNeutralField } = usePrediction();
  
  const [loading, setLoading] = useState(false);
  const [projection, setProjection] = useState<PredictionResponse | null>(null);
  
  const [homeForm, setHomeForm] = useState<{matches: RecentMatch[], total: number}>({matches: [], total: 0});
  const [awayForm, setAwayForm] = useState<{matches: RecentMatch[], total: number}>({matches: [], total: 0});
  const [homeAnomalies, setHomeAnomalies] = useState<Anomaly[]>([]);
  const [awayAnomalies, setAwayAnomalies] = useState<Anomaly[]>([]);
  
  const [h2hBtts, setH2hBtts] = useState<number | null>(null);
  const [h2hGoals, setH2hGoals] = useState<number | null>(null);

  // Modo de análise: partida futura (pré-preenche de um jogo agendado) ou independente.
  const [mode, setMode] = useState<'independente' | 'futura'>('independente');
  const [referee, setReferee] = useState('');
  const [referees, setReferees] = useState<string[]>([]);
  const [upcoming, setUpcoming] = useState<UpcomingFixture[]>([]);
  const [teamIds, setTeamIds] = useState<Record<string, number>>({});
  const [modalOpen, setModalOpen] = useState(false);

  React.useEffect(() => {
    api.referees().then(r => setReferees(r.referees)).catch(() => {});
    api.upcomingFixtures().then(r => setUpcoming(r.fixtures)).catch(() => {});
    api.teamIds().then(setTeamIds).catch(() => {});
  }, []);

  const selectFutureFixture = (fid: string) => {
    const fx = upcoming.find(f => f.fixture_id === fid);
    if (!fx) return;
    setHomeTeamId(fx.home);
    setAwayTeamId(fx.away);
    setCompetition(fx.tournament);
    setNeutralField(fx.neutral);
    setProjection(null);
  };

  React.useEffect(() => {
    api.teams().then(res => {
      setTeams(res.teams);
      setTournaments(res.tournaments);
    }).catch(console.error);
  }, []);

  React.useEffect(() => {
    if (homeTeamId) {
      api.recentMatches(homeTeamId).then(res => setHomeForm({matches: res.matches, total: res.total_matches})).catch(() => {});
      api.teamAnomalies(homeTeamId).then(res => setHomeAnomalies(res.anomalies)).catch(() => {});
    } else {
      setHomeForm({matches: [], total: 0});
      setHomeAnomalies([]);
    }
  }, [homeTeamId]);

  React.useEffect(() => {
    if (awayTeamId) {
      api.recentMatches(awayTeamId).then(res => setAwayForm({matches: res.matches, total: res.total_matches})).catch(() => {});
      api.teamAnomalies(awayTeamId).then(res => setAwayAnomalies(res.anomalies)).catch(() => {});
    } else {
      setAwayForm({matches: [], total: 0});
      setAwayAnomalies([]);
    }
  }, [awayTeamId]);

  const canGenerate = homeTeamId && awayTeamId && homeTeamId !== awayTeamId;

  const handleGenerate = useCallback(() => {
    if (!canGenerate) return;
    setLoading(true);
    setProjection(null);
    setH2hBtts(null);
    setH2hGoals(null);
    
    // Fetch H2H explicitly to get extra metrics if needed, although prediction might not have it.
    api.h2h(homeTeamId, awayTeamId).then(h2h => {
      const btts = h2h?.metrics?.btts_percentage;
      const goals = h2h?.metrics?.avg_total_goals;
      setH2hBtts(typeof btts === 'number' ? btts : null);
      setH2hGoals(typeof goals === 'number' ? goals : null);
    }).catch(() => {
      setH2hBtts(null);
      setH2hGoals(null);
    });

    api.predict({
      home_team: homeTeamId,
      away_team: awayTeamId,
      tournament: competition,
      neutral: neutralField
    }).then(res => {
      setProjection(res);
      setLoading(false);
    }).catch(err => {
      console.error(err);
      setLoading(false);
    });
  }, [homeTeamId, awayTeamId, competition, neutralField, canGenerate]);

  return (
    <div className="space-y-6">
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="bg-card border border-border/50 rounded-xl p-5">
        <h2 className="text-lg font-heading font-bold mb-4 flex items-center gap-2">
          <TrendingUp className="w-5 h-5 text-emerald-500" /> Configuração do Confronto
        </h2>

        {/* Modo de análise: partida futura agendada x análise independente */}
        <div className="inline-flex p-1 mb-4 rounded-lg bg-muted text-xs font-medium">
          <button
            onClick={() => setMode('futura')}
            className={`px-3 py-1.5 rounded-md transition-colors ${mode === 'futura' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
          >Selecionar Partida Futura</button>
          <button
            onClick={() => setMode('independente')}
            className={`px-3 py-1.5 rounded-md transition-colors ${mode === 'independente' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
          >Análise Independente</button>
        </div>

        {mode === 'futura' && (
          <div className="mb-2">
            <button onClick={() => setModalOpen(true)}
              className="px-4 py-2 rounded-lg text-sm font-medium border border-cyan-500/40 bg-cyan-500/10 text-foreground hover:bg-cyan-500/20 transition-colors">
              {homeTeamId && awayTeamId ? `${teamPt(homeTeamId)} x ${teamPt(awayTeamId)} — trocar partida` : 'Escolher partida agendada'}
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

      <MatchPickerModal
        open={modalOpen}
        onOpenChange={setModalOpen}
        fixtures={upcoming}
        teamIds={teamIds}
        onSelect={(fx) => selectFutureFixture(fx.fixture_id)}
        title="Selecionar Partida Futura"
      />

      <AnimatePresence>
        {(homeTeamId || awayTeamId) && (
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {[
              { teamId: homeTeamId, form: homeForm, anomalies: homeAnomalies, label: 'Mandante' },
              { teamId: awayTeamId, form: awayForm, anomalies: awayAnomalies, label: 'Visitante' }
            ].map(({ teamId, form, anomalies, label }) => teamId && (
              <div key={teamId} className="bg-card border border-border/50 rounded-xl p-5 overflow-hidden">
                <div className="relative mb-2">
                  <div className="absolute right-0 top-0 z-10"><DataReliabilityBadge totalMatches={form.total} /></div>
                  <div className="text-center">
                    {teamLogoUrl(teamIds[teamId]) && (
                      <img src={teamLogoUrl(teamIds[teamId])!} alt="" className="w-9 h-9 mx-auto mb-1 object-contain" loading="lazy" onError={(e) => { e.currentTarget.style.display = 'none'; }} />
                    )}
                    <p className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</p>
                    <h3 className="text-sm font-semibold">{teamPt(teamId)}</h3>
                  </div>
                </div>

                <div className="mt-4 mb-4">
                  <p className="text-xs text-muted-foreground mb-2 flex items-center gap-1">Resultados dos últimos 5 jogos</p>
                  <div className="flex gap-2 overflow-x-auto pb-2 custom-scrollbar">
                    {form.matches.map((m, i) => {
                      const mh = m.is_home ? teamId : m.opponent;
                      const ma = m.is_home ? m.opponent : teamId;
                      return <RecentMatchCard key={i} match={m} onOpen={() => router.push(`/estatisticas?home=${encodeURIComponent(mh)}&away=${encodeURIComponent(ma)}&date=${encodeURIComponent(m.date.slice(0, 10))}`)} />;
                    })}
                  </div>
                </div>

                <div className={`rounded-lg p-3 ${anomalies.length > 0 ? 'bg-amber-500/5 border border-amber-500/20' : 'bg-muted/50 border border-border/50'}`}>
                  <p className="text-xs font-medium mb-1.5 flex items-center gap-1.5">
                    <Zap className={`w-3.5 h-3.5 ${anomalies.length > 0 ? 'text-amber-400' : 'text-muted-foreground'}`} />
                    Radar de Anomalias
                  </p>
                  {anomalies.length > 0 ? (
                    <ul className="space-y-1">
                      {anomalies.map((a, i) => (
                        <li key={i} className="text-xs text-amber-500/80 flex items-start gap-1.5">
                          <AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" /><span>{a.message}</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-xs text-muted-foreground italic">Nenhum desvio estatístico detectado recentemente.</p>
                  )}
                </div>
              </div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>

      <div className="flex justify-center">
        <motion.button
          whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
          onClick={handleGenerate} disabled={!canGenerate || loading}
          className="px-8 py-3 rounded-xl font-semibold text-sm transition-all disabled:opacity-40 disabled:cursor-not-allowed bg-gradient-to-r from-emerald-500 to-cyan-500 text-white shadow-lg shadow-emerald-500/20 hover:shadow-emerald-500/30"
        >
          {loading ? <span className="flex items-center gap-2"><div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> Processando...</span> : 'Gerar Previsão'}
        </motion.button>
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

            {/* Probabilidades de Resultados */}
            <div className="bg-card border border-border/50 rounded-xl p-6 text-center shadow-sm">
              <p className="text-xs text-muted-foreground mb-4 font-semibold uppercase tracking-wider">PROBABILIDADES DE RESULTADOS</p>
              <div className="flex flex-wrap items-center justify-center gap-4 sm:gap-8 mb-4">
                <div className="text-center w-full sm:w-1/4">
                  {teamLogoUrl(teamIds[homeTeamId]) && (
                    <img src={teamLogoUrl(teamIds[homeTeamId])!} alt="" className="w-8 h-8 mx-auto mb-1 object-contain" loading="lazy" onError={(e)=>{e.currentTarget.style.display='none'}} />
                  )}
                  <p className="text-sm font-medium text-foreground mb-1 truncate">{teamPt(homeTeamId)}</p>
                  <p className="text-3xl font-bold font-mono text-emerald-400">{projection.vencedor.probabilidades[homeTeamId]}%</p>
                  <p className="text-[10px] text-muted-foreground mt-1">Faixa de odd justa: {oddRangeStr(projection.vencedor.probabilidades[homeTeamId])}</p>
                </div>
                <div className="text-center w-full sm:w-1/4 border-y sm:border-y-0 sm:border-x border-border/50 py-4 sm:py-0">
                  <p className="text-sm font-medium text-muted-foreground mb-1">Empate</p>
                  <p className="text-2xl font-bold font-mono text-muted-foreground">{projection.vencedor.probabilidades["Empate"]}%</p>
                  <p className="text-[10px] text-muted-foreground mt-1">Faixa de odd justa: {oddRangeStr(projection.vencedor.probabilidades["Empate"])}</p>
                </div>
                <div className="text-center w-full sm:w-1/4">
                  {teamLogoUrl(teamIds[awayTeamId]) && (
                    <img src={teamLogoUrl(teamIds[awayTeamId])!} alt="" className="w-8 h-8 mx-auto mb-1 object-contain" loading="lazy" onError={(e)=>{e.currentTarget.style.display='none'}} />
                  )}
                  <p className="text-sm font-medium text-foreground mb-1 truncate">{teamPt(awayTeamId)}</p>
                  <p className="text-3xl font-bold font-mono text-cyan-400">{projection.vencedor.probabilidades[awayTeamId]}%</p>
                  <p className="text-[10px] text-muted-foreground mt-1">Faixa de odd justa: {oddRangeStr(projection.vencedor.probabilidades[awayTeamId])}</p>
                </div>
              </div>
            </div>

            {/* Ambas Marcam (BTTS) — logo abaixo das probabilidades de resultado */}
            {projection.ambas_marcam && (
              <div className="bg-card border border-border/50 rounded-xl p-5">
                <h4 className="text-sm font-semibold mb-3 flex items-center gap-1.5">
                  Ambas Marcam (BTTS)
                  <InfoTooltip text="Probabilidade de as duas equipes marcarem pelo menos um gol na partida." />
                </h4>
                <div className="flex flex-wrap items-center justify-around gap-4 text-center">
                  <div>
                    <p className="text-[10px] uppercase tracking-wide text-muted-foreground mb-1">Sim</p>
                    <p className="text-2xl font-mono font-bold text-emerald-400">{projection.ambas_marcam.prob_sim}%</p>
                    <p className="text-[10px] text-muted-foreground mt-1">Faixa de odd justa: {oddRangeStr(projection.ambas_marcam.prob_sim)}</p>
                  </div>
                  <div>
                    <p className="text-[10px] uppercase tracking-wide text-muted-foreground mb-1">Não</p>
                    <p className="text-2xl font-mono font-bold text-blue-400">{(100 - projection.ambas_marcam.prob_sim).toFixed(1)}%</p>
                    <p className="text-[10px] text-muted-foreground mt-1">Faixa de odd justa: {oddRangeStr(100 - projection.ambas_marcam.prob_sim)}</p>
                  </div>
                </div>
              </div>
            )}

            {/* H2H — só quando há histórico de confronto direto */}
            {projection.confronto_direto && !projection.confronto_direto.includes('Sem confrontos') && (
              <div className="bg-card border border-border/50 rounded-xl p-4 text-sm text-muted-foreground shadow-sm">
                <div className="flex flex-col sm:flex-row gap-4 sm:items-center justify-between">
                  <div>
                    <span className="font-semibold text-foreground block mb-1">Resumo do Confronto Direto (H2H):</span>
                    <span className="italic">{projection.confronto_direto}</span>
                  </div>
                  {typeof h2hBtts === 'number' && typeof h2hGoals === 'number' && (
                    <div className="flex gap-4 sm:border-l border-border/50 sm:pl-4 shrink-0">
                       <div>
                         <span className="block text-[10px] uppercase tracking-wide">Média Gols H2H</span>
                         <span className="font-mono font-bold text-foreground">{h2hGoals.toFixed(2)}</span>
                       </div>
                       <div>
                         <span className="block text-[10px] uppercase tracking-wide">Ambas Marcam H2H</span>
                         <span className="font-mono font-bold text-foreground">{h2hBtts.toFixed(1)}%</span>
                       </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* MERCADOS */}
            <h3 className="text-lg font-heading font-bold mt-8 mb-4 border-b border-border/50 pb-2">MERCADOS</h3>

            <div className="space-y-8">
              {/* Gols (mandante/total/visitante, com seletor de tempo) */}
              {projection.gols && (
                <div>
                  <h4 className="text-sm font-bold uppercase text-foreground mb-3 flex items-center justify-center gap-1.5">
                    Gols
                    <InfoTooltip text="Gols marcados na partida. Use o seletor de cada cartão para ver partida inteira, 1º ou 2º tempo." />
                  </h4>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <MarketCard title="Gols" subtitle={`Mandante (${teamPt(homeTeamId)})`} periods={goalPeriods(projection, homeTeamId)} />
                    <MarketCard title="Gols" subtitle="Totais (Partida)" periods={goalPeriods(projection, 'total')} />
                    <MarketCard title="Gols" subtitle={`Visitante (${teamPt(awayTeamId)})`} periods={goalPeriods(projection, awayTeamId)} />
                  </div>
                </div>
              )}

              {/* Finalizações */}
              {projection.chutes && (
                <div>
                  <h4 className="text-sm font-bold uppercase text-foreground mb-3 flex items-center justify-center gap-1.5">
                    Finalizações
                    <InfoTooltip text="Conta qualquer tentativa de marcar gol, independentemente da direção. Inclui chutes no alvo, para fora, na trave e também os bloqueados pela defesa adversária." />
                  </h4>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    {projection.chutes_equipe && projection.chutes_equipe[homeTeamId] && (
                      <MarketCard title="Finalizações" subtitle={`Mandante (${teamPt(homeTeamId)})`} prediction={projection.chutes_equipe[homeTeamId]} />
                    )}
                    <MarketCard title="Finalizações" subtitle="Totais (Partida)" prediction={projection.chutes as any} />
                    {projection.chutes_equipe && projection.chutes_equipe[awayTeamId] && (
                      <MarketCard title="Finalizações" subtitle={`Visitante (${teamPt(awayTeamId)})`} prediction={projection.chutes_equipe[awayTeamId]} />
                    )}
                  </div>
                </div>
              )}

              {/* Chutes a Gol */}
              {projection.chutes_a_gol && projection.chutes_a_gol.total && (
                <div>
                  <h4 className="text-sm font-bold uppercase text-foreground mb-3 flex items-center justify-center gap-1.5">
                    Chutes a Gol
                    <InfoTooltip text="Considera apenas os chutes que vão na direção exata da baliza e que seriam gol se não houvesse intervenção do goleiro. Chutes na trave, para fora ou bloqueados não contam." />
                  </h4>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <MarketCard title="Chutes a Gol" subtitle={`Mandante (${teamPt(homeTeamId)})`} prediction={projection.chutes_a_gol[homeTeamId]} />
                    <MarketCard title="Chutes a Gol" subtitle="Totais (Partida)" prediction={projection.chutes_a_gol.total} />
                    <MarketCard title="Chutes a Gol" subtitle={`Visitante (${teamPt(awayTeamId)})`} prediction={projection.chutes_a_gol[awayTeamId]} />
                  </div>
                </div>
              )}

              {/* Escanteios */}
              {projection.escanteios && projection.escanteios.total && (
                <div>
                  <h4 className="text-sm font-bold uppercase text-foreground mb-3 flex items-center justify-center gap-1.5">
                    Escanteios
                    <InfoTooltip text="Soma dos tiros de canto efetivamente cobrados durante a partida. Escanteios assinalados pelo árbitro, mas não cobrados antes do apito final, geralmente não entram na conta." />
                  </h4>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <MarketCard title="Escanteios" subtitle={`Mandante (${teamPt(homeTeamId)})`} prediction={projection.escanteios[homeTeamId]} />
                    <MarketCard title="Escanteios" subtitle="Totais (Partida)" prediction={projection.escanteios.total} />
                    <MarketCard title="Escanteios" subtitle={`Visitante (${teamPt(awayTeamId)})`} prediction={projection.escanteios[awayTeamId]} />
                  </div>
                </div>
              )}

              {/* Cartões (com seletor de tempo) */}
              {projection.cartoes && projection.cartoes.total && (
                <div>
                  <h4 className="text-sm font-bold uppercase text-foreground mb-3 flex items-center justify-center gap-1.5">
                    Cartões
                    <InfoTooltip text="Contagem de cartões amarelos e vermelhos aplicados aos jogadores ativos em campo. Cartões mostrados para jogadores no banco de reservas ou para a comissão técnica não são contabilizados." />
                  </h4>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <MarketCard title="Cartões" subtitle={`Mandante (${teamPt(homeTeamId)})`} periods={cardPeriods(projection, homeTeamId)} />
                    <MarketCard title="Cartões" subtitle="Totais (Partida)" periods={cardPeriods(projection, 'total')} />
                    <MarketCard title="Cartões" subtitle={`Visitante (${teamPt(awayTeamId)})`} periods={cardPeriods(projection, awayTeamId)} />
                  </div>
                </div>
              )}
            </div>

          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
