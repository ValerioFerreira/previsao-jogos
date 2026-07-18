"use client";
import React from "react";
import Link from "next/link";
import { teamLogoUrl, onImgError } from "@/lib/api";
import { teamPt } from "@/lib/teamNames";
import { competitionPt } from "@/lib/competitionNames";
import InfoTooltip from "@/components/platform/InfoTooltip";

function fmtBR(s?: string): string {
  if (!s) return "";
  const d = s.slice(0, 10).split("-");
  return d.length === 3 ? `${d[2]}/${d[1]}/${d[0]}` : s;
}

type RecentH2H = { date: string; home_team: string; away_team: string; home_score: number; away_score: number; tournament?: string | null };

// Card de confronto direto (H2H) — enriquecido, ocupa toda a altura do bloco (a lista de
// confrontos cresce para preencher, evitando espaço em branco no rodapé).
export default function H2HCard({ h2hData, home, away, teamIds }: {
  h2hData: any; home: string; away: string; teamIds: Record<string, number>;
}) {
  if (!h2hData || (h2hData.h2h_played ?? 0) === 0) return null;
  const played: number = h2hData.h2h_played;
  const hw: number = h2hData.home_wins ?? 0;
  const dr: number = h2hData.draws ?? 0;
  const aw: number = h2hData.away_wins ?? 0;
  const bttsCount: number = h2hData.btts_count ?? Math.round(((h2hData.btts_percentage ?? 0) / 100) * played);
  const recent: RecentH2H[] = Array.isArray(h2hData.recent) ? h2hData.recent : [];
  const pct = (n: number) => (played > 0 ? Math.round((n / played) * 100) : 0);
  const gdMean: number | null = typeof h2hData.home_gd_mean === "number" ? h2hData.home_gd_mean : null;
  const daysSince: number | null = typeof h2hData.days_since_last_h2h === "number" ? Math.round(h2hData.days_since_last_h2h) : null;

  const AVG_ROWS: [string, string][] = [["Gols", "goals"], ["Chutes", "shots"], ["Chutes a gol", "shots_on_target"], ["Escanteios", "corners"], ["Cartões", "cards"]];

  // Métricas-resumo (chips) — Gols/jogo, Ambas marcam e Média de gols sempre na mesma linha.
  const chips: { label: string; value: string }[] = [
    {
      label: "Gols/jogo (M–V)",
      value: h2hData.home_avgs?.goals != null && h2hData.away_avgs?.goals != null
        ? `${h2hData.home_avgs.goals}–${h2hData.away_avgs.goals}` : "—",
    },
    { label: "Ambas marcam", value: `${pct(bttsCount)}%` },
    { label: "Média de gols", value: `${h2hData.avg_total_goals ?? "—"}` },
  ];

  return (
    <div className="bg-card border border-border/50 rounded-xl p-5 shadow-sm w-full h-full flex flex-col">
      <div className="text-center mb-3">
        <h3 className="text-sm font-bold uppercase mb-1 flex items-center justify-center gap-1.5">
          Resumo do Confronto Direto
          <InfoTooltip text="Histórico de partidas entre as duas equipes (resultados da base martj42; estatísticas avançadas quando disponíveis)." />
        </h3>
        <p className="text-[10px] text-muted-foreground">
          {played} {played === 1 ? "jogo" : "jogos"}
          {h2hData.last_date ? ` · último em ${fmtBR(h2hData.last_date)}` : ""}
          {daysSince != null ? ` (${daysSince} dias)` : ""}
        </p>
      </div>

      {/* Placar do retrospecto: vitórias/empates + barra de distribuição */}
      <div className="grid grid-cols-3 gap-2 mb-2">
        {[
          { id: home, w: hw, color: "text-emerald-500", label: "Vitórias" },
          { id: null, w: dr, color: "text-muted-foreground", label: "Empates" },
          { id: away, w: aw, color: "text-cyan-500", label: "Vitórias" },
        ].map((s, i) => (
          <div key={i} className="flex flex-col items-center">
            {s.id ? (
              teamLogoUrl(teamIds[s.id]) && (
                <img src={teamLogoUrl(teamIds[s.id])!} alt="" className="w-8 h-8 object-contain mb-1" loading="lazy" onError={onImgError} />
              )
            ) : <div className="h-8 mb-1 flex items-center"><span className="text-[10px] uppercase tracking-wide text-muted-foreground">Empates</span></div>}
            {s.id && <span className="text-[11px] font-semibold leading-tight text-center truncate max-w-full">{teamPt(s.id)}</span>}
            {s.id && <span className="text-[9px] uppercase tracking-wide text-muted-foreground">{s.label}</span>}
            <span className={`text-2xl font-mono font-bold ${s.color}`}>{s.w}</span>
            <span className="text-[10px] text-muted-foreground">{pct(s.w)}%</span>
          </div>
        ))}
      </div>
      {/* barra de distribuição de resultados */}
      <div className="flex h-2 rounded-full overflow-hidden mb-3">
        <div style={{ width: `${pct(hw)}%` }} className="bg-emerald-500" title={`${teamPt(home)} ${pct(hw)}%`} />
        <div style={{ width: `${pct(dr)}%` }} className="bg-muted-foreground/50" title={`Empates ${pct(dr)}%`} />
        <div style={{ width: `${pct(aw)}%` }} className="bg-cyan-500" title={`${teamPt(away)} ${pct(aw)}%`} />
      </div>

      {/* chips de métricas do confronto — sempre na mesma linha */}
      <div className="grid grid-cols-3 gap-2 mb-3">
        {chips.map((c) => (
          <div key={c.label} className="rounded-lg bg-muted/50 border border-border/40 px-2 py-1.5 text-center">
            <p className="text-[9px] uppercase tracking-wide text-muted-foreground leading-tight">{c.label}</p>
            <p className="text-sm font-mono font-bold text-foreground leading-tight">{c.value}</p>
          </div>
        ))}
      </div>
      {gdMean != null && (
        <div className="rounded-lg bg-muted/50 border border-border/40 px-2.5 py-1.5 text-center mb-3">
          <p className="text-[9px] uppercase tracking-wide text-muted-foreground leading-tight">Saldo médio (mandante)</p>
          <p className="text-sm font-mono font-bold text-foreground leading-tight">{gdMean > 0 ? "+" : ""}{gdMean.toFixed(1)}</p>
        </div>
      )}

      {/* médias no confronto direto (por equipe) */}
      <div className="mb-3">
        <p className="text-[10px] uppercase tracking-wide text-muted-foreground mb-1 text-center">Médias no confronto direto</p>
        <div className="grid grid-cols-3 items-center text-[10px] text-muted-foreground pb-1 border-b border-border/30">
          <span className="text-center text-emerald-400 truncate">{teamPt(home)}</span>
          <span className="text-center" />
          <span className="text-center text-cyan-400 truncate">{teamPt(away)}</span>
        </div>
        {AVG_ROWS.map(([label, key]) => (
          <div key={key} className="grid grid-cols-3 items-center text-xs py-1 border-t border-border/20 first:border-t-0">
            <span className="font-mono font-semibold text-emerald-400 text-center">{h2hData.home_avgs?.[key] ?? "—"}</span>
            <span className="text-muted-foreground text-center">{label}</span>
            <span className="font-mono font-semibold text-cyan-400 text-center">{h2hData.away_avgs?.[key] ?? "—"}</span>
          </div>
        ))}
      </div>

      {/* últimos confrontos — cresce para preencher a altura restante do card */}
      {recent.length > 0 && (
        <div className="flex-1 flex flex-col min-h-0 pt-3 border-t border-border/30">
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground mb-1 text-center">Últimos confrontos</p>
          <div className="flex-1 overflow-y-auto pr-1 min-h-0">
            {recent.map((r, i) => (
              <Link
                key={i}
                href={`/estatisticas?home=${encodeURIComponent(r.home_team)}&away=${encodeURIComponent(r.away_team)}&date=${encodeURIComponent(r.date)}`}
                className="grid grid-cols-[3.6rem_1fr_auto_1fr_5rem] items-center gap-2 text-xs py-1.5 rounded hover:bg-muted/50 transition-colors"
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
