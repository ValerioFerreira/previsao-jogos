"use client";
import React from "react";
import { RecentMatch, teamLogoUrl } from "@/lib/api";
import { teamPt } from "@/lib/teamNames";
import { competitionPt } from "@/lib/competitionNames";
import InfoTooltip from "@/components/platform/InfoTooltip";

const hideOnError = (e: React.SyntheticEvent<HTMLImageElement>) => { e.currentTarget.style.display = "none"; };
function fmtBR(s?: string): string { const d = (s || "").slice(0, 10).split("-"); return d.length === 3 ? `${d[2]}/${d[1]}/${d[0]}` : (s || ""); }

type R = "V" | "E" | "D";
function res(m: RecentMatch): R { return m.goals_scored > m.goals_conceded ? "V" : m.goals_scored === m.goals_conceded ? "E" : "D"; }
const PILL: Record<R, string> = { V: "bg-emerald-500", E: "bg-amber-500", D: "bg-red-500" };

function avg(ms: RecentMatch[], f: (m: RecentMatch) => number): number {
  const v = ms.map(f).filter((x) => Number.isFinite(x));
  return v.length ? v.reduce((a, b) => a + b, 0) / v.length : 0;
}
const count = (ms: RecentMatch[], f: (m: RecentMatch) => boolean) => ms.filter(f).length;

// 5 destaques factuais priorizados a partir dos últimos jogos.
function highlights(team: string, ms: RecentMatch[]): { tone: "g" | "r" | "y" | "n"; text: string }[] {
  const n = ms.length;
  if (n === 0) return [];
  const w = count(ms, (m) => res(m) === "V"), e = count(ms, (m) => res(m) === "E"), d = count(ms, (m) => res(m) === "D");
  const scored = count(ms, (m) => m.goals_scored > 0);
  const conceded = count(ms, (m) => m.goals_conceded > 0);
  const over25 = count(ms, (m) => m.goals_scored + m.goals_conceded > 2.5);
  const btts = count(ms, (m) => m.goals_scored > 0 && m.goals_conceded > 0);
  const gf = avg(ms, (m) => m.goals_scored), ga = avg(ms, (m) => m.goals_conceded);
  const sh = avg(ms, (m) => m.sb_shots || 0), sot = avg(ms, (m) => m.sb_shots_on_target || 0);
  const co = avg(ms, (m) => m.sb_corners || 0), ca = avg(ms, (m) => m.sb_cards || 0);
  const out: { tone: "g" | "r" | "y" | "n"; text: string; prio: number }[] = [];
  out.push({ tone: w >= 3 ? "g" : d >= 3 ? "r" : "n", text: `${w}V · ${e}E · ${d}D nos últimos ${n} jogos`, prio: 5 });
  out.push({ tone: scored >= n - 1 ? "g" : "n", text: `Marcou em ${scored} dos ${n} · média ${gf.toFixed(1)} gol/jogo`, prio: scored >= n - 1 ? 4 : 2 });
  out.push({ tone: conceded >= n ? "r" : conceded <= 1 ? "g" : "n", text: conceded <= 1 ? `Gol invicto em ${n - conceded} dos ${n} · sofre ${ga.toFixed(1)}/jogo` : `Sofreu em ${conceded} dos ${n} · média ${ga.toFixed(1)} sofrido/jogo`, prio: conceded <= 1 || conceded >= n ? 4 : 1 });
  out.push({ tone: over25 >= Math.ceil(n * 0.6) ? "y" : "n", text: `Mais de 2,5 gols em ${over25} dos ${n} jogos`, prio: over25 >= Math.ceil(n * 0.6) ? 3 : 1 });
  out.push({ tone: btts >= Math.ceil(n * 0.6) ? "y" : "n", text: `Ambas marcam em ${btts} dos ${n} jogos`, prio: btts >= Math.ceil(n * 0.6) ? 3 : 1 });
  out.push({ tone: "n", text: `Média ${sh.toFixed(0)} finalizações (${sot.toFixed(0)} a gol) por jogo`, prio: 2 });
  out.push({ tone: ca >= 3 ? "y" : "n", text: `Média ${co.toFixed(0)} escanteios · ${ca.toFixed(1)} cartões/jogo`, prio: 2 });
  return out.sort((a, b) => b.prio - a.prio).slice(0, 5).map(({ tone, text }) => ({ tone, text }));
}

