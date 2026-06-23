import React, { useState, useMemo } from 'react';
import { motion } from 'framer-motion';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Label } from '@/components/ui/label';
import { BarChart3, TrendingUp, Target, Users } from 'lucide-react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RTooltip,
  ResponsiveContainer, ScatterChart, Scatter, BarChart, Bar, Legend, Cell,
} from 'recharts';
import { TEAMS, generateProjection, generateScatterData, generateFrequencyData } from '@/lib/mock-data';
import InfoTooltip from '@/components/platform/InfoTooltip';

export default function Estatisticas() {
  const [homeTeamId, setHomeTeamId] = useState('');
  const [awayTeamId, setAwayTeamId] = useState('');

  const homeTeam = TEAMS.find(t => t.id.toString() === homeTeamId);
  const awayTeam = TEAMS.find(t => t.id.toString() === awayTeamId);
  const bothSelected = homeTeam && awayTeam && homeTeamId !== awayTeamId;

  const data = useMemo(() => {
    if (!bothSelected) return null;
    const proj = generateProjection(homeTeam, awayTeam);
    const scatter = generateScatterData(homeTeam, awayTeam);
    const homeCorners = generateFrequencyData(homeTeam.name, 'escanteios');
    const awayCorners = generateFrequencyData(awayTeam.name, 'escanteios');
    const homeCards = generateFrequencyData(homeTeam.name, 'cartoes');
    const awayCards = generateFrequencyData(awayTeam.name, 'cartoes');
    return { proj, scatter, homeCorners, awayCorners, homeCards, awayCards };
  }, [homeTeamId, awayTeamId]);

  return (
    <div className="space-y-6">
      {/* Selection */}
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
            <Select value={homeTeamId} onValueChange={setHomeTeamId}>
              <SelectTrigger className="h-10"><SelectValue placeholder="Selecione..." /></SelectTrigger>
              <SelectContent>
                {TEAMS.filter(t => t.id.toString() !== awayTeamId).map(t => (
                  <SelectItem key={t.id} value={t.id.toString()}>{t.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs text-muted-foreground mb-1.5 block">Time Visitante</Label>
            <Select value={awayTeamId} onValueChange={setAwayTeamId}>
              <SelectTrigger className="h-10"><SelectValue placeholder="Selecione..." /></SelectTrigger>
              <SelectContent>
                {TEAMS.filter(t => t.id.toString() !== homeTeamId).map(t => (
                  <SelectItem key={t.id} value={t.id.toString()}>{t.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      </motion.div>

      {!bothSelected && (
        <div className="text-center py-16 text-muted-foreground text-sm">
          Selecione duas equipes para visualizar as estatísticas comparativas.
        </div>
      )}

      {bothSelected && data && (
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
                <LineChart data={data.proj.eloHistory}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.5} />
                  <XAxis dataKey="year" tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} />
                  <YAxis tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} domain={['auto', 'auto']} />
                  <RTooltip
                    contentStyle={{ backgroundColor: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: '8px', fontSize: '12px' }}
                    labelStyle={{ color: 'hsl(var(--foreground))' }}
                  />
                  <Legend wrapperStyle={{ fontSize: '12px' }} />
                  <Line type="monotone" dataKey={homeTeam.name} stroke="#10b981" strokeWidth={2} dot={{ r: 3 }} />
                  <Line type="monotone" dataKey={awayTeam.name} stroke="#06b6d4" strokeWidth={2} dot={{ r: 3 }} />
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
                    formatter={(value, name) => [value.toFixed(2), name]}
                  />
                  <Legend wrapperStyle={{ fontSize: '12px' }} />
                  <Scatter name={homeTeam.name} data={data.scatter.homeData} fill="#10b981" opacity={0.7} />
                  <Scatter name={awayTeam.name} data={data.scatter.awayData} fill="#06b6d4" opacity={0.7} />
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
                  <BarChart data={data.homeCorners.map((h, i) => ({
                    value: h.label,
                    [homeTeam.name]: h.frequency,
                    [awayTeam.name]: data.awayCorners[i]?.frequency || 0,
                  }))}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.5} />
                    <XAxis dataKey="value" tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }} />
                    <YAxis tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }} />
                    <RTooltip contentStyle={{ backgroundColor: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: '8px', fontSize: '11px' }} />
                    <Legend wrapperStyle={{ fontSize: '11px' }} />
                    <Bar dataKey={homeTeam.name} fill="#10b981" radius={[2, 2, 0, 0]} />
                    <Bar dataKey={awayTeam.name} fill="#06b6d4" radius={[2, 2, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Cards */}
            <div className="bg-card border border-border/50 rounded-xl p-5">
              <h3 className="text-sm font-semibold mb-1 flex items-center gap-1.5">
                Distribuição de Cartões
                <InfoTooltip text="Frequência histórica de cartões nos últimos 20 jogos de cada equipe. Útil para análise de mercados de cartões totais." />
              </h3>
              <p className="text-xs text-muted-foreground mb-4">Últimos 20 jogos</p>
              <div className="h-48">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={data.homeCards.map((h, i) => ({
                    value: h.label,
                    [homeTeam.name]: h.frequency,
                    [awayTeam.name]: data.awayCards[i]?.frequency || 0,
                  }))}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.5} />
                    <XAxis dataKey="value" tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }} />
                    <YAxis tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }} />
                    <RTooltip contentStyle={{ backgroundColor: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: '8px', fontSize: '11px' }} />
                    <Legend wrapperStyle={{ fontSize: '11px' }} />
                    <Bar dataKey={homeTeam.name} fill="#f59e0b" radius={[2, 2, 0, 0]} />
                    <Bar dataKey={awayTeam.name} fill="#ef4444" radius={[2, 2, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          {/* H2H */}
          <div className="bg-card border border-border/50 rounded-xl p-5">
            <h3 className="text-sm font-semibold mb-1 flex items-center gap-1.5">
              <Users className="w-4 h-4 text-purple-500" />
              Confrontos Diretos (H2H)
              <InfoTooltip text="Histórico de confrontos diretos entre as duas seleções. O saldo de gols médio (h2h_home_gd_mean) contextualiza a vantagem histórica do mandante." />
            </h3>
            <div className="flex items-center gap-4 mb-4">
              <span className="text-xs text-muted-foreground">
                Total de Jogos: <span className="text-foreground font-semibold">{data.proj.h2h.totalGames}</span>
              </span>
              <span className="text-xs text-muted-foreground">
                Saldo de Gols Médio (Mandante): <span className={`font-semibold font-mono ${data.proj.h2h.avgGoalDiff >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {data.proj.h2h.avgGoalDiff > 0 ? '+' : ''}{data.proj.h2h.avgGoalDiff}
                </span>
              </span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-border/50">
                    <th className="text-left py-2 px-3 text-muted-foreground font-medium">Ano</th>
                    <th className="text-left py-2 px-3 text-muted-foreground font-medium">Competição</th>
                    <th className="text-center py-2 px-3 text-muted-foreground font-medium">{homeTeam.name}</th>
                    <th className="text-center py-2 px-3 text-muted-foreground font-medium">Placar</th>
                    <th className="text-center py-2 px-3 text-muted-foreground font-medium">{awayTeam.name}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.proj.h2h.matches.map((m, i) => {
                    const diff = m.homeGoals - m.awayGoals;
                    return (
                      <tr key={i} className="border-b border-border/30 hover:bg-muted/30 transition-colors">
                        <td className="py-2 px-3 font-mono">{m.year}</td>
                        <td className="py-2 px-3 text-muted-foreground truncate max-w-[150px]">{m.competition}</td>
                        <td className="py-2 px-3 text-center">
                          <span className={`inline-block w-5 h-5 rounded text-[10px] font-bold leading-5 ${diff > 0 ? 'bg-emerald-500/20 text-emerald-400' : diff < 0 ? 'bg-red-500/20 text-red-400' : 'bg-amber-500/20 text-amber-400'}`}>
                            {diff > 0 ? 'V' : diff < 0 ? 'D' : 'E'}
                          </span>
                        </td>
                        <td className="py-2 px-3 text-center font-mono font-semibold">{m.homeGoals} - {m.awayGoals}</td>
                        <td className="py-2 px-3 text-center">
                          <span className={`inline-block w-5 h-5 rounded text-[10px] font-bold leading-5 ${diff < 0 ? 'bg-emerald-500/20 text-emerald-400' : diff > 0 ? 'bg-red-500/20 text-red-400' : 'bg-amber-500/20 text-amber-400'}`}>
                            {diff < 0 ? 'V' : diff > 0 ? 'D' : 'E'}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </motion.div>
      )}
    </div>
  );
}