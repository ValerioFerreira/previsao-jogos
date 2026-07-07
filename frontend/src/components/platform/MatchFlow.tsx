"use client";
import React from "react";
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, ReferenceLine, Tooltip as RTooltip, ResponsiveContainer } from "recharts";
import { MatchDetail as MD } from "@/lib/api";
import { teamPt } from "@/lib/teamNames";
import InfoTooltip from "@/components/platform/InfoTooltip";

type GoalEv = { minute: number; team: "home" | "away"; player: string; own: boolean };

export default function MatchFlow({ data }: { data: MD }) {
  const info = data.info;
  const evs = data.events || [];
  if (!info || evs.length === 0) return null;

  // Gols (inclui contra e pênalti), atribuídos ao time que PONTUA.
  const goals: GoalEv[] = [];
  evs.forEach((e) => {
    if ((e.type || "").toLowerCase() !== "goal") return;
    if ((e.detail || "").toLowerCase().includes("missed")) return; // pênalti perdido não conta
    const isHomeEvent = e.team_id != null && info.home_id != null ? e.team_id === info.home_id : e.team === info.home;
    const own = (e.detail || "").includes("Own");
    // gol contra: ponto vai para o adversário
    const scoringHome = own ? !isHomeEvent : isHomeEvent;
    const min = (e.minute ?? 0) + (e.extra ?? 0);
    goals.push({ minute: min, team: scoringHome ? "home" : "away", player: e.player, own });
  });
  if (goals.length === 0) return null;
  goals.sort((a, b) => a.minute - b.minute);

  // Série de diferença de placar (mando − visitante) ao longo do tempo (degraus).
  const maxMin = Math.max(90, ...goals.map((g) => g.minute));
  let h = 0, a = 0;
  const gByMin = new Map<number, GoalEv[]>();
  goals.forEach((g) => { if (!gByMin.has(g.minute)) gByMin.set(g.minute, []); gByMin.get(g.minute)!.push(g); });
  const pts: { minute: number; diff: number; label?: string }[] = [{ minute: 0, diff: 0 }];
  for (let m = 1; m <= maxMin; m++) {
    const gs = gByMin.get(m);
    if (gs) {
      gs.forEach((g) => (g.team === "home" ? h++ : a++));
      const scorers = gs.map((g) => `${g.player}${g.own ? " (c)" : ""} ${g.team === "home" ? teamPt(info.home || "") : teamPt(info.away || "")}`).join(" · ");
      pts.push({ minute: m, diff: h - a, label: `${m}' ${h}-${a} · ${scorers}` });
    } else {
      pts.push({ minute: m, diff: h - a });
    }
  }

  const homeName = teamPt(info.home || "");
  const awayName = teamPt(info.away || "");
  const maxAbs = Math.max(1, ...pts.map((p) => Math.abs(p.diff)));

  const CustomTip = ({ active, payload }: any) => {
    if (!active || !payload?.length) return null;
    const p = payload[0].payload;
    return (
      <div className="rounded-lg border border-border/60 bg-popover shadow-xl p-2 text-[11px]">
        {p.label ? <p className="font-medium">⚽ {p.label}</p> : <p className="text-muted-foreground">{p.minute}' · {homeName} lidera por {p.diff > 0 ? p.diff : p.diff < 0 ? `${-p.diff} contra` : "empate"}</p>}
      </div>
    );
  };

  return (
    <div className="bg-card border border-border/50 rounded-xl p-5">
      <h3 className="text-base font-semibold mb-1 flex items-center gap-1.5">
        Fluxo da Partida
        <InfoTooltip text="Evolução da diferença de gols ao longo do tempo. Acima da linha (verde) o mandante esteve à frente; abaixo (laranja) o visitante. Passe o mouse para ver o autor de cada gol." />
      </h3>
      <div className="flex items-center justify-between text-[11px] mb-2">
        <span className="text-emerald-400 font-medium">▲ {homeName}</span>
        <span className="text-orange-400 font-medium">{awayName} ▼</span>
      </div>
      <div className="h-44">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={pts} margin={{ top: 4, right: 8, bottom: 0, left: -20 }}>
            <defs>
              {/* Domínio simétrico ⇒ y=0 está exatamente em 50%: verde acima, laranja abaixo. */}
              <linearGradient id="flowSplitFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#10b981" stopOpacity={0.55} />
                <stop offset="49%" stopColor="#10b981" stopOpacity={0.06} />
                <stop offset="51%" stopColor="#f97316" stopOpacity={0.06} />
                <stop offset="100%" stopColor="#f97316" stopOpacity={0.55} />
              </linearGradient>
              <linearGradient id="flowSplitStroke" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#10b981" />
                <stop offset="49.9%" stopColor="#10b981" />
                <stop offset="50.1%" stopColor="#f97316" />
                <stop offset="100%" stopColor="#f97316" />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.3} />
            <XAxis dataKey="minute" type="number" domain={[0, maxMin]} ticks={[0, 15, 30, 45, 60, 75, 90]} tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }} tickFormatter={(v) => `${v}'`} />
            <YAxis domain={[-maxAbs, maxAbs]} allowDecimals={false} tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }} width={28} />
            <ReferenceLine y={0} stroke="hsl(var(--border))" />
            <ReferenceLine x={45} stroke="hsl(var(--border))" strokeDasharray="2 4" label={{ value: "intervalo", fontSize: 9, fill: "hsl(var(--muted-foreground))", position: "insideTopRight" }} />
            <RTooltip content={<CustomTip />} />
            <Area type="stepAfter" dataKey="diff" stroke="url(#flowSplitStroke)" strokeWidth={2} fill="url(#flowSplitFill)" baseValue={0} dot={false} activeDot={{ r: 4, fill: "#10b981" }} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
