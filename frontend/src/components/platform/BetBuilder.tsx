"use client";
import React, { useEffect, useState, useCallback } from "react";
import { CheckCircle2, Loader2, Lock, Sparkles, Ticket } from "lucide-react";
import { betsApi, type MarketOption, type BetResponse } from "@/lib/monetizationApi";
import { Button } from "@/components/ui/button";

const STATUS_LABEL: Record<string, string> = {
  awaiting_start: "Aguardando início",
  in_progress: "Em andamento",
  awaiting_settlement: "Aguardando liquidação",
  won: "Vencedora",
  lost: "Não vencedora",
  credit_consumed: "Crédito consumido",
  credit_refunded: "Crédito estornado",
  canceled: "Cancelada",
};

export default function BetBuilder({ analysisId, onConfirmed }: { analysisId: string; onConfirmed?: (b: BetResponse) => void }) {
  const [options, setOptions] = useState<MarketOption[]>([]);
  const [cap, setCap] = useState(2.0);
  const [selected, setSelected] = useState<string[]>([]);
  const [combined, setCombined] = useState<number | null>(null);
  const [valid, setValid] = useState(true);
  const [exceeds, setExceeds] = useState(false);
  const [autoPreview, setAutoPreview] = useState<{ label: string; odd: number }[]>([]);
  const [loadingMk, setLoadingMk] = useState(true);
  const [confirming, setConfirming] = useState(false);
  const [bet, setBet] = useState<BetResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    betsApi.markets(analysisId)
      .then((m) => { setOptions(m.options); setCap(m.max_combined_odd); })
      .catch((e) => setErr((e as Error).message))
      .finally(() => setLoadingMk(false));
  }, [analysisId]);

  const runPreview = useCallback(async (keys: string[]) => {
    try {
      const p = await betsApi.preview(analysisId, keys);
      setCombined(p.combined_odd);
      setValid(p.valid);
      setExceeds(p.exceeds_cap);
      if (keys.length === 0) setAutoPreview(p.selections.map((s) => ({ label: s.label, odd: s.odd })));
    } catch (e) {
      setErr((e as Error).message);
    }
  }, [analysisId]);

  useEffect(() => { if (!loadingMk) runPreview(selected); }, [selected, loadingMk, runPreview]);

  const toggle = (opt: MarketOption) => {
    setErr(null);
    setSelected((prev) => {
      if (prev.includes(opt.market_key)) return prev.filter((k) => k !== opt.market_key);
      // remove qualquer outra opção do mesmo grupo (mutuamente exclusivo)
      const sameGroup = options.filter((o) => o.group === opt.group).map((o) => o.market_key);
      return [...prev.filter((k) => !sameGroup.includes(k)), opt.market_key];
    });
  };

  async function confirm() {
    setConfirming(true); setErr(null);
    try {
      const b = await betsApi.create(analysisId, selected);
      setBet(b);
      onConfirmed?.(b);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setConfirming(false);
    }
  }

  if (bet) {
    return (
      <div className="bg-card border border-emerald-500/30 rounded-xl p-5">
        <h3 className="text-lg font-bold flex items-center gap-2 mb-3">
          <Lock className="w-5 h-5 text-emerald-500" /> Aposta confirmada
        </h3>
        <p className="text-xs text-muted-foreground mb-3">
          Sua aposta é imutável. {bet.auto_selected ? "Foi selecionada automaticamente (odd ~2,00)." : ""} Status:{" "}
          <b className="text-foreground">{STATUS_LABEL[bet.status] || bet.status}</b>.
        </p>
        <div className="space-y-1.5 mb-3">
          {bet.selections.map((s) => (
            <div key={s.market_key} className="flex justify-between text-sm border-b border-border/30 py-1.5">
              <span>{s.label}</span>
              <span className="font-mono font-semibold">{s.odd.toFixed(2)}</span>
            </div>
          ))}
        </div>
        <div className="flex justify-between items-center bg-emerald-500/10 rounded-lg p-3">
          <span className="text-sm font-medium">Odd combinada</span>
          <span className="text-xl font-mono font-bold text-emerald-600">{Number(bet.combined_odd).toFixed(2)}</span>
        </div>
      </div>
    );
  }

  if (loadingMk) return <div className="flex justify-center py-8"><Loader2 className="w-5 h-5 animate-spin text-muted-foreground" /></div>;

  const grouped = options.reduce<Record<string, MarketOption[]>>((acc, o) => {
    (acc[o.group] ||= []).push(o);
    return acc;
  }, {});
  const pct = combined ? Math.min(100, (combined / cap) * 100) : 0;

  return (
    <div className="bg-card border border-border/50 rounded-xl p-5">
      <h3 className="text-lg font-bold flex items-center gap-2 mb-1">
        <Ticket className="w-5 h-5 text-primary" /> Aposta Escolhida
      </h3>
      <p className="text-xs text-muted-foreground mb-4">
        Combine mercados desta análise. A odd combinada não pode passar de <b>{cap.toFixed(2)}</b>.
        Se você não escolher, selecionamos automaticamente uma aposta com odd próxima de {cap.toFixed(2)}.
      </p>

      {err && <div className="mb-3 text-sm rounded-md bg-red-500/10 text-red-600 p-3">{err}</div>}

      {/* seleção por grupos */}
      <div className="max-h-72 overflow-y-auto pr-1 space-y-3 mb-4 custom-scrollbar">
        {Object.entries(grouped).map(([group, opts]) => (
          <div key={group}>
            <p className="text-[10px] uppercase tracking-wide text-muted-foreground mb-1">{opts[0].label.split(" ").slice(0, 2).join(" ")}</p>
            <div className="flex flex-wrap gap-1.5">
              {opts.map((o) => {
                const on = selected.includes(o.market_key);
                return (
                  <button key={o.market_key} onClick={() => toggle(o)}
                    className={`px-2.5 py-1.5 rounded-md text-xs border transition ${on ? "bg-primary text-primary-foreground border-primary" : "bg-muted/40 hover:bg-muted border-border/50"}`}>
                    {o.label} <span className="font-mono opacity-80">@{o.odd.toFixed(2)}</span>
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {/* auto preview quando nada selecionado */}
      {selected.length === 0 && autoPreview.length > 0 && (
        <div className="mb-4 text-xs rounded-md bg-primary/5 border border-primary/20 p-3">
          <div className="flex items-center gap-1.5 font-medium mb-1"><Sparkles className="w-3.5 h-3.5 text-primary" /> Seleção automática (prévia)</div>
          {autoPreview.map((s, i) => <div key={i} className="flex justify-between text-muted-foreground"><span>{s.label}</span><span className="font-mono">@{s.odd.toFixed(2)}</span></div>)}
        </div>
      )}

      {/* odd combinada */}
      <div className="mb-4">
        <div className="flex justify-between items-baseline mb-1">
          <span className="text-sm text-muted-foreground">Odd combinada</span>
          <span className={`text-2xl font-mono font-bold ${exceeds ? "text-red-500" : "text-emerald-600"}`}>{combined?.toFixed(2) ?? "—"}</span>
        </div>
        <div className="h-2 rounded-full bg-muted overflow-hidden">
          <div className={`h-full transition-all ${exceeds ? "bg-red-500" : "bg-emerald-500"}`} style={{ width: `${pct}%` }} />
        </div>
        {exceeds && <p className="text-xs text-red-500 mt-1">Ultrapassa o limite de {cap.toFixed(2)}. Remova alguma seleção.</p>}
      </div>

      <Button onClick={confirm} disabled={confirming || exceeds || !valid} className="w-full">
        {confirming ? <Loader2 className="w-4 h-4 animate-spin" /> : (
          <><CheckCircle2 className="w-4 h-4 mr-2" /> {selected.length === 0 ? "Confirmar aposta automática" : "Confirmar aposta"}</>
        )}
      </Button>
      <p className="text-[11px] text-center text-muted-foreground mt-2">Após confirmar, a aposta não poderá ser editada ou excluída.</p>
    </div>
  );
}
