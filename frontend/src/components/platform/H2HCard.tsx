"use client";
import React from "react";
import Link from "next/link";
import { CheckCircle2 } from "lucide-react";
import { teamLogoUrl } from "@/lib/api";
import { teamPt } from "@/lib/teamNames";
import { competitionPt } from "@/lib/competitionNames";
import InfoTooltip from "@/components/platform/InfoTooltip";

function fmtBR(s?: string): string {
  if (!s) return "";
  const d = s.slice(0, 10).split("-");
  return d.length === 3 ? `${d[2]}/${d[1]}/${d[0]}` : s;
}

type RecentH2H = { date: string; home_team: string; away_team: string; home_score: number; away_score: number; tournament?: string | null };

// Card de confronto direto (H2H) — enriquecido e centralizado. Disponível assim que
// as duas seleções estão escolhidas (antes de gerar a análise).
export default function H2HCard({ h2hData, home, away, teamIds }: {
  h2hData: any; home: string; away: string; teamIds: Record<string, number>;
}) {
  if (!h2hData || (h2hData.h2h_played ?? 0) === 0) return null;
  const played: number = h2hData.h2h_played;
  const bttsCount: number = h2hData.btts_count ?? Math.round(((h2hData.btts_percentage ?? 0) / 100) * played);
  const recent: RecentH2H[] = Array.isArray(h2hData.recent) ? h2hData.recent : [];
  const AVG_ROWS: [string, string][] = [["Gols", "goals"], ["Chutes", "shots"], ["Chutes a gol", "shots_on_target"], ["Escanteios", "corners"], ["Cartões", "cards"]];

  return (
    <div className="bg-card border border-border/50 rounded-xl p-5 shadow-sm max-w-3xl mx-auto w-full">
      <div className="text-center mb-4">
        <h3 className="text-sm font-bold uppercase mb-1 flex items-center justify-center gap-1.5">
          Resumo do Confronto Direto
          <InfoTooltip text="Histórico de partidas entre as duas seleções (resultados da base martj42; estatísticas avançadas quando disponíveis)." />
        </h3>
        <p className="text-[10px] text-muted-foreground">
          {played} {played === 1 ? "jogo" : "jogos"}
          {h2hData.last_date ? ` · último em ${fmtBR(h2hData.last_date)}` : ""}
        </p>
      </div>

      {/* Esquerda (vitórias + agregados) | divisor em degradê | Direita (médias) */}
      <div className="grid grid-cols-1 md:grid-cols-[1fr_auto_1fr] gap-4 md:gap-6 items-stretch">
        <div>
          <div className="flex items-start justify-center gap-5 sm:gap-7 mb-4">
            {[{ id: home, w: h2hData.home_wins }, null, { id: away, w: h2hData.away_wins }].map((side) =>
              side === null ? (
                <div key="draw" className="flex flex-col items-center justify-center pt-7">
                  <span className="text-[10px] uppercase tracking-wide text-muted-foreground">Empates</span>
                  <span className="text-2xl font-mono font-bold text-muted-foreground">{h2hData.draws}</span>
                </div>
              ) : (
                <div key={side.id} className="flex flex-col items-center w-24">
                  {teamLogoUrl(teamIds[side.id]) && (
                    <img src={teamLogoUrl(teamIds[side.id])!} alt="" className="w-9 h-9 object-contain mb-1" loading="lazy" onError={(e) => { e.currentTarget.style.display = "none"; }} />
                  )}
                  <span className="text-xs font-semibold leading-tight text-center">{teamPt(side.id)}</span>
                  <span className="text-[10px] uppercase tracking-wide text-muted-foreground mt-1">Vitórias</span>
                  <span className="flex items-center gap-1 text-lg font-mono font-bold"><CheckCircle2 className="w-4 h-4 text-emerald-500" /> {side.w}</span>
                </div>
              )
            )}
          </div>
          <div className="max-w-xs mx-auto space-y-2">
            <div className="rounded-lg bg-muted/50 border border-border/40 px-3 py-2 text-center">
              <p className="text-xs text-foreground">
                Ambas marcaram em <b className="font-mono">{bttsCount}</b> das <b className="font-mono">{played}</b> partidas
              </p>
            </div>
            <div className="rounded-lg bg-muted/50 border border-border/40 px-3 py-2 text-center">
              <p className="text-[9px] uppercase tracking-wide text-muted-foreground">Média de gols</p>
              <p className="text-base font-mono font-bold text-foreground">{h2hData.avg_total_goals ?? "—"}</p>
            </div>
          </div>
        </div>

        {/* Divisor: vertical (md+) / horizontal (mobile), na cor do botão Gerar análise */}
        <div className="w-full h-px md:w-px md:h-auto md:self-stretch bg-gradient-to-r md:bg-gradient-to-b from-emerald-500 to-cyan-500" />

        <div>
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground mb-1.5 text-center">Médias no confronto direto</p>
          {AVG_ROWS.map(([label, key]) => (
            <div key={key} className="grid grid-cols-3 items-center text-xs py-1 border-t border-border/20">
              <span className="font-mono font-semibold text-emerald-400 text-center">{h2hData.home_avgs?.[key] ?? "—"}</span>
              <span className="text-muted-foreground text-center">{label}</span>
              <span className="font-mono font-semibold text-cyan-400 text-center">{h2hData.away_avgs?.[key] ?? "—"}</span>
            </div>
          ))}
        </div>
      </div>

      {recent.length > 0 && (
        <div className="mt-5 pt-4 border-t border-border/30">
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground mb-2 text-center">Últimos confrontos</p>
          <div className="max-w-2xl mx-auto">
            {recent.map((r, i) => (
              <Link
                key={i}
                href={`/estatisticas?home=${encodeURIComponent(r.home_team)}&away=${encodeURIComponent(r.away_team)}&date=${encodeURIComponent(r.date)}`}
                className="grid grid-cols-[4rem_1fr_auto_1fr_5.5rem] items-center gap-2 text-xs py-1.5 rounded hover:bg-muted/50 transition-colors"
              >
                <span className="text-muted-foreground text-[10px] tabular-nums text-left">{fmtBR(r.date)}</span>
                <span className="font-medium text-right truncate">{teamPt(r.home_team)}</span>
                <span className="font-mono font-bold text-foreground text-center px-1 whitespace-nowrap">{r.home_score}–{r.away_score}</span>
                <span className="font-medium text-left truncate">{teamPt(r.away_team)}</span>
                <span className="text-muted-foreground text-[10px] truncate text-right">{r.tournament ? competitionPt(r.tournament) : ""}</span>
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
