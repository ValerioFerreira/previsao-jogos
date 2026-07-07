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

// Explicação de cada vértice (balão no hover via <title> SVG nativo).
const EXPLAIN: Record<string, string> = {
  "Ataque": "Gols marcados por jogo (escala: 2,5 gols = 100).",
  "Finalização": "Chutes a gol por jogo (escala: 6 = 100).",
  "Volume ofensivo": "Finalizações totais por jogo (escala: 16 = 100).",
  "Pressão": "Escanteios por jogo (escala: 7 = 100).",
  "Solidez defensiva": "Inverso dos gols sofridos por jogo (menos sofre, maior).",
  "Disciplina": "Inverso dos cartões por jogo (menos cartões, maior).",
};

function AngleTick({ x, y, cx, cy, payload }: any) {
  const label: string = payload?.value ?? "";
  const anchor = x > cx + 6 ? "start" : x < cx - 6 ? "end" : "middle";
  const dx = x > cx + 6 ? 4 : x < cx - 6 ? -4 : 0;
  return (
    <text x={x + dx} y={y} dy={4} textAnchor={anchor} fontSize={9.5} fill="hsl(var(--muted-foreground))" style={{ cursor: "help" }}>
      <title>{EXPLAIN[label] || label}</title>
      {label}
    </text>
  );
}

export default function StyleRadar({ home, away, homeMatches, awayMatches }: {
  home: string; away: string; homeMatches: RecentMatch[]; awayMatches: RecentMatch[];
}) {
  if ((homeMatches?.length ?? 0) === 0 && (awayMatches?.length ?? 0) === 0) return null;
  const ph = profile(homeMatches || []); const pa = profile(awayMatches || []);
  const data = Object.keys(ph).map((k) => ({ metric: k, [home]: Math.round((ph as any)[k]), [away]: Math.round((pa as any)[k]) }));
  return (
    <div className="bg-card border border-border/50 rounded-xl p-5 h-full flex flex-col">
      <h3 className="text-sm font-semibold mb-1 flex items-center gap-1.5">
        Radar de Estilo
        <InfoTooltip text="Perfil comparativo (0–100) das duas seleções nos jogos recentes. Passe o mouse sobre cada vértice para ver o que o indicador mede. Quanto mais para fora, mais forte naquele quesito." />
      </h3>
      <p className="text-xs text-muted-foreground mb-1">Passe o mouse nos vértices para detalhes</p>
      <div className="flex-1 min-h-[260px]">
        <ResponsiveContainer width="100%" height="100%">
          <RadarChart data={data} outerRadius="68%">
            <PolarGrid stroke="hsl(var(--border))" opacity={0.5} />
            <PolarAngleAxis dataKey="metric" tick={<AngleTick />} />
            <PolarRadiusAxis domain={[0, 100]} tick={{ fontSize: 8, fill: "hsl(var(--muted-foreground))" }} angle={90} />
            <Radar name={teamPt(home)} dataKey={home} stroke="#10b981" fill="#10b981" fillOpacity={0.3} />
            <Radar name={teamPt(away)} dataKey={away} stroke="#f97316" fill="#f97316" fillOpacity={0.25} />
            <Legend verticalAlign="top" height={24} wrapperStyle={{ fontSize: "11px" }} />
            <RTooltip contentStyle={{ backgroundColor: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: "8px", fontSize: "11px" }} />
          </RadarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
