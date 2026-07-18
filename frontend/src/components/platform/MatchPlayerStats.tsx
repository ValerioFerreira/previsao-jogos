"use client";
import React from "react";
import { MatchDetail as MD, MatchPlayer, teamLogoUrl, playerPhotoUrl, onImgError as hideOnError } from "@/lib/api";
import { teamPt } from "@/lib/teamNames";
import InfoTooltip from "@/components/platform/InfoTooltip";
const num = (v: number | null | undefined) => (v == null ? 0 : v);
const rf = (r: string | null | undefined): number => { const v = r ? parseFloat(r) : NaN; return isNaN(v) ? NaN : v; };

function ratingColor(v: number): string {
  if (isNaN(v)) return "text-muted-foreground";
  if (v >= 7.5) return "text-emerald-400";
  if (v >= 6.5) return "text-lime-400";
  if (v >= 6.0) return "text-amber-400";
  return "text-red-400";
}

type Row = MatchPlayer & { teamId: number; teamName: string };

// Mini-card de destaque (MVP / Maestro / Xerife)
function TopCard({ label, icon, accent, p, valueLabel, value }: {
  label: string; icon: string; accent: string; p: Row | null; valueLabel: string; value: string;
}) {
  if (!p) return null;
  return (
    <div className="bg-card border border-border/50 rounded-xl p-3 flex items-center gap-3">
      <div className="relative shrink-0">
        <div className="w-12 h-12 rounded-full bg-muted overflow-hidden ring-2" style={{ ["--tw-ring-color" as any]: accent }}>
          {playerPhotoUrl(p.id)
            ? <img src={playerPhotoUrl(p.id)!} alt="" className="w-full h-full object-cover" loading="lazy" onError={hideOnError} />
            : <span className="flex items-center justify-center w-full h-full text-sm font-bold text-muted-foreground">{p.number ?? "?"}</span>}
        </div>
        {teamLogoUrl(p.teamId) && <img src={teamLogoUrl(p.teamId)!} alt="" className="absolute -bottom-1 -right-1 w-5 h-5 object-contain bg-background rounded-full p-0.5" onError={hideOnError} />}
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-[10px] uppercase tracking-wide font-semibold flex items-center gap-1" style={{ color: accent }}>{icon} {label}</p>
        <p className="text-sm font-semibold leading-tight truncate">{p.name}</p>
        <p className="text-[11px] text-muted-foreground">{valueLabel}: <span className="font-mono font-bold text-foreground">{value}</span></p>
      </div>
    </div>
  );
}

type SortKey = "rating" | "minutes" | "shots_total" | "shots_on" | "passes" | "key_passes" | "tackles";
const COLS: { key: SortKey; label: string; short: string }[] = [
  { key: "minutes", label: "Minutos em campo", short: "Min" },
  { key: "rating", label: "Nota (rating)", short: "Nota" },
  { key: "shots_total", label: "Finalizações", short: "Fin" },
  { key: "shots_on", label: "Chutes a gol", short: "A gol" },
  { key: "passes", label: "Passes", short: "Passes" },
  { key: "key_passes", label: "Passes-chave", short: "Chave" },
  { key: "tackles", label: "Desarmes", short: "Desar." },
];

