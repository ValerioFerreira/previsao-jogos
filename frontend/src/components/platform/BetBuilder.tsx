"use client";
import React, { useEffect, useState, useCallback, useMemo } from "react";
import { CheckCircle2, Loader2, Lock, Sparkles, Layers, XCircle } from "lucide-react";
import { betsApi, type MarketOption, type BetResponse } from "@/lib/monetizationApi";
import { Button } from "@/components/ui/button";
import { teamPt } from "@/lib/teamNames";

const STATUS_LABEL: Record<string, string> = {
  awaiting_start: "Aguardando início", in_progress: "Em andamento", awaiting_settlement: "Aguardando liquidação",
  won: "Vencedora", lost: "Não vencedora", credit_consumed: "Crédito consumido", credit_refunded: "Crédito estornado", canceled: "Cancelada",
};

// Categoria de mercado (aba) a partir do group de cada opção. `ou` = mercado Over/Under.
function marketOf(group: string): { key: string; label: string; ou: boolean } {
  if (group === "resultado") return { key: "resultado", label: "Resultado", ou: false };
  if (group === "btts") return { key: "btts", label: "Ambas Marcam", ou: false };
  if (group === "gols_ou2.5") return { key: "gols", label: "Gols (2.5)", ou: true };
  if (group.startsWith("escanteios_total:")) return { key: "escanteios", label: "Escanteios", ou: true };
  if (group.startsWith("cartoes_total:")) return { key: "cartoes", label: "Cartões", ou: true };
  if (group.startsWith("chutes_total:")) return { key: "chutes", label: "Finalizações", ou: true };
  if (group.startsWith("chutes_a_gol_total:")) return { key: "chutes_a_gol", label: "Finalizações a Gol", ou: true };
  return { key: "outros", label: "Outros", ou: false };
}
function lineOf(o: MarketOption): number {
  if (o.group.includes(":")) return parseFloat(o.group.split(":")[1]) || 0;
  if (o.group === "gols_ou2.5") return 2.5;
  return 0;
}

