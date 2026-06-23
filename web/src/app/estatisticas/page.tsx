"use client";
import React, { useState, useMemo } from 'react';
import { motion } from 'framer-motion';
import { Label } from '@/components/ui/label';
import { BarChart3, TrendingUp, Target, Users } from 'lucide-react';
import { BarChart, Bar, LineChart, Line, ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip as RTooltip, Legend, ResponsiveContainer } from 'recharts';
import { api, TeamHistoryResponse, H2HResponse } from '@/lib/api';
import InfoTooltip from '@/components/platform/InfoTooltip';
import { usePrediction } from '@/lib/PredictionContext';
import { TeamSelect } from '@/components/platform/TeamSelect';

export default function Estatisticas() {
  const [teams, setTeams] = React.useState<string[]>([]);
  
  const { homeTeamId, setHomeTeamId, awayTeamId, setAwayTeamId } = usePrediction();
  const [loading, setLoading] = useState(false);
  
  const [homeHistory, setHomeHistory] = useState<TeamHistoryResponse | null>(null);
  const [awayHistory, setAwayHistory] = useState<TeamHistoryResponse | null>(null);
  const [h2h, setH2h] = useState<H2HResponse | null>(null);

  React.useEffect(() => {
    api.teams().then(res => setTeams(res.teams)).catch(console.error);
  }, []);

  const bothSelected = homeTeamId && awayTeamId && homeTeamId !== awayTeamId;

  React.useEffect(() => {
    if (bothSelected) {
      setLoading(true);
      Promise.all([
        api.teamHistory(homeTeamId).catch(() => null),
        api.teamHistory(awayTeamId).catch(() => null),
        api.h2h(homeTeamId, awayTeamId).catch(() => null)
      ]).then(([hHist, aHist, h2hData]) => {
        setHomeHistory(hHist);
        setAwayHistory(aHist);
        setH2h(h2hData);
        setLoading(false);
      }).catch(err => {
        console.error(err);
        setLoading(false);
      });
    }
  }, [homeTeamId, awayTeamId, bothSelected]);

  const eloHistoryData = useMemo(() => {
    if (!homeHistory?.elo_history || !awayHistory?.elo_history) return [];
    try {
      const years = Array.from(new Set([
        ...homeHistory.elo_history.map(e => e.date),
        ...awayHistory.elo_history.map(e => e.date)
      ])).sort();
      
      return years.map(y => {
        const hPoint = homeHistory.elo_history.find(e => e.date === y);
        const aPoint = awayHistory.elo_history.find(e => e.date === y);
        return {
          year: y,
          [homeTeamId]: hPoint ? hPoint.elo : null,
          [awayTeamId]: aPoint ? aPoint.elo : null
        };
      });
    } catch (e) {
      console.error("Error formatting elo history", e);
      return [];
    }
  }, [homeHistory, awayHistory, homeTeamId, awayTeamId]);

  return (
    <div className="space-y-6">
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="bg-card border border-border/50 rounded-xl p-5"
      >
        <h2 className="text-lg font-heading font-bold mb-4 flex items-center gap-2">
          <BarChart3 className="w-5 h-5 text-cyan-500" />
          Dashboard Analítico
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 max-w-lg">
          <div>
            <Label className="text-xs text-muted-foreground mb-1.5 block">Time Mandante</Label>
            <TeamSelect 
              value={homeTeamId} 
              onValueChange={setHomeTeamId} 
              teams={teams.filter(t => t !== awayTeamId)} 
            />
          </div>
          <div>
            <Label className="text-xs text-muted-foreground mb-1.5 block">Time Visitante</Label>
            <TeamSelect 
              value={awayTeamId} 
              onValueChange={setAwayTeamId} 
              teams={teams.filter(t => t !== homeTeamId)} 
            />
          </div>
        </div>
      </motion.div>

      {!bothSelected && (
        <div className="text-center py-16 text-muted-foreground text-sm">
          Selecione duas equipes para visualizar as estatísticas comparativas.
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
          {/* Elo Rating History */}
          <div className="bg-card border border-border/50 rounded-xl p-5">
            <h3 className="text-sm font-semibold mb-1 flex items-center gap-1.5">
              <TrendingUp className="w-4 h-4 text-emerald-500" />
              Evolução do Elo Rating
              <InfoTooltip text="O Elo Rating é um sistema de classificação que mede a força relativa de cada equipe. Quanto maior o Elo, mais forte a equipe é considerada historicamente." />
            </h3>
            <p className="text-xs text-muted-foreground mb-4">Flutuação comparativa do poder histórico ao longo dos anos</p>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={eloHistoryData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.5} />
                  <XAxis dataKey="year" tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} />
                  <YAxis tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} domain={['auto', 'auto']} />
                  <RTooltip
                    contentStyle={{ backgroundColor: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: '8px', fontSize: '12px' }}
                    labelStyle={{ color: 'hsl(var(--foreground))' }}
                  />
                  <Legend wrapperStyle={{ fontSize: '12px' }} />
                  <Line type="monotone" dataKey={homeTeamId} stroke="#10b981" strokeWidth={2} dot={{ r: 3 }} />
                  <Line type="monotone" dataKey={awayTeamId} stroke="#06b6d4" strokeWidth={2} dot={{ r: 3 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Scatter Plot */}
          <div className="bg-card border border-border/50 rounded-xl p-5">
            <h3 className="text-sm font-semibold mb-1 flex items-center gap-1.5">
              <Target className="w-4 h-4 text-amber-500" />
              Matriz Comparativa de Quadrantes
              <InfoTooltip text="Gráfico de dispersão posicionando o ataque (gols/chutes feitos) e a defesa (gols/chutes sofridos) de cada seleção frente à média global. Quadrante superior-esquerdo = ataque forte e defesa sólida." />
            </h3>
            <p className="text-xs text-muted-foreground mb-4">Ataque vs Defesa — Gols por partida nos últimos 20 jogos</p>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <ScatterChart>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.5} />
                  <XAxis type="number" dataKey="attack" name="Ataque" tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} label={{ value: 'Ataque (Gols/Jogo)', position: 'insideBottom', offset: -5, style: { fontSize: 10, fill: 'hsl(var(--muted-foreground))' } }} />
                  <YAxis type="number" dataKey="defense" name="Defesa" tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} label={{ value: 'Defesa (Gols Sofridos/Jogo)', angle: -90, position: 'insideLeft', style: { fontSize: 10, fill: 'hsl(var(--muted-foreground))' } }} />
                  <RTooltip
                    contentStyle={{ backgroundColor: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: '8px', fontSize: '12px' }}
                    formatter={(value: any, name: any) => [Number(value).toFixed(2), name]}
                  />
                  <Legend wrapperStyle={{ fontSize: '12px' }} />
                  <Scatter name={homeTeamId} data={[{ attack: homeHistory.attack_avg || 0, defense: homeHistory.defense_avg || 0 }]} fill="#10b981" opacity={0.7} />
                  <Scatter name={awayTeamId} data={[{ attack: awayHistory.attack_avg || 0, defense: awayHistory.defense_avg || 0 }]} fill="#06b6d4" opacity={0.7} />
                </ScatterChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Frequency Distributions */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Corners */}
            <div className="bg-card border border-border/50 rounded-xl p-5">
              <h3 className="text-sm font-semibold mb-1 flex items-center gap-1.5">
                Distribuição de Escanteios
                <InfoTooltip text="Frequência histórica de escanteios nos últimos 20 jogos de cada equipe. A distribuição revela o padrão mais provável e desvios." />
              </h3>
              <p className="text-xs text-muted-foreground mb-4">Últimos 20 jogos</p>
              <div className="h-48">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={(homeHistory.corners_freq || []).map(h => ({
                    value: h.label,
                    [homeTeamId]: h.frequency,
                    [awayTeamId]: (awayHistory.corners_freq || []).find(a => a.label === h.label)?.frequency || 0,
                  }))}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.5} />
                    <XAxis dataKey="value" tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }} />
                    <YAxis tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }} />
                    <RTooltip contentStyle={{ backgroundColor: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: '8px', fontSize: '11px' }} />
                    <Legend wrapperStyle={{ fontSize: '11px' }} />
                    <Bar dataKey={homeTeamId} fill="#10b981" radius={[2, 2, 0, 0]} />
                    <Bar dataKey={awayTeamId} fill="#06b6d4" radius={[2, 2, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Cartões */}
            <div className="bg-card border border-border/50 rounded-xl p-5">
              <h3 className="text-sm font-semibold mb-1 flex items-center gap-1.5">
                Distribuição de Cartões
                <InfoTooltip text="Frequência histórica de cartões nos últimos 20 jogos de cada equipe. Útil para análise de mercados de cartões totais." />
              </h3>
              <p className="text-xs text-muted-foreground mb-4">Últimos 20 jogos</p>
              <div className="h-48">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={(homeHistory.cards_freq || []).map(h => ({
                    value: h.label,
                    [homeTeamId]: h.frequency,
                    [awayTeamId]: (awayHistory.cards_freq || []).find(a => a.label === h.label)?.frequency || 0,
                  }))}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.5} />
                    <XAxis dataKey="value" tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }} />
                    <YAxis tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }} />
                    <RTooltip contentStyle={{ backgroundColor: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: '8px', fontSize: '11px' }} />
                    <Legend wrapperStyle={{ fontSize: '11px' }} />
                    <Bar dataKey={homeTeamId} fill="#f59e0b" radius={[2, 2, 0, 0]} />
                    <Bar dataKey={awayTeamId} fill="#ef4444" radius={[2, 2, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          {/* H2H */}
          {h2h && (
            <div className="bg-card border border-border/50 rounded-xl p-5">
              <h3 className="text-sm font-semibold mb-1 flex items-center gap-1.5">
                <Users className="w-4 h-4 text-purple-500" />
                Confrontos Diretos (H2H)
                <InfoTooltip text="Histórico de confrontos diretos entre as duas seleções." />
              </h3>
              <div className="flex flex-wrap items-center gap-4 mb-4">
                <span className="text-xs text-muted-foreground">
                  Jogos: <span className="text-foreground font-semibold">{h2h.metrics.total_matches || h2h.metrics.h2h_played || "N/A"}</span>
                </span>
                <span className="text-xs text-muted-foreground">
                  Média de Gols: <span className="text-foreground font-semibold">
                    {h2h.metrics.avg_total_goals ? Number(h2h.metrics.avg_total_goals).toFixed(2) : "N/A"}
                  </span>
                </span>
                <span className="text-xs text-muted-foreground">
                  Ambas Marcam (BTTS): <span className="text-foreground font-semibold">
                    {h2h.metrics.btts_percentage ? `${Number(h2h.metrics.btts_percentage).toFixed(1)}%` : "N/A"}
                  </span>
                </span>
              </div>
              <div className="text-sm text-muted-foreground italic p-4 bg-muted/30 rounded-lg">
                {h2h.summary}
              </div>
            </div>
          )}
        </motion.div>
      )}
    </div>
  );
}
