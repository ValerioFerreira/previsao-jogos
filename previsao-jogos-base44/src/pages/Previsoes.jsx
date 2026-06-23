import React, { useState, useMemo, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { AlertTriangle, Zap, TrendingUp } from 'lucide-react';
import { TEAMS, COMPETITIONS, generateRecentForm, generateAnomalies, generateProjection } from '@/lib/mock-data';
import FormBadge from '@/components/platform/FormBadge';
import MarketCard from '@/components/platform/MarketCard';
import ConfidenceBadge from '@/components/platform/ConfidenceBadge';
import InfoTooltip from '@/components/platform/InfoTooltip';

export default function Previsoes() {
  const [homeTeamId, setHomeTeamId] = useState('');
  const [awayTeamId, setAwayTeamId] = useState('');
  const [competition, setCompetition] = useState('');
  const [neutralField, setNeutralField] = useState(false);
  const [loading, setLoading] = useState(false);
  const [projection, setProjection] = useState(null);

  const homeTeam = TEAMS.find(t => t.id.toString() === homeTeamId);
  const awayTeam = TEAMS.find(t => t.id.toString() === awayTeamId);

  const homeForm = useMemo(() => homeTeam ? generateRecentForm(homeTeam.name) : [], [homeTeam?.id]);
  const awayForm = useMemo(() => awayTeam ? generateRecentForm(awayTeam.name) : [], [awayTeam?.id]);
  const homeAnomalies = useMemo(() => homeTeam ? generateAnomalies(homeTeam.name) : [], [homeTeam?.id]);
  const awayAnomalies = useMemo(() => awayTeam ? generateAnomalies(awayTeam.name) : [], [awayTeam?.id]);

  const handleGenerate = useCallback(() => {
    if (!homeTeam || !awayTeam) return;
    setLoading(true);
    setProjection(null);
    setTimeout(() => {
      const result = generateProjection(homeTeam, awayTeam);
      setProjection(result);
      setLoading(false);
    }, 1800);
  }, [homeTeam, awayTeam]);

  const canGenerate = homeTeam && awayTeam && homeTeamId !== awayTeamId;

  return (
    <div className="space-y-6">
      {/* Selection Panel */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="bg-card border border-border/50 rounded-xl p-5"
      >
        <h2 className="text-lg font-heading font-bold mb-4 flex items-center gap-2">
          <TrendingUp className="w-5 h-5 text-emerald-500" />
          Configuração do Confronto
        </h2>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Home Team */}
          <div>
            <Label className="text-xs text-muted-foreground mb-1.5 block">Time Mandante</Label>
            <Select value={homeTeamId} onValueChange={v => { setHomeTeamId(v); setProjection(null); }}>
              <SelectTrigger className="h-10">
                <SelectValue placeholder="Selecione..." />
              </SelectTrigger>
              <SelectContent>
                {TEAMS.filter(t => t.id.toString() !== awayTeamId).map(t => (
                  <SelectItem key={t.id} value={t.id.toString()}>{t.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Away Team */}
          <div>
            <Label className="text-xs text-muted-foreground mb-1.5 block">Time Visitante</Label>
            <Select value={awayTeamId} onValueChange={v => { setAwayTeamId(v); setProjection(null); }}>
              <SelectTrigger className="h-10">
                <SelectValue placeholder="Selecione..." />
              </SelectTrigger>
              <SelectContent>
                {TEAMS.filter(t => t.id.toString() !== homeTeamId).map(t => (
                  <SelectItem key={t.id} value={t.id.toString()}>{t.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Competition */}
          <div>
            <Label className="text-xs text-muted-foreground mb-1.5 block">Competição</Label>
            <Select value={competition} onValueChange={setCompetition}>
              <SelectTrigger className="h-10">
                <SelectValue placeholder="Selecione..." />
              </SelectTrigger>
              <SelectContent>
                {COMPETITIONS.map(c => (
                  <SelectItem key={c} value={c}>{c}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Neutral Field */}
          <div className="flex items-end pb-2">
            <div className="flex items-center gap-2">
              <Switch id="neutral" checked={neutralField} onCheckedChange={setNeutralField} />
              <Label htmlFor="neutral" className="text-sm cursor-pointer">Campo Neutro</Label>
              <InfoTooltip text="Quando ativado, remove a vantagem de mando de campo do modelo preditivo, tratando ambas as equipes como se jogassem em local neutro." />
            </div>
          </div>
        </div>
      </motion.div>

      {/* Recent Form */}
      <AnimatePresence>
        {(homeTeam || awayTeam) && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="grid grid-cols-1 lg:grid-cols-2 gap-4"
          >
            {[{ team: homeTeam, form: homeForm, anomalies: homeAnomalies, label: 'Mandante' },
              { team: awayTeam, form: awayForm, anomalies: awayAnomalies, label: 'Visitante' }].map(({ team, form, anomalies, label }) => (
              team && (
                <div key={team.id} className="bg-card border border-border/50 rounded-xl p-5">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-sm font-semibold">
                      <span className="text-muted-foreground">{label}: </span>
                      {team.name}
                    </h3>
                    <span className="text-[10px] text-muted-foreground font-mono">ELO {team.elo}</span>
                  </div>

                  {/* Form Badges */}
                  <div className="mb-4">
                    <p className="text-xs text-muted-foreground mb-2 flex items-center gap-1">
                      Forma Recente (5 jogos)
                      <InfoTooltip text="Últimas 5 partidas disputadas. Clique em cada badge para ver estatísticas detalhadas do jogo." />
                    </p>
                    <div className="flex gap-1.5 flex-wrap">
                      {form.map((m, i) => (
                        <FormBadge key={i} match={m} />
                      ))}
                    </div>
                  </div>

                  {/* Anomalies */}
                  <div className={`rounded-lg p-3 ${anomalies.length > 0 ? 'bg-amber-500/5 border border-amber-500/20' : 'bg-muted/50'}`}>
                    <p className="text-xs font-medium mb-1.5 flex items-center gap-1.5">
                      <Zap className={`w-3.5 h-3.5 ${anomalies.length > 0 ? 'text-amber-400' : 'text-muted-foreground'}`} />
                      Motor de Anomalias
                      <InfoTooltip text="Insights gerados automaticamente via Z-Score, identificando desvios estatísticos significativos em relação às médias históricas da equipe." />
                    </p>
                    {anomalies.length > 0 ? (
                      <ul className="space-y-1">
                        {anomalies.map((a, i) => (
                          <li key={i} className="text-xs text-amber-300/80 flex items-start gap-1.5">
                            <AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" />
                            <span>{a}</span>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-xs text-muted-foreground italic">
                        Equipe operando dentro dos padrões históricos esperados.
                      </p>
                    )}
                  </div>
                </div>
              )
            ))}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Generate Button */}
      <div className="flex justify-center">
        <motion.button
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          onClick={handleGenerate}
          disabled={!canGenerate || loading}
          className="px-8 py-3 rounded-xl font-semibold text-sm transition-all disabled:opacity-40 disabled:cursor-not-allowed bg-gradient-to-r from-emerald-500 to-cyan-500 text-white shadow-lg shadow-emerald-500/20 hover:shadow-emerald-500/30"
        >
          {loading ? (
            <span className="flex items-center gap-2">
              <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              Gerando Previsão...
            </span>
          ) : (
            'Gerar Previsão'
          )}
        </motion.button>
      </div>

      {/* Loading Skeletons */}
      <AnimatePresence>
        {loading && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="space-y-4"
          >
            <div className="bg-card border border-border/50 rounded-xl p-6 animate-pulse">
              <div className="h-8 bg-muted rounded w-1/3 mx-auto mb-4" />
              <div className="h-4 bg-muted rounded w-1/4 mx-auto" />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {[1, 2, 3, 4].map(i => (
                <div key={i} className="bg-card border border-border/50 rounded-xl p-5 animate-pulse">
                  <div className="h-4 bg-muted rounded w-1/2 mb-3" />
                  <div className="h-8 bg-muted rounded w-1/3 mb-3" />
                  <div className="h-6 bg-muted rounded w-full" />
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Projection Results */}
      <AnimatePresence>
        {projection && !loading && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="space-y-5"
          >
            {/* Score Header */}
            <div className="bg-card border border-border/50 rounded-xl p-6 text-center">
              <p className="text-xs text-muted-foreground mb-2">Placar Mais Provável</p>
              <div className="flex items-center justify-center gap-4 mb-3">
                <div className="text-right">
                  <p className="text-sm font-medium text-muted-foreground">{homeTeam?.name}</p>
                  <p className="text-4xl font-bold font-mono text-foreground">{projection.predictedScore.home}</p>
                </div>
                <span className="text-xl text-muted-foreground font-light">×</span>
                <div className="text-left">
                  <p className="text-sm font-medium text-muted-foreground">{awayTeam?.name}</p>
                  <p className="text-4xl font-bold font-mono text-foreground">{projection.predictedScore.away}</p>
                </div>
              </div>
              <ConfidenceBadge totalGames={projection.confidence.totalGames} />
            </div>

            {/* Market Cards */}
            <div>
              <h3 className="text-sm font-semibold text-muted-foreground mb-3 flex items-center gap-1.5">
                Projeções por Mercado
                <InfoTooltip text="Cada mercado apresenta a média projetada pelo modelo e permite explorar linhas (Over/Under) com probabilidades e odds justas calculadas via CDF (Função de Distribuição Cumulativa)." />
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {Object.values(projection.markets).map((market, i) => (
                  <MarketCard key={market.label} market={market} index={i} />
                ))}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}