export default function MatchPlayerStats({ data }: { data: MD }) {
  const [sortKey, setSortKey] = React.useState<SortKey>("rating");
  const [asc, setAsc] = React.useState(false);
  const [teamFilter, setTeamFilter] = React.useState<number | "all">("all");

  const info = data.info;
  const rows: Row[] = React.useMemo(() => {
    const out: Row[] = [];
    (data.players || []).forEach((pb) => (pb.players || []).forEach((p) => {
      out.push({ ...p, teamId: pb.team_id, teamName: pb.team });
    }));
    return out;
  }, [data]);

  if (rows.length === 0 || !info) return null;

  // times presentes (nomes reais dos blocos de players, que são a fonte autoritária)
  const teams = Array.from(new Map(rows.map((r) => [r.teamId, r.teamName])).entries());

  // Top performers (só quem jogou o suficiente)
  const played = rows.filter((r) => num(r.minutes) >= 30);
  const pick = (f: (r: Row) => number): Row | null => {
    const c = played.filter((r) => Number.isFinite(f(r)) && f(r) > 0);
    if (!c.length) return null;
    return c.reduce((a, b) => (f(b) > f(a) ? b : a));
  };
  const mvp = pick((r) => rf(r.rating));
  const maestro = pick((r) => num(r.passes));
  const xerife = pick((r) => num(r.tackles));

  const filtered = teamFilter === "all" ? rows : rows.filter((r) => r.teamId === teamFilter);
  const sorted = [...filtered].sort((a, b) => {
    const va = sortKey === "rating" ? rf(a.rating) : num(a[sortKey] as number);
    const vb = sortKey === "rating" ? rf(b.rating) : num(b[sortKey] as number);
    const na = Number.isFinite(va) ? va : -1, nb = Number.isFinite(vb) ? vb : -1;
    return asc ? na - nb : nb - na;
  });

  const toggle = (k: SortKey) => { if (k === sortKey) setAsc(!asc); else { setSortKey(k); setAsc(false); } };

  return (
    <div className="space-y-4">
      {/* Top Performers */}
      {(mvp || maestro || xerife) && (
        <div>
          <h3 className="text-base font-semibold mb-2 flex items-center gap-1.5">
            Destaques da Partida
            <InfoTooltip text="Melhores da partida por critério, entre quem atuou ao menos 30 minutos: MVP (maior nota), Maestro (mais passes) e Xerife (mais desarmes)." />
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <TopCard label="MVP · Maior Nota" icon="⭐" accent="#f59e0b" p={mvp} valueLabel="Nota" value={mvp ? rf(mvp.rating).toFixed(1) : "-"} />
            <TopCard label="Maestro · Mais Passes" icon="🎯" accent="#10b981" p={maestro} valueLabel="Passes" value={maestro ? String(num(maestro.passes)) : "-"} />
            <TopCard label="Xerife · Mais Desarmes" icon="🛡️" accent="#06b6d4" p={xerife} valueLabel="Desarmes" value={xerife ? String(num(xerife.tackles)) : "-"} />
          </div>
        </div>
      )}

      {/* Tabela ordenável */}
      <div className="bg-card border border-border/50 rounded-xl p-4">
        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <h3 className="text-base font-semibold flex items-center gap-1.5">
            Estatísticas por Jogador
            <InfoTooltip text="Clique num cabeçalho para ordenar. Filtre por equipe nos botões. Fonte: ficha oficial da partida (API-Football)." />
          </h3>
          <div className="flex gap-1">
            <button onClick={() => setTeamFilter("all")}
              className={`text-[11px] px-2 py-1 rounded-md border ${teamFilter === "all" ? "bg-primary text-primary-foreground border-primary" : "border-border/60 text-muted-foreground hover:bg-muted"}`}>Todos</button>
            {teams.map(([tid, tname]) => (
              <button key={tid} onClick={() => setTeamFilter(tid)}
                className={`text-[11px] px-2 py-1 rounded-md border flex items-center gap-1 ${teamFilter === tid ? "bg-primary text-primary-foreground border-primary" : "border-border/60 text-muted-foreground hover:bg-muted"}`}>
                {teamLogoUrl(tid) && <img src={teamLogoUrl(tid)!} alt="" className="w-3.5 h-3.5 object-contain" onError={hideOnError} />}
                {teamPt(tname)}
              </button>
            ))}
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-[0.8rem] border-collapse">
            <thead>
              <tr className="text-muted-foreground border-b border-border/50">
                <th className="text-left font-medium py-1.5 pr-2 sticky left-0 bg-card">Jogador</th>
                {COLS.map((c) => (
                  <th key={c.key} title={c.label} onClick={() => toggle(c.key)}
                    className={`text-right font-medium py-1.5 px-2 cursor-pointer select-none whitespace-nowrap hover:text-foreground ${sortKey === c.key ? "text-foreground" : ""}`}>
                    {c.short}{sortKey === c.key ? (asc ? " ▲" : " ▼") : ""}
                  </th>
                ))}
                <th className="text-right font-medium py-1.5 pl-2">Cart.</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((r, i) => {
                const rv = rf(r.rating);
                return (
                  <tr key={`${r.id}-${i}`} className="border-b border-border/20 hover:bg-muted/40">
                    <td className="py-1.5 pr-2 sticky left-0 bg-card">
                      <div className="flex items-center gap-2 min-w-[150px]">
                        {teamLogoUrl(r.teamId) && <img src={teamLogoUrl(r.teamId)!} alt="" className="w-4 h-4 object-contain shrink-0" onError={hideOnError} />}
                        <span className="truncate">{r.number ? `${r.number}. ` : ""}{r.name}</span>
                        {r.pos && <span className="text-[9px] text-muted-foreground shrink-0">{r.pos}</span>}
                      </div>
                    </td>
                    <td className="text-right px-2 font-mono">{num(r.minutes) || "-"}</td>
                    <td className={`text-right px-2 font-mono font-semibold ${ratingColor(rv)}`}>{Number.isFinite(rv) ? rv.toFixed(1) : "-"}</td>
                    <td className="text-right px-2 font-mono">{num(r.shots_total) || "-"}</td>
                    <td className="text-right px-2 font-mono">{num(r.shots_on) || "-"}</td>
                    <td className="text-right px-2 font-mono">{num(r.passes) || "-"}</td>
                    <td className="text-right px-2 font-mono">{num(r.key_passes) || "-"}</td>
                    <td className="text-right px-2 font-mono">{num(r.tackles) || "-"}</td>
                    <td className="text-right pl-2 font-mono whitespace-nowrap">
                      {num(r.yellow) > 0 && <span className="text-amber-400">{num(r.yellow)}🟨</span>}
                      {num(r.red) > 0 && <span className="text-red-400 ml-1">{num(r.red)}🟥</span>}
                      {num(r.yellow) === 0 && num(r.red) === 0 && <span className="text-muted-foreground">-</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
