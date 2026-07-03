"use client";
import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Search, TrendingUp, CheckCircle2, XCircle } from "lucide-react";
import { getOddFromProb, calculateOverProb, calculateUnderProb, fairOddRange } from "@/lib/math";
import { PredictionResponse } from "@/lib/api";
import InfoTooltip from "@/components/platform/InfoTooltip";

const MARKET_OPTIONS = [
  { value: "gols", label: "Gols Totais" },
  { value: "chutes", label: "Finalizações Totais" },
  { value: "escanteios", label: "Escanteios Totais" },
  { value: "cartoes", label: "Cartões Totais" },
];

function getMarketDistribution(prediction: PredictionResponse, market: string) {
  if (market === "gols") return { mean: prediction.gols.estimativa, dist: (prediction.gols as any).distribuicao || [] };
  if (market === "chutes") return { mean: prediction.chutes.estimativa, dist: prediction.chutes.distribuicao || [] };
  if (market === "escanteios") return { mean: prediction.escanteios.total.estimativa, dist: prediction.escanteios.total.distribuicao || [] };
  if (market === "cartoes") return { mean: prediction.cartoes.total.estimativa, dist: prediction.cartoes.total.distribuicao || [] };
  return { mean: 0, dist: [] };
}

function LineExplorer({ prediction }: { prediction: PredictionResponse }) {
  const [market, setMarket] = useState("gols");
  const [side, setSide] = useState("over");
  const [line, setLine] = useState(2.5);
  const marketData = getMarketDistribution(prediction, market);
  const prob = side === "over" ? calculateOverProb(marketData.dist, line) : calculateUnderProb(marketData.dist, line);
  const minLine = 0.5;
  const maxLine = market === "gols" ? 8.5 : market === "chutes" ? 35.5 : market === "escanteios" ? 18.5 : 12.5;
  React.useEffect(() => { if (line > maxLine) setLine(maxLine - 0.5); }, [market, maxLine, line]);

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="bg-card border border-border/50 rounded-xl p-5">
      <h3 className="text-sm font-semibold mb-4 flex items-center gap-1.5">
        <Search className="w-4 h-4 text-cyan-500" /> Explorador de Linha
        <InfoTooltip text="Escolha o mercado, o lado (Over/Under) e escaneie a grade de odds justas pela CDF da distribuição." href="/como-funciona#explorador-de-linha" />
      </h3>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-5">
        <div>
          <Label className="text-xs text-muted-foreground mb-1.5 block">Mercado</Label>
          <Select value={market} onValueChange={(v) => { setMarket(v); setLine(v === "gols" ? 2.5 : v === "chutes" ? 20.5 : v === "escanteios" ? 9.5 : 3.5); }}>
            <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
            <SelectContent>{MARKET_OPTIONS.map((m) => <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div>
          <Label className="text-xs text-muted-foreground mb-1.5 block">Lado</Label>
          <div className="flex gap-1">
            <button onClick={() => setSide("over")} className={`flex-1 py-2 text-xs font-medium rounded-md transition ${side === "over" ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30" : "bg-muted text-muted-foreground"}`}>Over</button>
            <button onClick={() => setSide("under")} className={`flex-1 py-2 text-xs font-medium rounded-md transition ${side === "under" ? "bg-blue-500/20 text-blue-400 border border-blue-500/30" : "bg-muted text-muted-foreground"}`}>Under</button>
          </div>
        </div>
        <div>
          <Label className="text-xs text-muted-foreground mb-1.5 block text-center">Média Projetada</Label>
          <div className="h-9 flex items-center justify-center text-2xl font-bold font-mono">{marketData.mean}</div>
        </div>
      </div>
      <div className="mb-4">
        <Label className="text-xs text-muted-foreground mb-2 block">{side === "over" ? "Acima de" : "Abaixo de"} {line}</Label>
        <Slider value={[line]} onValueChange={([v]) => { const s = Math.floor(v) + 0.5; setLine(s > maxLine ? maxLine : s); }} min={minLine} max={maxLine} step={1} className="w-full" />
      </div>
      <div className="grid grid-cols-3 gap-4 bg-muted/50 rounded-lg p-4">
        <div className="text-center"><p className="text-[10px] text-muted-foreground mb-1">Linha</p><p className="text-base font-bold font-mono">{side === "over" ? "Acima de" : "Abaixo de"} {line}</p></div>
        <div className="text-center"><p className="text-[10px] text-muted-foreground mb-1">Probabilidade</p><p className="text-lg font-bold font-mono text-cyan-400">{(prob * 100).toFixed(1)}%</p></div>
        <div className="text-center"><p className="text-[10px] text-muted-foreground mb-1">Faixa de Odd Justa</p><p className="text-base font-bold font-mono text-emerald-400">{fairOddRange(prob)}</p></div>
      </div>
    </motion.div>
  );
}

function ValueBetting({ prediction }: { prediction: PredictionResponse }) {
  const [market, setMarket] = useState("gols");
  const [side, setSide] = useState("over");
  const [line, setLine] = useState(2.5);
  const [offeredOdd, setOfferedOdd] = useState("");
  const [oppositeOdd, setOppositeOdd] = useState("");
  const marketData = getMarketDistribution(prediction, market);
  const modelProb = side === "over" ? calculateOverProb(marketData.dist, line) : calculateUnderProb(marketData.dist, line);
  const fairOdd = getOddFromProb(modelProb);
  let deVigProb: number | null = null;
  if (offeredOdd && oppositeOdd) {
    const o1 = parseFloat(offeredOdd), o2 = parseFloat(oppositeOdd);
    if (o1 > 1 && o2 > 1) { const p1 = 1 / o1, p2 = 1 / o2; deVigProb = parseFloat((p1 / (p1 + p2)).toFixed(4)); }
  }
  const offered = parseFloat(offeredOdd);
  let ev: number | null = null, roiPercent: number | null = null;
  if (offered > 1) { ev = modelProb * (offered - 1) - (1 - modelProb); roiPercent = ((modelProb - 1 / offered) / (1 / offered)) * 100; }

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="bg-card border border-border/50 rounded-xl p-5">
      <h3 className="text-sm font-semibold mb-4 flex items-center gap-1.5">
        <TrendingUp className="w-4 h-4 text-emerald-500" /> Value Betting — Identificação de Assimetrias
        <InfoTooltip text="Compare a probabilidade do modelo com a odd da casa. EV positivo = assimetria a favor. O De-Vig remove a margem da banca." href="/como-funciona#value-betting" />
      </h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-5">
        <div>
          <Label className="text-xs text-muted-foreground mb-1.5 block">Mercado</Label>
          <Select value={market} onValueChange={(v) => { setMarket(v); setLine(v === "gols" ? 2.5 : v === "chutes" ? 20.5 : v === "escanteios" ? 9.5 : 3.5); }}>
            <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
            <SelectContent>{MARKET_OPTIONS.map((m) => <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div>
          <Label className="text-xs text-muted-foreground mb-1.5 block">Lado & Linha</Label>
          <div className="flex gap-1">
            <button onClick={() => setSide((s) => (s === "over" ? "under" : "over"))} className="px-3 py-2 text-xs font-medium rounded-md bg-muted shrink-0">{side === "over" ? "Over" : "Under"}</button>
            <Input type="number" step="0.5" value={line} onChange={(e) => setLine(parseFloat(e.target.value) || 0)} className="h-9 text-sm font-mono" />
          </div>
        </div>
        <div><Label className="text-xs text-muted-foreground mb-1.5 block">Odd Oferecida</Label><Input type="number" step="0.01" min="1.01" placeholder="Ex: 1.85" value={offeredOdd} onChange={(e) => setOfferedOdd(e.target.value)} className="h-9 text-sm font-mono" /></div>
        <div>
          <Label className="text-xs text-muted-foreground mb-1.5 block flex items-center gap-1">Odd Oposta (De-Vig)<InfoTooltip text="Odd do lado oposto para calcular o De-Vig." href="/como-funciona#de-vig" /></Label>
          <Input type="number" step="0.01" min="1.01" placeholder="Opcional" value={oppositeOdd} onChange={(e) => setOppositeOdd(e.target.value)} className="h-9 text-sm font-mono" />
        </div>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4 bg-muted/50 rounded-lg p-3">
        <div className="text-center"><p className="text-[10px] text-muted-foreground">Prob. Modelo</p><p className="text-sm font-bold font-mono">{(modelProb * 100).toFixed(1)}%</p></div>
        <div className="text-center"><p className="text-[10px] text-muted-foreground">Odd Justa</p><p className="text-sm font-bold font-mono">{fairOdd > 50 ? "50+" : fairOdd}</p></div>
        {deVigProb !== null && <div className="text-center"><p className="text-[10px] text-muted-foreground">Prob. De-Vig</p><p className="text-sm font-bold font-mono text-amber-400">{(deVigProb * 100).toFixed(1)}%</p></div>}
        {offered > 1 && <div className="text-center"><p className="text-[10px] text-muted-foreground">Prob. Implícita (Casa)</p><p className="text-sm font-bold font-mono text-muted-foreground">{((1 / offered) * 100).toFixed(1)}%</p></div>}
      </div>
      <AnimatePresence>
        {ev !== null && (
          <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} className={`rounded-lg p-4 border ${ev > 0 ? "bg-emerald-500/10 border-emerald-500/30" : "bg-red-500/10 border-red-500/30"}`}>
            <div className="flex items-center gap-2">
              {ev > 0 ? <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" /> : <XCircle className="w-5 h-5 text-red-400 shrink-0" />}
              <div>
                <p className={`text-sm font-bold ${ev > 0 ? "text-emerald-400" : "text-red-400"}`}>{ev > 0 ? "🟢 Valor Encontrado (EV+)" : "🔴 Sem Valor Proporcional"}</p>
                <p className="text-xs text-muted-foreground mt-0.5">EV: <span className="font-mono font-semibold">{ev > 0 ? "+" : ""}{(ev * 100).toFixed(2)}%</span>{roiPercent !== null && <span> · ROI Potencial: <span className="font-mono font-semibold">{roiPercent > 0 ? "+" : ""}{roiPercent.toFixed(1)}%</span></span>}</p>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

export default function BetLab({ prediction }: { prediction: PredictionResponse }) {
  return (
    <div className="space-y-6">
      <LineExplorer prediction={prediction} />
      <ValueBetting prediction={prediction} />
    </div>
  );
}
