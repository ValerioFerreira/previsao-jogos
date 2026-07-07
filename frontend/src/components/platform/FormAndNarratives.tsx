"use client";
import React from "react";
import { RecentMatch } from "@/lib/api";
import { teamPt } from "@/lib/teamNames";
import { competitionPt } from "@/lib/competitionNames";
import InfoTooltip from "@/components/platform/InfoTooltip";

function fmtBR(s?: string): string {
  const d = (s || "").slice(0, 10).split("-");
  return d.length === 3 ? `${d[2]}/${d[1]}/${d[0]}` : (s || "");
}
type R = "V" | "E" | "D";
function res(m: RecentMatch): R {
  return m.goals_scored > m.goals_conceded ? "V" : m.goals_scored === m.goals_conceded ? "E" : "D";
}
const PILL: Record<R, string> = { V: "bg-emerald-500 text-white", E: "bg-amber-500 text-white", D: "bg-red-500 text-white" };

function Pills({ team, matches }: { team: string; matches: RecentMatch[] }) {
  const ms = (matches || []).slice(0, 8); // já vem do mais recente ao mais antigo
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs font-medium w-28 truncate shrink-0">{teamPt(team)}</span>
      <div className="flex gap-1">
        {ms.map((m, i) => {
          const r = res(m);
          const mh = m.is_home ? team : m.opponent;
          const ma = m.is_home ? m.opponent : team;
          return (
            <div key={i} className="group relative">
              <span className={`w-6 h-6 rounded-md flex items-center justify-center text-[11px] font-bold font-mono ${PILL[r]}`}>{r}</span>
              <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 hidden group-hover:block z-30 w-max max-w-[200px]">
                <div className="rounded-lg border border-border/60 bg-popover shadow-xl p-2 text-[11px] text-center">
                  <p className="font-medium">{teamPt(mh)} <span className="font-mono font-bold">{m.is_home ? m.goals_scored : m.goals_conceded}–{m.is_home ? m.goals_conceded : m.goals_scored}</span> {teamPt(ma)}</p>
                  <p className="text-muted-foreground text-[10px]">{fmtBR(m.date)}{m.competition ? ` · ${competitionPt(m.competition)}` : ""}</p>
                </div>
              </div>
            </div>
          );
        })}
        {ms.length === 0 && <span className="text-xs text-muted-foreground italic">sem jogos</span>}
      </div>
    </div>
  );
}

function narratives(home: string, away: string, hm: RecentMatch[], am: RecentMatch[]): { tone: "g" | "r" | "y"; text: string }[] {
  const out: { tone: "g" | "r" | "y"; text: string }[] = [];
  const last = (ms: RecentMatch[], n: number) => (ms || []).slice(0, n);
  const count = (ms: RecentMatch[], f: (m: RecentMatch) => boolean) => ms.filter(f).length;
  for (const [team, ms] of [[home, hm], [away, am]] as [string, RecentMatch[]][]) {
    const L = last(ms, 6); if (L.length < 4) continue;
    const scored = count(L, (m) => m.goals_scored > 0);
    const conceded = count(L, (m) => m.goals_conceded > 0);
    const wins = count(L, (m) => res(m) === "V");
    const over25 = count(L, (m) => m.goals_scored + m.goals_conceded > 2.5);
    if (scored >= L.length - 1) out.push({ tone: "g", text: `${teamPt(team)} marcou em ${scored} dos últimos ${L.length} jogos.` });
    if (conceded >= L.length) out.push({ tone: "r", text: `${teamPt(team)} sofreu gols em todos os últimos ${L.length} jogos.` });
    else if (conceded <= 1) out.push({ tone: "g", text: `${teamPt(team)} manteve o gol invicto em ${L.length - conceded} dos últimos ${L.length}.` });
    if (wins >= L.length - 1) out.push({ tone: "g", text: `${teamPt(team)} venceu ${wins} dos últimos ${L.length}.` });
    if (over25 >= Math.ceil(L.length * 0.7)) out.push({ tone: "y", text: `${teamPt(team)}: mais de 2,5 gols em ${over25} dos últimos ${L.length} jogos.` });
  }
  // BTTS combinado
  const comb = [...last(hm, 5), ...last(am, 5)];
  if (comb.length >= 6) {
    const btts = comb.filter((m) => m.goals_scored > 0 && m.goals_conceded > 0).length;
    const pct = Math.round((btts / comb.length) * 100);
    if (pct >= 60) out.push({ tone: "y", text: `Ambas Marcam bateu em ${pct}% dos jogos recentes das duas equipes combinadas.` });
  }
  return out.slice(0, 6);
}

const DOT: Record<string, string> = { g: "text-emerald-400", r: "text-red-400", y: "text-amber-400" };

export default function FormAndNarratives({ home, away, homeMatches, awayMatches }: {
  home: string; away: string; homeMatches: RecentMatch[]; awayMatches: RecentMatch[];
}) {
  const narr = narratives(home, away, homeMatches, awayMatches);
  if ((homeMatches?.length ?? 0) === 0 && (awayMatches?.length ?? 0) === 0) return null;
  return (
    <div className="bg-card border border-border/50 rounded-xl p-5">
      <h3 className="text-sm font-semibold mb-3 flex items-center gap-1.5">
        Guia de Forma & Narrativas
        <InfoTooltip text="Resultados recentes (V vitória / E empate / D derrota, do mais recente ao mais antigo — passe o mouse para o jogo) e alertas automáticos de padrões (sequências de marcar/sofrer gols, mais de 2,5, ambas marcam)." />
      </h3>
      <div className="space-y-2 mb-4">
        <Pills team={home} matches={homeMatches} />
        <Pills team={away} matches={awayMatches} />
      </div>
      {narr.length > 0 && (
        <div className="border-t border-border/30 pt-3 space-y-1.5">
          {narr.map((n, i) => (
            <p key={i} className="text-xs flex items-start gap-1.5">
              <span className={`mt-1 w-1.5 h-1.5 rounded-full shrink-0 ${n.tone === "g" ? "bg-emerald-400" : n.tone === "r" ? "bg-red-400" : "bg-amber-400"}`} />
              <span className="text-muted-foreground">{n.text}</span>
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