const STAT_ROWS: { label: string; f: (m: RecentMatch) => number; d?: number; suf?: string }[] = [
  { label: "Gols marcados", f: (m) => m.goals_scored, d: 1 },
  { label: "Gols sofridos", f: (m) => m.goals_conceded, d: 1 },
  { label: "Finalizações", f: (m) => m.sb_shots || 0, d: 1 },
  { label: "Chutes a gol", f: (m) => m.sb_shots_on_target || 0, d: 1 },
  { label: "Escanteios", f: (m) => m.sb_corners || 0, d: 1 },
  { label: "Faltas", f: (m) => m.sb_fouls || 0, d: 1 },
  { label: "Impedimentos", f: (m) => m.sb_offsides || 0, d: 1 },
  { label: "Cartões", f: (m) => m.sb_cards || 0, d: 1 },
  { label: "Posse", f: (m) => m.sb_possession || 0, d: 0, suf: "%" },
];

const DOT: Record<string, string> = { g: "bg-emerald-400", r: "bg-red-400", y: "bg-amber-400", n: "bg-muted-foreground/50" };

function TeamPanel({ team, matches, teamIds, accent }: { team: string; matches: RecentMatch[]; teamIds: Record<string, number>; accent: string }) {
  const ms = (matches || []).slice(0, 5);
  const hl = highlights(team, ms);
  return (
    <div className="px-4 first:pl-0 last:pr-0">
      <div className="flex items-center gap-2 mb-3">
        {teamLogoUrl(teamIds[team]) && <img src={teamLogoUrl(teamIds[team])!} alt="" className="w-6 h-6 object-contain" loading="lazy" onError={hideOnError} />}
        <span className="text-sm font-semibold" style={{ color: accent }}>{teamPt(team)}</span>
      </div>

      {/* Últimos 5 adversários */}
      <p className="text-[10px] uppercase tracking-wide text-muted-foreground mb-1.5">Últimos jogos</p>
      <div className="space-y-1 mb-3">
        {ms.map((m, i) => {
          const r = res(m);
          return (
            <div key={i} className="group relative flex items-center gap-2 text-xs">
              <span className={`w-4 h-4 rounded flex items-center justify-center text-[9px] font-bold text-white shrink-0 ${PILL[r]}`}>{r}</span>
              <span className="text-muted-foreground text-[10px] shrink-0">{m.is_home ? "vs" : "@"}</span>
              <span className="flex-1 truncate">{teamPt(m.opponent)}</span>
              <span className="font-mono font-semibold shrink-0">{m.goals_scored}–{m.goals_conceded}</span>
              <div className="absolute left-0 bottom-full mb-1 hidden group-hover:block z-30 w-max max-w-[190px]">
                <div className="rounded-lg border border-border/60 bg-popover shadow-xl p-2 text-[10px] text-muted-foreground">
                  {fmtBR(m.date)}{m.competition ? ` · ${competitionPt(m.competition)}` : ""}{m.is_home ? " · mandante" : " · visitante"}
                </div>
              </div>
            </div>
          );
        })}
        {ms.length === 0 && <span className="text-xs text-muted-foreground italic">sem jogos</span>}
      </div>

      {/* Médias das principais estatísticas */}
      {ms.length > 0 && (
        <>
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground mb-1">Médias (últimos {ms.length})</p>
          <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 mb-3">
            {STAT_ROWS.map((s) => (
              <div key={s.label} className="flex items-center justify-between text-[11px] border-b border-border/15 py-0.5">
                <span className="text-muted-foreground">{s.label}</span>
                <span className="font-mono font-medium">{avg(ms, s.f).toFixed(s.d ?? 1)}{s.suf || ""}</span>
              </div>
            ))}
          </div>
        </>
      )}

      {/* Principais Destaques */}
      {hl.length > 0 && (
        <>
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground mb-1">Principais Destaques</p>
          <ul className="space-y-1">
            {hl.map((h, i) => (
              <li key={i} className="flex items-start gap-1.5 text-[11px]">
                <span className={`mt-1 w-1.5 h-1.5 rounded-full shrink-0 ${DOT[h.tone]}`} />
                <span className="text-muted-foreground">{h.text}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

export default function DestaquesRecentes({ home, away, homeMatches, awayMatches, teamIds }: {
  home: string; away: string; homeMatches: RecentMatch[]; awayMatches: RecentMatch[]; teamIds: Record<string, number>;
}) {
  if ((homeMatches?.length ?? 0) === 0 && (awayMatches?.length ?? 0) === 0) return null;
  return (
    <div className="bg-card border border-border/50 rounded-xl p-5 h-full">
      <h3 className="text-sm font-semibold mb-3 flex items-center gap-1.5">
        Destaques Recentes
        <InfoTooltip text="Panorama dos últimos 5 jogos de cada seleção: adversários e placares, médias das principais estatísticas (gols, finalizações, escanteios, faltas, impedimentos, cartões, posse) e os principais destaques automáticos de padrão." />
      </h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 sm:divide-x divide-border/40">
        <TeamPanel team={home} matches={homeMatches} teamIds={teamIds} accent="#10b981" />
        <TeamPanel team={away} matches={awayMatches} teamIds={teamIds} accent="#f97316" />
      </div>
    </div>
  );
}
