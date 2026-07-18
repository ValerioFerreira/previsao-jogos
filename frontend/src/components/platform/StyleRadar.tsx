"use client";
import React from "react";
import { RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar, ResponsiveContainer, Legend, Tooltip as RTooltip } from "recharts";
import { RecentMatch } from "@/lib/api";
import { teamPt } from "@/lib/teamNames";
import InfoTooltip from "@/components/platform/InfoTooltip";
import { getRelevantMatches } from "@/lib/teamInsights";

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

// Balão custom da tooltip: aparece ao passar o mouse sobre um vértice do radar,
// com o nome do indicador, sua explicação curta e o valor de cada seleção.
function VertexTooltip({ active, payload, home, away }: any) {
  if (!active || !payload || !payload.length) return null;
  const metric: string = payload[0]?.payload?.metric ?? "";
  return (
    <div className="rounded-lg border border-border bg-popover shadow-xl p-2.5 text-xs max-w-[220px]">
      <p className="font-semibold mb-1">{metric}</p>
      {EXPLAIN[metric] && <p className="text-muted-foreground mb-1.5 leading-snug">{EXPLAIN[metric]}</p>}
      {payload.map((p: any) => (
        <p key={p.dataKey} className="flex items-center justify-between gap-3">
          <span style={{ color: p.color }}>{teamPt(p.dataKey === home ? home : away)}</span>
          <span className="font-mono font-bold" style={{ color: p.color }}>{p.value}</span>
        </p>
      ))}
    </div>
  );
}

export default function StyleRadar({ home, away, homeMatches, awayMatches, targetCompetition }: {
  home: string; away: string; homeMatches: RecentMatch[]; awayMatches: RecentMatch[];
  targetCompetition?: string;
}) {
  if ((homeMatches?.length ?? 0) === 0 && (awayMatches?.length ?? 0) === 0) return null;
  
  const homeMatches10 = React.useMemo(() => getRelevantMatches(homeMatches || [], targetCompetition, 10), [homeMatches, targetCompetition]);
  const awayMatches10 = React.useMemo(() => getRelevantMatches(awayMatches || [], targetCompetition, 10), [awayMatches, targetCompetition]);

  const ph = profile(homeMatches10); const pa = profile(awayMatches10);
  const data = Object.keys(ph).map((k) => ({ metric: k, [home]: Math.round((ph as any)[k]), [away]: Math.round((pa as any)[k]) }));
  return (
    <div className="bg-card border border-border/50 rounded-xl p-5 h-full flex flex-col justify-between">
      <div>
        <h3 className="text-sm font-semibold mb-1 flex items-center gap-1.5">
          Radar de Estilo
          <InfoTooltip text="Perfil comparativo (0–100) das duas equipes nos jogos recentes. Passe o mouse sobre cada vértice para ver o que o indicador mede. Quanto mais para fora, mais forte naquele quesito." />
        </h3>
        <p className="text-xs text-muted-foreground mb-1">Passe o mouse nos vértices para detalhes</p>
        <div className="flex-1 min-h-[260px] relative">
          <ResponsiveContainer width="100%" height="100%">
            <RadarChart data={data} outerRadius="50%" margin={{ top: 10, right: 10, bottom: 10, left: 10 }}>
              <PolarGrid stroke="hsl(var(--border))" opacity={0.5} />
              <PolarAngleAxis dataKey="metric" tick={<AngleTick />} />
              <PolarRadiusAxis domain={[0, 100]} tick={{ fontSize: 8, fill: "hsl(var(--muted-foreground))" }} angle={90} />
              <Radar name={teamPt(home)} dataKey={home} stroke="#10b981" fill="#10b981" fillOpacity={0.3} dot={{ r: 3, fill: "#10b981", stroke: "hsl(var(--card))", strokeWidth: 1 }} activeDot={{ r: 5, cursor: "pointer" }} />
              <Radar name={teamPt(away)} dataKey={away} stroke="#f97316" fill="#f97316" fillOpacity={0.25} dot={{ r: 3, fill: "#f97316", stroke: "hsl(var(--card))", strokeWidth: 1 }} activeDot={{ r: 5, cursor: "pointer" }} />
              <Legend verticalAlign="top" height={24} wrapperStyle={{ fontSize: "11px" }} />
              <RTooltip content={<VertexTooltip home={home} away={away} />} />
            </RadarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Legenda dos Vértices */}
      <div className="mt-auto pt-4 border-t border-border/30 text-[10px] text-muted-foreground grid grid-cols-2 gap-x-4 gap-y-2 leading-relaxed">
        <div>
          <span className="font-semibold text-foreground/90 block sm:inline">Ataque:</span>
          <span className="sm:ml-1">Média de gols marcados</span>
        </div>
        <div>
          <span className="font-semibold text-foreground/90 block sm:inline">Solidez Defensiva:</span>
          <span className="sm:ml-1">Eficiência (menos sofridos)</span>
        </div>
        <div>
          <span className="font-semibold text-foreground/90 block sm:inline">Finalização:</span>
          <span className="sm:ml-1">Média de chutes no gol</span>
        </div>
        <div>
          <span className="font-semibold text-foreground/90 block sm:inline">Disciplina:</span>
          <span className="sm:ml-1">Inverso de cartões recebidos</span>
        </div>
        <div>
          <span className="font-semibold text-foreground/90 block sm:inline">Volume Ofensivo:</span>
          <span className="sm:ml-1">Total de finalizações criadas</span>
        </div>
        <div>
          <span className="font-semibold text-foreground/90 block sm:inline">Pressão:</span>
          <span className="sm:ml-1">Média de escanteios cobrados</span>
        </div>
      </div>
    </div>
  );
}
