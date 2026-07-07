"use client";
import React from "react";
import { RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar, ResponsiveContainer, Legend, Tooltip as RTooltip } from "recharts";
import { RecentMatch } from "@/lib/api";
import { teamPt } from "@/lib/teamNames";
import InfoTooltip from "@/components/platform/InfoTooltip";

function avg(ms: RecentMatch[], f: (m: RecentMatch) => number): number {
  const v = ms.map(f).filter((x) => Number.isFinite(x));
  return v.length ? v.reduce((a, b) => a + b, 0) / v.length : 0;
}
const clamp = (x: number) => Math.max(0, Math.min(100, x));

// Métricas de estilo (0–100) a partir dos jogos recentes com box-score.
function profile(ms: RecentMatch[]) {
  const gf = avg(ms, (m) => m.goals_scored);
  const ga = avg(ms, (m) => m.goals_conceded);
  const sh = avg(ms, (m) => m.sb_shots || 0);
  const sot = avg(ms, (m) => m.sb_shots_on_target || 0);
  const co = avg(ms, (m) => m.sb_corners || 0);
  const ca = avg(ms, (m) => m.sb_cards || 0);
  return {
    "Ataque": clamp((gf / 2.5) * 100),                       // gols/jogo (2.5 = topo)
    "Finalização": clamp((sot / 6) * 100),                   // chutes a gol/jogo
    "Volume ofensivo": clamp((sh / 16) * 100),               // finalizações/jogo
    "Pressão": clamp((co / 7) * 100),                        // escanteios/jogo
    "Solidez defensiva": clamp((1 - ga / 2.5) * 100),        // inverso de gols sofridos
    "Disciplina": clamp((1 - ca / 5) * 100),                 // inverso de cartões
  };
}

export default function StyleRadar({ home, away, homeMatches, awayMatches }: {
  home: string; away: string; homeMatches: RecentMatch[]; awayMatches: RecentMatch[];
}) {
  if ((homeMatches?.length ?? 0) === 0 && (awayMatches?.length ?? 0) === 0) return null;
  const ph = profile(homeMatches || []); const pa = profile(awayMatches || []);
  const data = Object.keys(ph).map((k) => ({ metric: k, [home]: Math.round((ph as any)[k]), [away]: Math.round((pa as any)[k]) }));
  return (
    <div className="bg-card border border-border/50 rounded-xl p-5">
      <h3 className="text-sm font-semibold mb-1 flex items-center gap-1.5">
        Radar de Estilo de Jogo
        <InfoTooltip text="Perfil comparativo (0–100) das duas seleções nos jogos recentes: ataque (gols), finalização (chutes a gol), volume ofensivo (finalizações), pressão (escanteios), solidez defensiva (inverso de gols sofridos) e disciplina (inverso de cartões). Quanto mais para fora, mais forte naquele quesito." />
      </h3>
      <p className="text-xs text-muted-foreground mb-2">Perfil dos últimos jogos com estatística avançada</p>
      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <RadarChart data={data} outerRadius="72%">
            <PolarGrid stroke="hsl(var(--border))" opacity={0.5} />
            <PolarAngleAxis dataKey="metric" tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }} />
            <PolarRadiusAxis domain={[0, 100]} tick={{ fontSize: 9, fill: "hsl(var(--muted-foreground))" }} angle={90} />
            <Radar name={teamPt(home)} dataKey={home} stroke="#10b981" fill="#10b981" fillOpacity={0.3} />
            <Radar name={teamPt(away)} dataKey={away} stroke="#f97316" fill="#f97316" fillOpacity={0.25} />
            <Legend verticalAlign="top" height={28} wrapperStyle={{ fontSize: "12px" }} />
            <RTooltip contentStyle={{ backgroundColor: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: "8px", fontSize: "11px" }} />
          </RadarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
