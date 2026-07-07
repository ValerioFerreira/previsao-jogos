"use client";
import React from "react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, ReferenceLine, Tooltip as RTooltip, ResponsiveContainer } from "recharts";
import { GoalTimingResponse } from "@/lib/api";
import { teamPt } from "@/lib/teamNames";
import InfoTooltip from "@/components/platform/InfoTooltip";

type Row = { label: string; scoredPct: number; concededPct: number; scored: number; conceded: number };

function build(d: GoalTimingResponse): Row[] {
  const ts = d.total_scored || 1, tc = d.total_conceded || 1;
  return d.blocks.map((b) => ({
    label: b.label,
    scoredPct: +((b.scored / ts) * 100).toFixed(1),
    concededPct: -+((b.conceded / tc) * 100).toFixed(1), // negativo -> abaixo do zero
    scored: b.scored,
    conceded: b.conceded,
  }));
}

function peak(rows: Row[], key: "scored" | "conceded"): string {
  let best = rows[0]; for (const r of rows) if (r[key] > best[key]) best = r;
  return best.label;
}

function TeamTiming({ team, data, accent }: { team: string; data: GoalTimingResponse; accent: string }) {
  const rows = build(data);
  const maxAbs = Math.max(5, ...rows.map((r) => Math.max(r.scoredPct, -r.concededPct)));

  const Tip = ({ active, payload, label }: any) => {
    if (!active || !payload?.length) return null;
    const r = rows.find((x) => x.label === label);
    if (!r) return null;
    return (
      <div className="rounded-lg border border-border/60 bg-popover shadow-xl p-2 text-[11px]">
        <p className="font-medium mb-0.5">{label} min</p>
        <p style={{ color: accent }}>Marcados: {r.scored} <span className="text-muted-foreground">({r.scoredPct}%)</span></p>
        <p className="text-red-400">Sofridos: {r.conceded} <span className="text-muted-foreground">({-r.concededPct}%)</span></p>
      </div>
    );
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="text-sm font-semibold">{teamPt(team)}</span>
        <span className="text-[11px] text-muted-foreground">{data.n_matches} jogos · {data.total_scored}⚽ / {data.total_conceded} sofridos</span>
      </div>
      <div className="h-40">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} margin={{ top: 4, right: 4, bottom: 0, left: -24 }} barCategoryGap="18%">
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.3} vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 9, fill: "hsl(var(--muted-foreground))" }} />
            <YAxis domain={[-maxAbs, maxAbs]} tick={{ fontSize: 9, fill: "hsl(var(--muted-foreground))" }} width={30} tickFormatter={(v) => `${Math.abs(v)}%`} />
            <ReferenceLine y={0} stroke="hsl(var(--border))" />
            <RTooltip content={<Tip />} cursor={{ fill: "hsl(var(--muted))", opacity: 0.25 }} />
            <Bar dataKey="scoredPct" radius={[3, 3, 0, 0]} fill={accent} />
            <Bar dataKey="concededPct" radius={[0, 0, 3, 3]} fill="#ef4444" fillOpacity={0.75} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p className="text-[11px] text-muted-foreground mt-1">
        <span style={{ color: accent }}>▲</span> marca mais em <b>{peak(rows, "scored")}′</b> · <span className="text-red-400">▼</span> mais vulnerável em <b>{peak(rows, "conceded")}′</b>
      </p>
    </div>
  );
}

export default function GoalTiming({ home, homeData, away, awayData }: {
  home: string; homeData: GoalTimingResponse | null; away: string; awayData: GoalTimingResponse | null;
}) {
  const hasH = homeData && homeData.n_matches > 0;
  const hasA = awayData && awayData.n_matches > 0;
  if (!hasH && !hasA) return null;
  return (
    <div className="bg-card border border-border/50 rounded-xl p-5">
      <h3 className="text-sm font-semibold mb-1 flex items-center gap-1.5">
        Minutagem de Gols
        <InfoTooltip text="Distribuição percentual dos gols marcados (acima) e sofridos (abaixo) por faixa de 15 minutos, no histórico com detalhe da seleção. Mostra QUANDO cada equipe tende a marcar e a ser mais vulnerável." />
      </h3>
      <p className="text-xs text-muted-foreground mb-3">% dos gols por faixa de 15′ (acréscimos entram na faixa do tempo)</p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-4">
        {hasH && <TeamTiming team={home} data={homeData!} accent="#10b981" />}
        {hasA && <TeamTiming team={away} data={awayData!} accent="#f97316" />}
      </div>
    </div>
  );
}
