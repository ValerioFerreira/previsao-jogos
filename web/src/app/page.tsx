"use client";
import React, { useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { AlertTriangle, Zap, TrendingUp, ShieldAlert, ShieldCheck } from 'lucide-react';
import { api, PredictionResponse, RecentMatch, Anomaly } from '@/lib/api';
import InfoTooltip from '@/components/platform/InfoTooltip';
import { usePrediction } from '@/lib/PredictionContext';
import { TeamSelect } from '@/components/platform/TeamSelect';
import { MarketCard } from '@/components/platform/MarketCard';

// Labels amigáveis para os mercados por tempo (renderizados quando o backend enviar `tempos`).
const TEMPO_LABELS: Record<string, string> = {
  gols_1t: 'Gols — 1º Tempo',
  gols_2t: 'Gols — 2º Tempo',
  cartoes_1t: 'Cartões — 1º Tempo',
  cartoes_2t: 'Cartões — 2º Tempo',
};

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

function RecentMatchCard({ match }: { match: RecentMatch }) {
  const diff = match.goals_scored - match.goals_conceded;
  const result = diff > 0 ? 'V' : diff < 0 ? 'D' : 'E';
  const color = result === 'V' ? 'bg-emerald-500/20 text-emerald-500 border-emerald-500/30' : result === 'D' ? 'bg-red-500/20 text-red-500 border-red-500/30' : 'bg-amber-500/20 text-amber-500 border-amber-500/30';
  
  return (
    <div className="flex flex-col p-2 bg-muted/40 border border-border/50 rounded-lg text-xs min-w-[140px] shrink-0">
      <div className="flex justify-between items-center mb-1 border-b border-border/30 pb-1">
        <span className="text-[10px] text-muted-foreground">{match.date.split(' ')[0]}</span>
        <div className={`flex items-center justify-center w-5 h-5 rounded-[4px] border font-bold ${color}`}>
          {result}
        </div>
      </div>
      <p className="font-semibold truncate max-w-[120px]" title={match.opponent}>
        {match.is_home ? 'C' : 'F'} vs {match.opponent}
      </p>
      <p className="text-[11px] font-mono mt-1 text-muted-foreground">
        Placar: <span className="text-foreground">{match.is_home ? `${match.goals_scored}-${match.goals_conceded}` : `${match.goals_conceded}-${match.goals_scored}`}</span>
      </p>
      <div className="flex gap-2 mt-1.5 text-[10px] text-muted-foreground">
        <span title="Chutes">👟 {match.sb_shots || 0}</span>
        <span title="Escanteios">🚩 {match.sb_corners || 0}</span>
        <span title="Cartões">🟨 {match.sb_cards || 0}</span>
      </div>
    </div>
  );
}

export default function Previsoes() {
  const [teams, setTeams] = React.useState<string[]>([]);
  const [tournaments, setTournaments] = React.useState<string[]>([]);
  
  const { homeTeamId, setHomeTeamId, awayTeamId, setAwayTeamId, competition, setCompetition, neutralField, setNeutralField } = usePrediction();
  
  const [loading, setLoading] = useState(false);
  const [projection, setProjection] = useState<PredictionResponse | null>(null);
  
  const [homeForm, setHomeForm] = useState<{matches: RecentMatch[], total: number}>({matches: [], total: 0});
  const [awayForm, setAwayForm] = useState<{matches: RecentMatch[], total: number}>({matches: [], total: 0});
  const [homeAnomalies, setHomeAnomalies] = useState<Anomaly[]>([]);
  const [awayAnomalies, setAwayAnomalies] = useState<Anomaly[]>([]);
  
  const [h2hBtts, setH2hBtts] = useState<number | null>(null);
  const [h2hGoals, setH2hGoals] = useState<number | null>(null);

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

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div>
            <Label className="text-xs text-muted-foreground mb-1.5 block">Time Mandante</Label>
            <TeamSelect 
              value={homeTeamId} 
              onValueChange={v => { setHomeTeamId(v); setProjection(null); }} 
              teams={teams.filter(t => t !== awayTeamId)} 
            />
          </div>

          <div>
            <Label className="text-xs text-muted-foreground mb-1.5 block">Time Visitante</Label>
            <TeamSelect 
              value={awayTeamId} 
              onValueChange={v => { setAwayTeamId(v); setProjection(null); }} 
              teams={teams.filter(t => t !== homeTeamId)} 
            />
          </div>

          <div>
            <Label className="text-xs text-muted-foreground mb-1.5 block">Competição</Label>
            <Select value={competition} onValueChange={setCompetition}>
              <SelectTrigger className="h-10"><SelectValue placeholder="Selecione..." /></SelectTrigger>
              <SelectContent>{tournaments.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
            </Select>
          </div>

          <div className="flex items-end pb-2">
            <div className="flex items-center gap-2">
              <Switch id="neutral" checked={neutralField} onCheckedChange={setNeutralField} />
              <Label htmlFor="neutral" className="text-sm cursor-pointer">Campo Neutro</Label>
              <InfoTooltip text="Remove a vantagem de mando de campo do modelo preditivo." />
            </div>
          </div>
        </div>
      </motion.div>

      <AnimatePresence>
        {(homeTeamId || awayTeamId) && (
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {[
              { teamId: homeTeamId, form: homeForm, anomalies: homeAnomalies, label: 'Mandante' },
              { teamId: awayTeamId, form: awayForm, anomalies: awayAnomalies, label: 'Visitante' }
            ].map(({ teamId, form, anomalies, label }) => teamId && (
              <div key={teamId} className="bg-card border border-border/50 rounded-xl p-5 overflow-hidden">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-sm font-semibold"><span className="text-muted-foreground">{label}: </span>{teamId}</h3>
                </div>
                <DataReliabilityBadge totalMatches={form.total} />

                <div className="mt-4 mb-4">
                  <p className="text-xs text-muted-foreground mb-2 flex items-center gap-1">Forma Recente (5 jogos)</p>
                  <div className="flex gap-2 overflow-x-auto pb-2 custom-scrollbar">
                    {form.matches.map((m, i) => <RecentMatchCard key={i} match={m} />)}
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

            {/* Vitória Matrix */}
            <div className="bg-card border border-border/50 rounded-xl p-6 text-center shadow-sm">
              <p className="text-xs text-muted-foreground mb-4 font-semibold uppercase tracking-wider">Probabilidades de Vitória (Dixon-Coles)</p>
              <div className="flex flex-wrap items-center justify-center gap-4 sm:gap-8 mb-4">
                <div className="text-center w-full sm:w-1/4">
                  <p className="text-sm font-medium text-foreground mb-1 truncate">{homeTeamId}</p>
                  <p className="text-3xl font-bold font-mono text-emerald-400">{projection.vencedor.probabilidades[homeTeamId]}%</p>
                  <p className="text-[10px] text-muted-foreground mt-1">Odd Justa: {(100 / projection.vencedor.probabilidades[homeTeamId]).toFixed(2)}</p>
                </div>
                <div className="text-center w-full sm:w-1/4 border-y sm:border-y-0 sm:border-x border-border/50 py-4 sm:py-0">
                  <p className="text-sm font-medium text-muted-foreground mb-1">Empate</p>
                  <p className="text-2xl font-bold font-mono text-muted-foreground">{projection.vencedor.probabilidades["Empate"]}%</p>
                  <p className="text-[10px] text-muted-foreground mt-1">Odd Justa: {(100 / projection.vencedor.probabilidades["Empate"]).toFixed(2)}</p>
                </div>
                <div className="text-center w-full sm:w-1/4">
                  <p className="text-sm font-medium text-foreground mb-1 truncate">{awayTeamId}</p>
                  <p className="text-3xl font-bold font-mono text-cyan-400">{projection.vencedor.probabilidades[awayTeamId]}%</p>
                  <p className="text-[10px] text-muted-foreground mt-1">Odd Justa: {(100 / projection.vencedor.probabilidades[awayTeamId]).toFixed(2)}</p>
                </div>
              </div>
            </div>

            {/* Core General Markets (Gols Totais & BTTS) */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
               {/* Gols */}
               <div className="bg-card border border-border/50 rounded-xl p-5 flex justify-between items-center">
                 <div>
                   <h3 className="font-semibold text-sm">Gols Totais</h3>
                   <p className="text-[10px] text-muted-foreground mt-1">Over 2.5: <span className="font-mono text-foreground font-semibold">{projection.over_2_5.prob_sim}%</span> (Justa: {(100 / projection.over_2_5.prob_sim).toFixed(2)})</p>
                 </div>
                 <div className="text-right">
                   <p className="text-3xl font-mono font-bold">{projection.gols.estimativa.toFixed(2)}</p>
                   <p className="text-[10px] text-muted-foreground mt-1">Projeção Média</p>
                 </div>
               </div>
               
               {/* BTTS */}
               <div className="bg-card border border-border/50 rounded-xl p-5 flex justify-between items-center">
                 <div>
                   <h3 className="font-semibold text-sm">Ambas Marcam (BTTS)</h3>
                   <p className="text-[10px] text-muted-foreground mt-1">Odd Justa: <span className="font-mono text-foreground font-semibold">{(100 / projection.ambas_marcam.prob_sim).toFixed(2)}</span></p>
                 </div>
                 <div className="text-right">
                   <p className="text-3xl font-mono font-bold text-amber-400">{projection.ambas_marcam.prob_sim}%</p>
                   <p className="text-[10px] text-muted-foreground mt-1">Probabilidade</p>
                 </div>
               </div>
            </div>

            {/* H2H Panel Enrichment */}
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

            {/* Fractional Market Grids */}
            <h3 className="text-lg font-heading font-bold mt-8 mb-4 border-b border-border/50 pb-2">Mercados Fracionados (CDF)</h3>
            
            <div className="space-y-8">
              {/* Shots (Chutes) */}
              {projection.chutes && (
                <div>
                  <h4 className="text-sm font-semibold text-muted-foreground mb-3 flex items-center gap-1.5">
                    Finalizações
                    <InfoTooltip text="Linhas exatas calculadas para o mercado de finalizações da partida (totais e por equipe)." />
                  </h4>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    {projection.chutes_equipe && projection.chutes_equipe[homeTeamId] && (
                      <MarketCard title="Finalizações" subtitle={`Mandante (${homeTeamId})`} prediction={projection.chutes_equipe[homeTeamId]} />
                    )}
                    <MarketCard title="Finalizações" subtitle="Totais (Partida)" prediction={projection.chutes as any} />
                    {projection.chutes_equipe && projection.chutes_equipe[awayTeamId] && (
                      <MarketCard title="Finalizações" subtitle={`Visitante (${awayTeamId})`} prediction={projection.chutes_equipe[awayTeamId]} />
                    )}
                  </div>
                </div>
              )}

              {/* Chutes a gol (Shots on target) */}
              {projection.chutes_a_gol && projection.chutes_a_gol.total && (
                <div>
                  <h4 className="text-sm font-semibold text-muted-foreground mb-3 flex items-center gap-1.5">
                    Chutes a Gol
                    <InfoTooltip text="Finalizações no alvo (shots on target), totais e por equipe." />
                  </h4>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <MarketCard title="Chutes a Gol" subtitle={`Mandante (${homeTeamId})`} prediction={projection.chutes_a_gol[homeTeamId]} />
                    <MarketCard title="Chutes a Gol" subtitle="Totais (Partida)" prediction={projection.chutes_a_gol.total} />
                    <MarketCard title="Chutes a Gol" subtitle={`Visitante (${awayTeamId})`} prediction={projection.chutes_a_gol[awayTeamId]} />
                  </div>
                </div>
              )}

              {/* Escanteios */}
              {projection.escanteios && projection.escanteios.total && (
                <div>
                  <h4 className="text-sm font-semibold text-muted-foreground mb-3">Escanteios</h4>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <MarketCard title="Escanteios" subtitle={`Mandante (${homeTeamId})`} prediction={projection.escanteios[homeTeamId]} />
                    <MarketCard title="Escanteios" subtitle="Totais (Partida)" prediction={projection.escanteios.total} />
                    <MarketCard title="Escanteios" subtitle={`Visitante (${awayTeamId})`} prediction={projection.escanteios[awayTeamId]} />
                  </div>
                </div>
              )}

              {/* Cartões */}
              {projection.cartoes && projection.cartoes.total && (
                <div>
                  <h4 className="text-sm font-semibold text-muted-foreground mb-3">Cartões</h4>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <MarketCard title="Cartões" subtitle={`Mandante (${homeTeamId})`} prediction={projection.cartoes[homeTeamId]} />
                    <MarketCard title="Cartões" subtitle="Totais (Partida)" prediction={projection.cartoes.total} />
                    <MarketCard title="Cartões" subtitle={`Visitante (${awayTeamId})`} prediction={projection.cartoes[awayTeamId]} />
                  </div>
                </div>
              )}

              {/* Mercados por Tempo (1º / 2º) — renderiza automaticamente quando o backend enviar `tempos` */}
              {projection.tempos && Object.keys(projection.tempos).length > 0 && (
                <div>
                  <h4 className="text-sm font-semibold text-muted-foreground mb-3 flex items-center gap-1.5">
                    Mercados por Tempo (1º / 2º)
                    <InfoTooltip text="Linhas de gols e cartões por tempo de jogo." />
                  </h4>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {Object.entries(projection.tempos).map(([key, pred]) => (
                      <MarketCard key={key} title={TEMPO_LABELS[key] ?? key} prediction={pred} />
                    ))}
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
