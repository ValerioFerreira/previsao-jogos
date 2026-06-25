"use client";
import React, { useState, useMemo } from 'react';
import { motion } from 'framer-motion';
import { Label } from '@/components/ui/label';
import { BarChart3, TrendingUp, Target, Users } from 'lucide-react';
import { BarChart, Bar, LineChart, Line, ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip as RTooltip, Legend, ResponsiveContainer } from 'recharts';
import { api, TeamHistoryResponse, H2HResponse, MatchDetail as MatchDetailT } from '@/lib/api';
import InfoTooltip from '@/components/platform/InfoTooltip';
import { usePrediction } from '@/lib/PredictionContext';
import { TeamSelect } from '@/components/platform/TeamSelect';
import { teamPt } from '@/lib/teamNames';
import { MatchDetail } from '@/components/platform/MatchDetail';
import { MatchModePicker } from '@/components/platform/MatchModePicker';
import { MatchHeader } from '@/components/platform/MatchHeader';
import { ArrowLeft } from 'lucide-react';

export default function Estatisticas() {
  const [teams, setTeams] = React.useState<string[]>([]);
  
  const { homeTeamId, setHomeTeamId, awayTeamId, setAwayTeamId } = usePrediction();
  const [loading, setLoading] = useState(false);
  
  const [homeHistory, setHomeHistory] = useState<TeamHistoryResponse | null>(null);
  const [awayHistory, setAwayHistory] = useState<TeamHistoryResponse | null>(null);
  const [h2h, setH2h] = useState<H2HResponse | null>(null);

  // Detalhe de uma partida específica (via ?home=&away=&date= ou seletor de passadas).
  const [matchParams, setMatchParams] = useState<{ home: string; away: string; date: string } | null>(null);
  const [matchData, setMatchData] = useState<MatchDetailT | null>(null);
  const [matchLoading, setMatchLoading] = useState(false);
  const [pickerMode, setPickerMode] = useState<'futura' | 'passada' | 'independente'>('independente');
  const [teamIds, setTeamIds] = useState<Record<string, number>>({});
  const [matchDate, setMatchDate] = useState<string | undefined>(undefined);

  const openMatch = (home: string, away: string, date: string) => {
    setMatchParams({ home, away, date });
    setMatchLoading(true);
    api.matchDetail(home, away, date).then(setMatchData).catch(() => setMatchData({ found: false })).finally(() => setMatchLoading(false));
  };

  React.useEffect(() => {
    api.teams().then(res => setTeams(res.teams)).catch(console.error);
    api.teamIds().then(setTeamIds).catch(() => {});
    const sp = new URLSearchParams(window.location.search);
    const home = sp.get('home'), away = sp.get('away'), date = sp.get('date');
    if (home && away && date) openMatch(home, away, date);
  }, []);

  const clearMatch = () => {
    setMatchParams(null);
    setMatchData(null);
    window.history.replaceState(null, '', '/estatisticas');
  };

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

  // Modo "detalhe de partida": acionado ao clicar num jogo recente (Previsões).
  if (matchParams) {
    return (
      <div className="space-y-6">
        <button onClick={clearMatch} className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors">
          <ArrowLeft className="w-4 h-4" /> Voltar ao painel comparativo
        </button>
        <h2 className="text-lg font-heading font-bold flex items-center gap-2">
          <BarChart3 className="w-5 h-5 text-cyan-500" />
          Detalhe da Partida
        </h2>
        {matchLoading ? (
          <div className="flex justify-center py-12"><div className="w-8 h-8 border-4 border-slate-200 border-t-cyan-500 rounded-full animate-spin" /></div>
        ) : matchData ? (
          <MatchDetail data={matchData} />
        ) : null}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {bothSelected && (
        <MatchHeader home={homeTeamId} away={awayTeamId} teamIds={teamIds} date={matchDate} />
      )}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="bg-card border border-border/50 rounded-xl p-5"
      >
        <h2 className="text-lg font-heading font-bold mb-4 flex items-center gap-2">
          <BarChart3 className="w-5 h-5 text-cyan-500" />
          Dashboard Analítico
        </h2>
        <MatchModePicker
          showReferee={false}
          onModeChange={(m) => { setPickerMode(m); if (m !== 'futura') setMatchDate(undefined); }}
          onSelectFuture={(fx) => setMatchDate(fx.date)}
          onSelectPast={(fx) => openMatch(fx.home, fx.away, (fx.date || '').slice(0, 10))}
        />
        {pickerMode === 'independente' && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 max-w-lg">
            <div>
              <Label className="text-xs text-muted-foreground mb-1.5 block">Time Mandante</Label>
              <TeamSelect value={homeTeamId} onValueChange={setHomeTeamId} teams={teams.filter(t => t !== awayTeamId)} />
            </div>
            <div>
              <Label className="text-xs text-muted-foreground mb-1.5 block">Time Visitante</Label>
              <TeamSelect value={awayTeamId} onValueChange={setAwayTeamId} teams={teams.filter(t => t !== homeTeamId)} />
            </div>
          </div>
        )}
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
                  <Line type="monotone" dataKey={awayTeamId} name={teamPt(awayTeamId)} stroke="#06b6d4" strokeWidth={2} dot={{ r: 3 }} connectNulls />
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
                <ScatterChart margin={{ top: 8, right: 24, bottom: 28, left: 16 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.5} />
                  <XAxis type="number" dataKey="attack" name="Ataque" tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} label={{ value: 'Ataque (gols/jogo)', position: 'insideBottom', offset: -8, style: { fontSize: 10, fill: 'hsl(var(--muted-foreground))', textAnchor: 'middle' } }} />
                  <YAxis type="number" dataKey="defense" name="Defesa" tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} label={{ value: 'Defesa (gols sofridos/jogo)', angle: -90, position: 'insideLeft', offset: 6, style: { fontSize: 10, fill: 'hsl(var(--muted-foreground))', textAnchor: 'middle' } }} />
                  <RTooltip
                    contentStyle={{ backgroundColor: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: '8px', fontSize: '12px' }}
                    formatter={(value: any, name: any) => [Number(value).toFixed(2), name]}
                  />
                  <Legend verticalAlign="top" height={28} wrapperStyle={{ fontSize: '12px' }} />
                  <Scatter name={teamPt(homeTeamId)} data={[{ attack: homeHistory.attack_avg || 0, defense: homeHistory.defense_avg || 0 }]} fill="#10b981" opacity={0.7} />
                  <Scatter name={teamPt(awayTeamId)} data={[{ attack: awayHistory.attack_avg || 0, defense: awayHistory.defense_avg || 0 }]} fill="#06b6d4" opacity={0.7} />
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
                  <BarChart margin={{ top: 5, right: 8, bottom: 22, left: 4 }} data={(homeHistory.corners_freq || []).map(h => ({
                    value: h.label,
                    [homeTeamId]: h.frequency,
                    [awayTeamId]: (awayHistory.corners_freq || []).find(a => a.label === h.label)?.frequency || 0,
                  }))}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.5} />
                    <XAxis dataKey="value" tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }} label={{ value: 'Escanteios na partida', position: 'insideBottom', offset: -10, style: { fontSize: 9, fill: 'hsl(var(--muted-foreground))' } }} />
                    <YAxis allowDecimals={false} tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }} label={{ value: 'Nº de jogos', angle: -90, position: 'insideLeft', style: { fontSize: 9, fill: 'hsl(var(--muted-foreground))', textAnchor: 'middle' } }} />
                    <RTooltip contentStyle={{ backgroundColor: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: '8px', fontSize: '11px' }} />
                    <Legend wrapperStyle={{ fontSize: '11px' }} />
                    <Bar dataKey={homeTeamId} name={teamPt(homeTeamId)} fill="#10b981" radius={[2, 2, 0, 0]} />
                    <Bar dataKey={awayTeamId} name={teamPt(awayTeamId)} fill="#06b6d4" radius={[2, 2, 0, 0]} />
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
                  <BarChart margin={{ top: 5, right: 8, bottom: 22, left: 4 }} data={(homeHistory.cards_freq || []).map(h => ({
                    value: h.label,
                    [homeTeamId]: h.frequency,
                    [awayTeamId]: (awayHistory.cards_freq || []).find(a => a.label === h.label)?.frequency || 0,
                  }))}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.5} />
                    <XAxis dataKey="value" tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }} label={{ value: 'Cartões na partida', position: 'insideBottom', offset: -10, style: { fontSize: 9, fill: 'hsl(var(--muted-foreground))' } }} />
                    <YAxis allowDecimals={false} tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }} label={{ value: 'Nº de jogos', angle: -90, position: 'insideLeft', style: { fontSize: 9, fill: 'hsl(var(--muted-foreground))', textAnchor: 'middle' } }} />
                    <RTooltip contentStyle={{ backgroundColor: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: '8px', fontSize: '11px' }} />
                    <Legend wrapperStyle={{ fontSize: '11px' }} />
                    <Bar dataKey={homeTeamId} name={teamPt(homeTeamId)} fill="#f59e0b" radius={[2, 2, 0, 0]} />
                    <Bar dataKey={awayTeamId} name={teamPt(awayTeamId)} fill="#ef4444" radius={[2, 2, 0, 0]} />
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