export default function BetBuilder({ analysisId, home, away, onConfirmed }: { analysisId: string; home?: string; away?: string; onConfirmed?: (b: BetResponse) => void }) {
  // Traduz nomes de seleção (em inglês nos rótulos do backend) para PT-BR.
  const tl = useCallback((s: string) => {
    let out = s;
    if (home) out = out.split(home).join(teamPt(home));
    if (away) out = out.split(away).join(teamPt(away));
    return out;
  }, [home, away]);
  const [options, setOptions] = useState<MarketOption[]>([]);
  const [cap, setCap] = useState(2.0);
  const [selected, setSelected] = useState<string[]>([]);
  const [combined, setCombined] = useState<number | null>(null);
  const [valid, setValid] = useState(true);
  const [exceeds, setExceeds] = useState(false);
  const [autoPreview, setAutoPreview] = useState<{ label: string; odd: number }[]>([]);
  const [showAutoPreview, setShowAutoPreview] = useState(false);
  const [loadingMk, setLoadingMk] = useState(true);
  const [confirming, setConfirming] = useState(false);
  const [bet, setBet] = useState<BetResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [activeMarket, setActiveMarket] = useState("resultado");

  useEffect(() => {
    betsApi.markets(analysisId)
      .then((m) => { setOptions(m.options); setCap(m.max_combined_odd); })
      .catch((e) => setErr((e as Error).message))
      .finally(() => setLoadingMk(false));
  }, [analysisId]);

  const runPreview = useCallback(async (keys: string[]) => {
    try {
      const p = await betsApi.preview(analysisId, keys);
      setCombined(p.combined_odd); setValid(p.valid); setExceeds(p.exceeds_cap);
      if (keys.length === 0) setAutoPreview(p.selections.map((s) => ({ label: s.label, odd: s.odd })));
    } catch (e) { setErr((e as Error).message); }
  }, [analysisId]);

  const regenerateAuto = useCallback(async () => {
    setShowAutoPreview(true);
    await runPreview([]);
  }, [runPreview]);

  useEffect(() => { if (!loadingMk) runPreview(selected); }, [selected, loadingMk, runPreview]);

  const byId = useMemo(() => Object.fromEntries(options.map((o) => [o.market_key, o])), [options]);
  const markets = useMemo(() => {
    const seen: Record<string, { key: string; label: string; ou: boolean }> = {};
    options.forEach((o) => { const m = marketOf(o.group); seen[m.key] = m; });
    const order = ["resultado", "btts", "gols", "escanteios", "cartoes", "chutes", "chutes_a_gol", "outros"];
    return order.filter((k) => seen[k]).map((k) => seen[k]);
  }, [options]);

  const active = markets.find((m) => m.key === activeMarket) || markets[0];
  const activeOpts = useMemo(() => options.filter((o) => marketOf(o.group).key === active?.key), [options, active]);

  const toggle = (o: MarketOption) => {
    setErr(null);
    setSelected((prev) => {
      if (prev.includes(o.market_key)) return prev.filter((k) => k !== o.market_key);
      // Um por mercado-base: trocar remove qualquer seleção interdependente do mesmo
      // mercado (ex.: duas linhas de escanteios/cartões, ou Menos 1,5 + Menos 2,5 gols).
      const baseKey = marketOf(o.group).key;
      const sameBase = options.filter((x) => marketOf(x.group).key === baseKey).map((x) => x.market_key);
      return [...prev.filter((k) => !sameBase.includes(k)), o.market_key];
    });
  };

  async function confirm() {
    setConfirming(true); setErr(null);
    try {
      const b = await betsApi.create(analysisId, selected);
      setBet(b); onConfirmed?.(b);
    } catch (e) { setErr((e as Error).message); } finally { setConfirming(false); }
  }

  // ---- aposta confirmada (imutável) ----
  if (bet) {
    return (
      <div className="bg-card border border-emerald-500/30 rounded-xl p-5">
        <h3 className="text-lg font-bold flex items-center gap-2 mb-3"><Lock className="w-5 h-5 text-emerald-500" /> Aposta confirmada</h3>
        <p className="text-xs text-muted-foreground mb-3">
          Sua aposta é imutável. {bet.auto_selected ? "Foi selecionada automaticamente (odd ~2,00)." : ""} Status:{" "}
          <b className="text-foreground">{STATUS_LABEL[bet.status] || bet.status}</b>.
        </p>
        <div className="space-y-1.5 mb-3">
          {bet.selections.map((s) => (
            <div key={s.market_key} className="flex justify-between text-sm border-b border-border/30 py-1.5"><span>{tl(s.label)}</span><span className="font-mono font-semibold">{s.odd.toFixed(2)}</span></div>
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

  const overs = activeOpts.filter((o) => o.selection === "over").sort((a, b) => lineOf(a) - lineOf(b));
  const unders = activeOpts.filter((o) => o.selection === "under").sort((a, b) => lineOf(a) - lineOf(b));
  const pct = combined ? Math.min(100, (combined / cap) * 100) : 0;

  const OptBtn = ({ o, showLineOnly }: { o: MarketOption; showLineOnly?: boolean }) => {
    const on = selected.includes(o.market_key);
    return (
      <button onClick={() => toggle(o)}
        className={`px-2.5 py-1.5 rounded-md text-xs border transition text-left ${on ? "bg-primary text-primary-foreground border-primary" : "bg-muted/40 hover:bg-muted border-border/50"}`}>
        {showLineOnly ? lineOf(o).toFixed(1) : tl(o.label)} <span className="font-mono opacity-80">@{o.odd.toFixed(2)}</span>
      </button>
    );
  };

  return (
    <div className="bg-card border border-border/50 rounded-xl p-5">
      <h3 className="text-lg font-bold flex items-center gap-2 mb-1"><Layers className="w-5 h-5 text-primary" /> Monte sua Aposta</h3>
      <p className="text-xs text-muted-foreground mb-4">
        Selecione mercados desta análise para montar sua aposta. A odd combinada não pode passar de <b>{cap.toFixed(2)}</b>.
        Se você não escolher nada, selecionamos automaticamente uma aposta com odd próxima de {cap.toFixed(2)}.
      </p>
      {err && <div className="mb-3 text-sm rounded-md bg-red-500/10 text-red-600 p-3">{err}</div>}

      {/* abas por mercado */}
      <div className="flex flex-wrap gap-1.5 mb-4">
        {markets.map((m) => (
          <button key={m.key} onClick={() => setActiveMarket(m.key)}
            className={`px-3 py-1.5 rounded-md text-xs font-medium border transition ${active?.key === m.key ? "bg-purple-500/10 border-purple-500/40 text-foreground" : "border-border/50 text-muted-foreground hover:text-foreground"}`}>
            {m.label}
          </button>
        ))}
      </div>

      {/* opções do mercado ativo */}
      {active?.ou ? (
        <div className="grid grid-cols-2 gap-4 mb-4">
          <div>
            <p className="text-[11px] uppercase tracking-wide text-emerald-500 font-semibold mb-2">Acima de</p>
            <div className="flex flex-col gap-1.5">{overs.map((o) => <OptBtn key={o.market_key} o={o} showLineOnly />)}</div>
          </div>
          <div>
            <p className="text-[11px] uppercase tracking-wide text-blue-500 font-semibold mb-2">Abaixo de</p>
            <div className="flex flex-col gap-1.5">{unders.map((o) => <OptBtn key={o.market_key} o={o} showLineOnly />)}</div>
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap gap-1.5 mb-4">{activeOpts.map((o) => <OptBtn key={o.market_key} o={o} />)}</div>
      )}

      {/* seleções atuais (de todos os mercados) — removíveis */}
      {selected.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-4">
          {selected.map((k) => byId[k]).filter(Boolean).map((o) => (
            <button key={o.market_key} onClick={() => toggle(o)} className="flex items-center gap-1 px-2 py-1 rounded-md text-[11px] bg-primary/10 border border-primary/30 hover:bg-primary/20 transition">
              {tl(o.label)} @{o.odd.toFixed(2)} <XCircle className="w-3 h-3 opacity-60" />
            </button>
          ))}
        </div>
      )}

      {/* auto-seleção: botão + prévia opcional quando nada escolhido manualmente */}
      {selected.length === 0 && (
        <div className="mb-4">
          <button
            onClick={regenerateAuto}
            className="w-full flex items-center justify-center gap-1.5 text-xs font-medium rounded-md border border-primary/30 bg-primary/5 hover:bg-primary/10 p-2.5 transition-colors"
          >
            <Sparkles className="w-3.5 h-3.5 text-primary" /> {showAutoPreview ? "Gerar outra sugestão automática" : "Selecionar Automaticamente"}
          </button>
          {showAutoPreview && autoPreview.length > 0 && (
            <div className="mt-2 text-xs rounded-md bg-primary/5 border border-primary/20 p-3">
              <div className="flex items-center gap-1.5 font-medium mb-1"><Sparkles className="w-3.5 h-3.5 text-primary" /> Seleção automática (prévia)</div>
              {autoPreview.map((s, i) => <div key={i} className="flex justify-between text-muted-foreground"><span>{tl(s.label)}</span><span className="font-mono">@{s.odd.toFixed(2)}</span></div>)}
            </div>
          )}
        </div>
      )}

      {/* barra de odd combinada */}
      <div className="mb-4">
        <div className="flex justify-between items-baseline mb-1">
          <span className="text-sm text-muted-foreground">Odd combinada</span>
          <span className={`text-2xl font-mono font-bold ${exceeds ? "text-red-500" : "text-emerald-600"}`}>{combined?.toFixed(2) ?? "—"}</span>
        </div>
        <div className="h-2 rounded-full bg-muted overflow-hidden"><div className={`h-full transition-all ${exceeds ? "bg-red-500" : "bg-emerald-500"}`} style={{ width: `${pct}%` }} /></div>
        {exceeds && <p className="text-xs text-red-500 mt-1">Ultrapassa o limite de {cap.toFixed(2)}. Remova alguma seleção.</p>}
      </div>

      <Button onClick={confirm} disabled={confirming || exceeds || !valid} className="w-full">
        {confirming ? <Loader2 className="w-4 h-4 animate-spin" /> : (<><CheckCircle2 className="w-4 h-4 mr-2" /> {selected.length === 0 ? "Confirmar aposta automática" : "Confirmar aposta"}</>)}
      </Button>
      <p className="text-[11px] text-center text-muted-foreground mt-2">Após confirmar, a aposta não poderá ser editada ou excluída.</p>
    </div>
  );
}
