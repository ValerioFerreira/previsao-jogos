"use client";
import React from "react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, ReferenceLine, Tooltip as RTooltip, ResponsiveContainer, Cell } from "recharts";
import { PmfPreviewResponse } from "@/lib/api";
import { teamPt } from "@/lib/teamNames";
import InfoTooltip from "@/components/platform/InfoTooltip";
import { useRouter } from "next/navigation";

export default function PmfPreview({ data }: { data: PmfPreviewResponse | null }) {
  const router = useRouter();
  if (!data || !data.distribution || data.distribution.length === 0) return null;

  // Agrupa a cauda em "8+" e monta os pontos (marcados/under vs over 2.5).
  const CAP = 8;
  const rows = data.distribution.reduce<{ k: number; label: string; pct: number; over: boolean }[]>((acc, p, k) => {
    const bucket = Math.min(k, CAP);
    const existing = acc.find((r) => r.k === bucket);
    const pct = p * 100;
    if (existing) existing.pct += pct;
    else acc.push({ k: bucket, label: bucket === CAP ? "8+" : String(bucket), pct, over: bucket >= 3 });
    return acc;
  }, []);

  const eg = data.expected_goals;
  const Tip = ({ active, payload }: any) => {
    if (!active || !payload?.length) return null;
    const r = payload[0].payload;
    return (
      <div className="rounded-lg border border-border/60 bg-popover shadow-xl p-2 text-[11px]">
        <p><b>{r.label}</b> gol(s) na partida</p>
        <p className="text-muted-foreground">Probabilidade: {r.pct.toFixed(1)}%</p>
      </div>
    );
  };

  return (
    <div className="bg-card border border-border/50 rounded-xl p-5">
      <h3 className="text-sm font-semibold mb-1 flex items-center gap-1.5">
        Prévia de Gols (Modelo)
        <InfoTooltip text="Distribuição de probabilidade do total de gols na partida, do modelo Dixon-Coles. Verde = 3+ gols (Mais de 2,5), cinza = até 2 gols (Menos de 2,5). Prévia gratuita — a análise completa (todos os mercados, placares, por equipe) fica na página Análise." />
      </h3>
      <p className="text-xs text-muted-foreground mb-3">Distribuição do total de gols · linha principal Over/Under 2,5</p>

      <div className="flex flex-wrap items-center gap-x-6 gap-y-1 mb-2 text-xs">
        {eg != null && <span>Gols esperados: <b className="font-mono">{eg.toFixed(1)}</b></span>}
        <span className="text-emerald-400">Mais de 2,5: <b className="font-mono">{data.prob_over_2_5?.toFixed(1)}%</b>{data.odd_over_2_5 && <span className="text-muted-foreground"> · odd {data.odd_over_2_5.toFixed(2)}</span>}</span>
        <span className="text-muted-foreground">Menos de 2,5: <b className="font-mono text-foreground">{data.prob_over_2_5 != null ? (100 - data.prob_over_2_5).toFixed(1) : "-"}%</b>{data.odd_under_2_5 && <span> · odd {data.odd_under_2_5.toFixed(2)}</span>}</span>
      </div>

      <div className="h-44">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} margin={{ top: 4, right: 8, bottom: 0, left: -22 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.3} vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }} />
            <YAxis tick={{ fontSize: 9, fill: "hsl(var(--muted-foreground))" }} width={30} tickFormatter={(v) => `${v}%`} />
            <ReferenceLine x="2" stroke="#f97316" strokeDasharray="4 3" label={{ value: "2,5", fontSize: 9, fill: "#f97316", position: "top" }} />
            <RTooltip content={<Tip />} cursor={{ fill: "hsl(var(--muted))", opacity: 0.25 }} />
            <Bar dataKey="pct" radius={[3, 3, 0, 0]}>
              {rows.map((r, i) => <Cell key={i} fill={r.over ? "#10b981" : "#64748b"} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* 1X2 resumido */}
      {(data.prob_home != null && data.prob_away != null) && (
        <div className="mt-3">
          <div className="h-2 rounded-full overflow-hidden flex text-[0px]">
            <div style={{ width: `${data.prob_home}%`, backgroundColor: "#10b981" }} />
            <div style={{ width: `${data.prob_draw ?? 0}%`, backgroundColor: "#64748b" }} />
            <div style={{ width: `${data.prob_away}%`, backgroundColor: "#f97316" }} />
          </div>
          <div className="flex justify-between text-[11px] mt-1">
            <span className="text-emerald-400">{teamPt(data.home)} {data.prob_home.toFixed(0)}%</span>
            <span className="text-muted-foreground">Empate {data.prob_draw?.toFixed(0)}%</span>
            <span className="text-orange-400">{teamPt(data.away)} {data.prob_away.toFixed(0)}%</span>
          </div>
        </div>
      )}

      <button
        onClick={() => router.push("/")}
        className="mt-4 w-full text-xs font-medium py-2 rounded-lg border border-cyan-500/40 text-cyan-400 hover:bg-cyan-500/10 transition-colors"
      >
        Ver análise completa (todos os mercados) →
      </button>
    </div>
  );
}
