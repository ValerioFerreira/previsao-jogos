"use client";
import React from "react";
import { api, RefereeStatsResponse } from "@/lib/api";
import { TeamSelect } from "@/components/platform/TeamSelect";
import InfoTooltip from "@/components/platform/InfoTooltip";

function verdict(avg: number, bench: number): { label: string; color: string; icon: string } {
  if (bench <= 0) return { label: "—", color: "text-muted-foreground", icon: "⚖️" };
  if (avg >= bench * 1.12) return { label: "Rigoroso", color: "text-red-400", icon: "🔴" };
  if (avg <= bench * 0.9) return { label: "Tolerante", color: "text-emerald-400", icon: "🟢" };
  return { label: "Mediano", color: "text-amber-400", icon: "🟡" };
}

// Barra comparativa: valor do árbitro (colorido) vs marcador da média geral.
function CompareBar({ label, value, bench, unit, accent }: { label: string; value: number; bench: number; unit: string; accent: string }) {
  const max = Math.max(value, bench) * 1.35 || 1;
  const vp = Math.min(100, (value / max) * 100);
  const bp = Math.min(100, (bench / max) * 100);
  const diff = bench > 0 ? Math.round(((value - bench) / bench) * 100) : 0;
  return (
    <div>
      <div className="flex items-center justify-between text-[11px] mb-1">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-mono">
          <b style={{ color: accent }}>{value.toFixed(2)}</b>
          <span className="text-muted-foreground"> / méd. {bench.toFixed(2)} {unit}</span>
          {diff !== 0 && <span className={diff > 0 ? "text-red-400 ml-1" : "text-emerald-400 ml-1"}>({diff > 0 ? "+" : ""}{diff}%)</span>}
        </span>
      </div>
      <div className="relative h-2.5 rounded-full bg-muted overflow-visible">
        <div className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${vp}%`, backgroundColor: accent }} />
        <div className="absolute inset-y-[-3px] w-0.5 bg-foreground/70" style={{ left: `${bp}%` }} title={`Média geral: ${bench.toFixed(2)}`} />
      </div>
    </div>
  );
}

export default function FatorArbitro() {
  const [referees, setReferees] = React.useState<string[]>([]);
  const [ref, setRef] = React.useState("");
  const [stats, setStats] = React.useState<RefereeStatsResponse | null>(null);
  const [loading, setLoading] = React.useState(false);

  React.useEffect(() => { api.referees().then((r) => setReferees(r.referees)).catch(() => {}); }, []);
  React.useEffect(() => {
    if (!ref) { setStats(null); return; }
    setLoading(true);
    api.refereeStats(ref).then(setStats).catch(() => setStats(null)).finally(() => setLoading(false));
  }, [ref]);

  const v = stats && stats.n_card_matches > 0 ? verdict(stats.avg_cards, stats.bench_cards) : null;
  const lowConf = stats && stats.n_card_matches > 0 && stats.n_card_matches < 5;

  return (
    <div className="bg-card border border-border/50 rounded-xl p-5">
      <h3 className="text-sm font-semibold mb-1 flex items-center gap-1.5">
        Fator Árbitro
        <InfoTooltip text="Tendência disciplinar do árbitro designado: média de cartões e faltas por jogo comparada à média geral, a partir do histórico com detalhe. Útil para os mercados de cartões. Informe o árbitro da partida." />
      </h3>
      <p className="text-xs text-muted-foreground mb-3">Informe o árbitro para ver o perfil disciplinar</p>
      <div className="mb-4 max-w-xs">
        <TeamSelect value={ref} onValueChange={setRef} teams={referees} labelFn={(s) => s} placeholder="Buscar árbitro..." searchPlaceholder="Buscar árbitro..." />
      </div>

      {loading && <p className="text-xs text-muted-foreground">Carregando…</p>}

      {!loading && stats && stats.n_card_matches === 0 && (
        <p className="text-xs text-muted-foreground italic">Sem histórico detalhado suficiente para este árbitro.</p>
      )}

      {!loading && stats && v && (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <span className="text-lg">{v.icon}</span>
            <div>
              <p className={`text-sm font-semibold ${v.color}`}>{v.label}</p>
              <p className="text-[10px] text-muted-foreground">
                {stats.avg_yellow.toFixed(1)}🟨 {stats.avg_red.toFixed(2)}🟥 por jogo · {stats.n_card_matches} jogos analisados
                {lowConf && <span className="text-amber-400"> · amostra pequena</span>}
              </p>
            </div>
          </div>
          <CompareBar label="Cartões por jogo" value={stats.avg_cards} bench={stats.bench_cards} unit="" accent="#f59e0b" />
          {stats.n_foul_matches > 0 && (
            <CompareBar label="Faltas por jogo" value={stats.avg_fouls} bench={stats.bench_fouls} unit="" accent="#06b6d4" />
          )}
          <p className="text-[10px] text-muted-foreground">A barra clara marca a média geral de todos os árbitros da base.</p>
        </div>
      )}
    </div>
  );
}
