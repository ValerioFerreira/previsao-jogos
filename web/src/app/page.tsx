"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { AlertCircle, Loader2, RefreshCcw, RotateCcw, Server, TrendingUp, AlertTriangle, CheckCircle2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api, CountPrediction, H2HResponse, NumericLineMarket, NumericPrediction, OddsMarket, PredictionResponse, TeamResponse, RecentMatch, Anomaly } from "@/lib/api";

// As 10 features de alto impacto (analise de importancia, Passo 3). Destas, 7 sao
// editaveis por selecao (abaixo); as outras 3 entram por controles dedicados:
// neutral (checkbox), tournament_weight (dropdown de competicao) e h2h_home_gd_mean
// (slider de confronto direto). elo_diff e derivado de elo_pre dos dois lados.
const PRIMARY_FIELDS = [
  "elo_pre",
  "gf_l5",
  "ga_l5",
  "days_rest",
  "sb_shots_l5",
  "sb_corners_l5",
  "sb_cards_l5",
];

const LABELS: Record<string, string> = {
  elo_pre: "Rating Elo atual",
  gf_l5: "Gols feitos ult. 5",
  ga_l5: "Gols sofridos ult. 5",
  days_rest: "Dias de descanso",
  sb_shots_l5: "Finalizacoes/jogo ult. 5",
  sb_corners_l5: "Escanteios/jogo ult. 5",
  sb_cards_l5: "Cartoes/jogo ult. 5",
};

// Faixas para a edicao CONTROLADA por slider (substitui a antiga edicao livre).
// decimals = casas exibidas. A faixa efetiva sempre engloba o valor automatico.
type FeatureRange = { min: number; max: number; step: number; decimals: number };
const FEATURE_RANGES: Record<string, FeatureRange> = {
  elo_pre: { min: 1000, max: 2200, step: 5, decimals: 0 },
  gf_l5: { min: 0, max: 5, step: 0.05, decimals: 2 },
  ga_l5: { min: 0, max: 5, step: 0.05, decimals: 2 },
  days_rest: { min: 0, max: 90, step: 1, decimals: 0 },
  sb_shots_l5: { min: 0, max: 30, step: 0.1, decimals: 1 },
  sb_corners_l5: { min: 0, max: 12, step: 0.1, decimals: 1 },
  sb_cards_l5: { min: 0, max: 8, step: 0.1, decimals: 1 },
  h2h_home_gd_mean: { min: -3, max: 3, step: 0.1, decimals: 2 },
};

type EditableValues = Record<string, string>;

function formatDefault(value: number | undefined) {
  return value === undefined || value === null || Number.isNaN(Number(value)) ? "" : String(Number(value));
}

function asEditable(defaults: Record<string, number>, fields: string[]) {
  return Object.fromEntries(fields.map((field) => [field, formatDefault(defaults[field])]));
}

// Considera "alterado" se difere do automatico por mais de meio passo do slider.
function isEdited(value: string | undefined, automatic: number | undefined, step = 1e-9) {
  if (value === undefined || value.trim() === "" || automatic === undefined) return false;
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return false;
  return Math.abs(numeric - automatic) > step / 2;
}

function changedValues(values: EditableValues, defaults: Record<string, number>) {
  const output: Record<string, number> = {};
  for (const [key, value] of Object.entries(values)) {
    if (value.trim() === "") continue;
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) continue;
    const original = defaults[key];
    const step = FEATURE_RANGES[key]?.step ?? 1e-9;
    if (original === undefined || Math.abs(numeric - Number(original)) > step / 2) {
      output[key] = numeric;
    }
  }
  return output;
}

function confidenceClass(confidence: string) {
  const normalized = confidence.normalize("NFD").replace(/\p{Diacritic}/gu, "");
  if (normalized === "Alta") return "bg-emerald-100 text-emerald-800 border-emerald-200";
  if (normalized === "Media") return "bg-amber-100 text-amber-800 border-amber-200";
  return "bg-red-100 text-red-800 border-red-200";
}

// Confiabilidade do confronto pelo volume de historico direto (h2h). Mais jogos =
// mais sinal especifico do duelo; com poucos, a previsao se apoia em Elo e forma.
function matchupReliability(h2hPlayed: number): { label: string; cls: string; note: string } {
  if (h2hPlayed >= 8)
    return {
      label: "Alta",
      cls: "bg-emerald-100 text-emerald-800 border-emerald-200",
      note: `${h2hPlayed} confrontos diretos: amostra robusta para o historico do duelo.`,
    };
  if (h2hPlayed >= 4)
    return {
      label: "Media",
      cls: "bg-amber-100 text-amber-800 border-amber-200",
      note: `${h2hPlayed} confrontos diretos: amostra moderada; o historico do duelo pesa menos.`,
    };
  return {
    label: "Baixa",
    cls: "bg-red-100 text-red-800 border-red-200",
    note: `${h2hPlayed} confronto(s) direto(s): pouca historia entre as equipes; a previsao se apoia mais no Elo e na forma recente.`,
  };
}

function ApiStatus({ status, error }: { status: "checking" | "ok" | "error"; error: string | null }) {
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <Badge variant={status === "ok" ? "secondary" : status === "error" ? "destructive" : "outline"} className="gap-2">
        {status === "checking" ? <Loader2 className="h-3 w-3 animate-spin" /> : <Server className="h-3 w-3" />}
        {status === "checking" ? "Acordando API" : status === "ok" ? "API online" : "API indisponivel"}
      </Badge>
      {error ? <span className="text-muted-foreground">{error}</span> : null}
    </div>
  );
}

function TeamSelect({
  id,
  label,
  value,
  teams,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  teams: string[];
  onChange: (value: string) => void;
}) {
  return (
    <div className="space-y-2">
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      <Input id={id} list={`${id}-teams`} value={value} onChange={(event) => onChange(event.target.value)} autoComplete="off" />
      <datalist id={`${id}-teams`}>
        {teams.map((team) => (
          <option value={team} key={team} />
        ))}
      </datalist>
    </div>
  );
}

// Edicao CONTROLADA de uma feature: slider bounded (a faixa engloba o valor automatico),
// valor exibido, marca editado/automatico e botao de reset. Substitui a edicao livre.
function FeatureSlider({
  id,
  label,
  value,
  automatic,
  range,
  onChange,
  onReset,
}: {
  id: string;
  label: string;
  value: string | undefined;
  automatic: number | undefined;
  range: FeatureRange;
  onChange: (value: string) => void;
  onReset: () => void;
}) {
  const current = value !== undefined && value.trim() !== "" ? Number(value) : automatic;
  const edited = isEdited(value, automatic, range.step);
  const safe = Number.isFinite(current as number) ? (current as number) : range.min;
  const lo = Math.min(range.min, safe);
  const hi = Math.max(range.max, safe);
  const display = Number.isFinite(current as number) ? (current as number).toFixed(range.decimals) : "—";
  return (
    <div className="rounded-lg border bg-card p-3">
      <div className="mb-2 flex items-start justify-between gap-2">
        <label htmlFor={id} className="text-sm font-medium leading-5">
          {label}
        </label>
        <Badge variant="outline" className={edited ? "border-primary text-primary" : "text-muted-foreground"}>
          {edited ? "editado" : "automatico"}
        </Badge>
      </div>
      <div className="flex items-center gap-3">
        <input
          id={id}
          type="range"
          min={lo}
          max={hi}
          step={range.step}
          value={safe}
          onChange={(event) => onChange(event.target.value)}
          className="w-full accent-primary"
        />
        <span className="w-12 shrink-0 text-right text-sm font-medium tabular-nums">{display}</span>
        <Button type="button" variant="outline" size="icon" title="Restaurar valor automatico" onClick={onReset}>
          <RotateCcw className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}

function TeamFields({
  title,
  snapshot,
  values,
  onChange,
  onReset,
}: {
  title: string;
  snapshot: TeamResponse | null;
  values: EditableValues;
  onChange: (field: string, value: string) => void;
  onReset: (field: string) => void;
}) {
  const fields = useMemo(
    () => PRIMARY_FIELDS.filter((field) => snapshot?.bases.includes(field) && FEATURE_RANGES[field]),
    [snapshot],
  );

  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-base font-semibold">{title}</h2>
        <p className="text-sm text-muted-foreground">
          Arraste para simular cenarios. Cada slider parte do valor automatico da API.
        </p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        {fields.map((field) => (
          <FeatureSlider
            key={field}
            id={`${title}-${field}`}
            label={LABELS[field] || field}
            value={values[field]}
            automatic={snapshot?.defaults[field]}
            range={FEATURE_RANGES[field]}
            onChange={(value) => onChange(field, value)}
            onReset={() => onReset(field)}
          />
        ))}
      </div>
    </section>
  );
}

function OddsText({ market }: { market: OddsMarket }) {
  return (
    <span className="text-sm text-muted-foreground">
      Odd justa {market.odd_justa.toFixed(2)} · faixa {market.faixa_odd_justa.min.toFixed(2)}-{market.faixa_odd_justa.max.toFixed(2)}
    </span>
  );
}

function NumericCard({ title, metric, line }: { title: string; metric: NumericPrediction; line?: NumericLineMarket }) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle>{title}</CardTitle>
            <CardDescription>Intervalo 80%: {metric.intervalo[0]} a {metric.intervalo[1]}</CardDescription>
          </div>
          <Badge variant="outline" className={confidenceClass(metric.confianca)}>
            {metric.confianca}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="text-3xl font-semibold">{metric.estimativa}</div>
        {line?.disponivel ? (
          <div className="rounded-md bg-muted p-3 text-sm">
            <div className="font-medium">Linha {line.linha}</div>
            <div className="mt-1 grid gap-1">
              <div>Over: <OddsText market={line.over} /></div>
              <div>Under: <OddsText market={line.under} /></div>
            </div>
          </div>
        ) : line ? (
          <p className="text-sm text-muted-foreground">{line.motivo}</p>
        ) : null}
      </CardContent>
    </Card>
  );
}

// Grade completa de linhas over/under derivada da CDF real (PMF do modelo de contagem).
// Destaca a linha mais equilibrada (over mais proximo de 50%).
function LinesGrid({ linhas }: { linhas: CountPrediction["linhas"] }) {
  const entries = Object.entries(linhas).sort((a, b) => Number(a[0]) - Number(b[0]));
  let balancedKey = entries[0]?.[0];
  let bestDist = Infinity;
  for (const [key, lado] of entries) {
    const dist = Math.abs(lado.over.prob - 50);
    if (dist < bestDist) {
      bestDist = dist;
      balancedKey = key;
    }
  }
  return (
    <div className="overflow-hidden rounded-md border text-sm">
      <div className="grid grid-cols-3 bg-muted/60 px-3 py-1.5 text-xs font-medium text-muted-foreground">
        <span>Linha</span>
        <span className="text-right">Over</span>
        <span className="text-right">Under</span>
      </div>
      {entries.map(([linha, lado]) => {
        const balanced = linha === balancedKey;
        return (
          <div
            key={linha}
            className={`grid grid-cols-3 items-center border-t px-3 py-1.5 ${balanced ? "bg-primary/5 font-medium" : ""}`}
          >
            <span>
              {linha}
              {balanced ? <span className="ml-1 text-[10px] uppercase tracking-wide text-primary">equilibrada</span> : null}
            </span>
            <span className="text-right tabular-nums">
              {lado.over.prob}% <span className="text-muted-foreground">· {lado.over.odd_justa.toFixed(2)}</span>
            </span>
            <span className="text-right tabular-nums">
              {lado.under.prob}% <span className="text-muted-foreground">· {lado.under.odd_justa.toFixed(2)}</span>
            </span>
          </div>
        );
      })}
    </div>
  );
}

function getOverProbability(line: number, distribuicao: number[]): number {
  const startIdx = Math.floor(line + 1);
  let sum = 0;
  for (let k = startIdx; k < distribuicao.length; k++) {
    sum += distribuicao[k] || 0;
  }
  return sum * 100;
}

function InteractiveLineSelector({
  title,
  market
}: {
  title: string;
  market: CountPrediction;
}) {
  const [targetProb, setTargetProb] = useState(70);
  const [oddInput, setOddInput] = useState("1.43");
  const [mode, setMode] = useState<"prob" | "odd">("prob");
  const [showTable, setShowTable] = useState(false);

  const lines = useMemo(() => {
    const titleL = title.toLowerCase();
    const arr: number[] = [];
    if (titleL.includes("escanteio") || titleL.includes("corner")) {
      for (let l = 4.5; l <= 14.5; l += 1.0) arr.push(l);
    } else if (titleL.includes("cartao") || titleL.includes("card")) {
      for (let l = 1.5; l <= 6.5; l += 1.0) arr.push(l);
    } else if (titleL.includes("chute") || titleL.includes("shot") || titleL.includes("finaliza")) {
      for (let l = 14.5; l <= 28.5; l += 1.0) arr.push(l);
    } else {
      return Object.keys(market.linhas).map(Number).sort((a, b) => a - b);
    }
    return arr;
  }, [title, market]);

  const handleProbChange = (val: number) => {
    setTargetProb(val);
    const odd = 100 / val;
    setOddInput(odd.toFixed(2));
  };

  const handleOddChange = (val: string) => {
    setOddInput(val);
    const oddVal = Number(val);
    if (Number.isFinite(oddVal) && oddVal > 1) {
      const prob = 100 / oddVal;
      setTargetProb(Math.min(99, Math.max(1, Math.round(prob))));
    }
  };

  const bestLine = useMemo(() => {
    let pick = lines[0];
    let pickProb = 0;
    for (const L of lines) {
      const prob = getOverProbability(L, market.distribuicao);
      if (prob >= targetProb) {
        pick = L;
        pickProb = prob;
      }
    }
    if (pickProb < targetProb) {
      pick = lines[0];
    }
    return pick;
  }, [lines, targetProb, market.distribuicao]);

  const bestProb = useMemo(() => getOverProbability(bestLine, market.distribuicao), [bestLine, market.distribuicao]);
  const bestOdd = bestProb > 0 ? 100 / bestProb : 0;

  const toggleBtn = (active: boolean) =>
    `rounded-md border px-2 py-1 text-xs transition ${
      active ? "border-primary bg-primary/10 font-medium text-primary" : "text-muted-foreground hover:bg-muted"
    }`;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2 border-t pt-2">
        <div className="flex gap-1.5">
          <button type="button" className={toggleBtn(mode === "prob")} onClick={() => setMode("prob")}>
            Prob.
          </button>
          <button type="button" className={toggleBtn(mode === "odd")} onClick={() => setMode("odd")}>
            Odd
          </button>
        </div>
        <button
          type="button"
          onClick={() => setShowTable(!showTable)}
          className="text-xs text-muted-foreground hover:underline"
        >
          {showTable ? "Ocultar Grade" : "Ver Grade"}
        </button>
      </div>

      {showTable ? (
        <LinesGrid linhas={market.linhas} />
      ) : (
        <div className="space-y-3 rounded-md bg-muted/40 p-2.5 border">
          {mode === "prob" ? (
            <div className="space-y-1">
              <div className="flex justify-between text-xs">
                <span className="text-muted-foreground">Probabilidade-alvo</span>
                <span className="font-semibold tabular-nums">{targetProb}%</span>
              </div>
              <input
                type="range"
                min={10}
                max={95}
                step={1}
                value={targetProb}
                onChange={(event) => handleProbChange(Number(event.target.value))}
                className="w-full accent-primary h-1"
              />
            </div>
          ) : (
            <div className="flex items-center justify-between gap-2 text-xs">
              <label htmlFor={`odd-alvo-${title}`} className="text-muted-foreground">
                Odd-alvo
              </label>
              <input
                id={`odd-alvo-${title}`}
                type="number"
                step="0.05"
                min="1.05"
                max="10.0"
                value={oddInput}
                onChange={(event) => handleOddChange(event.target.value)}
                className="w-20 rounded border bg-card px-2 py-0.5 text-right tabular-nums focus:outline-none"
              />
            </div>
          )}

          <div className="border-t pt-2 space-y-1">
            <div className="text-[10px] uppercase font-bold text-muted-foreground">Aposta Recomendada</div>
            <div className="flex justify-between items-baseline">
              <span className="text-sm font-bold text-primary">Over {bestLine.toFixed(1)}</span>
              <span className="text-xs tabular-nums font-semibold">
                {bestProb.toFixed(1)}% <span className="text-muted-foreground">({bestOdd.toFixed(2)})</span>
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// Card de mercado de contagem (chutes/escanteios/cartoes): estimativa + intervalo + grade O/U.
function CountCard({ title, market }: { title: string; market: CountPrediction }) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle>{title}</CardTitle>
            <CardDescription>
              Intervalo 80%: {market.intervalo[0]} a {market.intervalo[1]}
            </CardDescription>
          </div>
          <Badge variant="outline" className={confidenceClass(market.confianca)}>
            {market.confianca}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="text-3xl font-semibold">{market.estimativa}</div>
        <InteractiveLineSelector title={title} market={market} />
      </CardContent>
    </Card>
  );
}

// Secao de um mercado com tres recortes (mandante / visitante / total).
function MarketSection({
  title,
  markets,
  home,
  away,
}: {
  title: string;
  markets: Record<string, CountPrediction>;
  home: string;
  away: string;
}) {
  return (
    <section className="space-y-3">
      <h3 className="text-base font-semibold">{title}</h3>
      <div className="grid gap-4 md:grid-cols-3">
        {markets[home] ? <CountCard title={home} market={markets[home]} /> : null}
        {markets[away] ? <CountCard title={away} market={markets[away]} /> : null}
        {markets.total ? <CountCard title="Total da partida" market={markets.total} /> : null}
      </div>
    </section>
  );
}

type ExplorerMarket = { key: string; label: string; market: CountPrediction };

// A partir da PMF (distribuicao), deriva a prob over/under de TODAS as linhas .5 possiveis,
// nao so as 5-6 da grade do backend. over(t-0.5) = P(X >= t) = soma da cauda da PMF.
function buildLineProbs(pmf: number[]): { line: number; over: number; under: number }[] {
  const n = pmf.length;
  const suffix = new Array(n + 1).fill(0);
  for (let k = n - 1; k >= 0; k--) suffix[k] = suffix[k + 1] + (pmf[k] || 0);
  const out: { line: number; over: number; under: number }[] = [];
  for (let t = 1; t <= n - 1; t++) {
    const over = suffix[t] * 100;
    out.push({ line: t - 0.5, over, under: 100 - over });
  }
  return out;
}

// Explorador interativo: o usuario escolhe um mercado, um lado (over/under) e uma
// probabilidade-alvo (ou uma odd), e ve a linha cuja prob real mais se aproxima do alvo.
function LineExplorer({ markets }: { markets: ExplorerMarket[] }) {
  const [marketKey, setMarketKey] = useState(markets[0]?.key ?? "");
  const [side, setSide] = useState<"over" | "under">("over");
  const [mode, setMode] = useState<"prob" | "odd">("prob");
  const [targetProb, setTargetProb] = useState(60);
  const [oddInput, setOddInput] = useState("1.80");

  const selected = markets.find((m) => m.key === marketKey) ?? markets[0];
  const lineProbs = useMemo(() => (selected ? buildLineProbs(selected.market.distribuicao) : []), [selected]);

  const oddValue = Number(oddInput);
  const target = mode === "prob" ? targetProb : Number.isFinite(oddValue) && oddValue > 1 ? 100 / oddValue : NaN;

  const best = useMemo(() => {
    if (!lineProbs.length || !Number.isFinite(target)) return null;
    let pick = lineProbs[0];
    let bestDist = Infinity;
    for (const candidate of lineProbs) {
      const prob = side === "over" ? candidate.over : candidate.under;
      const dist = Math.abs(prob - target);
      if (dist < bestDist) {
        bestDist = dist;
        pick = candidate;
      }
    }
    return pick;
  }, [lineProbs, target, side]);

  if (!selected) return null;

  const bestProb = best ? (side === "over" ? best.over : best.under) : NaN;
  const bestOdd = Number.isFinite(bestProb) && bestProb > 0 ? 100 / bestProb : NaN;

  const toggle = (active: boolean) =>
    `rounded-md border px-3 py-1.5 text-sm transition ${
      active ? "border-primary bg-primary/10 font-medium text-primary" : "text-muted-foreground hover:bg-muted"
    }`;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Explorador de linha</CardTitle>
        <CardDescription>
          Escolha a probabilidade-alvo (ou uma odd) e veja a linha cuja chance real mais se aproxima, com a odd justa.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <label htmlFor="explorer-market" className="text-sm font-medium">
              Mercado
            </label>
            <select
              id="explorer-market"
              value={marketKey}
              onChange={(event) => setMarketKey(event.target.value)}
              className="h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            >
              {markets.map((item) => (
                <option value={item.key} key={item.key}>
                  {item.label}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-2">
            <span className="text-sm font-medium">Lado</span>
            <div className="flex gap-2">
              <button type="button" className={toggle(side === "over")} onClick={() => setSide("over")}>
                Over (mais que)
              </button>
              <button type="button" className={toggle(side === "under")} onClick={() => setSide("under")}>
                Under (menos que)
              </button>
            </div>
          </div>
        </div>

        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium">Entrada por</span>
            <button type="button" className={toggle(mode === "prob")} onClick={() => setMode("prob")}>
              Probabilidade
            </button>
            <button type="button" className={toggle(mode === "odd")} onClick={() => setMode("odd")}>
              Odd
            </button>
          </div>

          {mode === "prob" ? (
            <div className="space-y-1">
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Probabilidade-alvo</span>
                <span className="font-medium tabular-nums">{targetProb}%</span>
              </div>
              <input
                type="range"
                min={1}
                max={99}
                step={1}
                value={targetProb}
                onChange={(event) => setTargetProb(Number(event.target.value))}
                className="w-full accent-primary"
              />
            </div>
          ) : (
            <div className="flex items-center gap-3">
              <label htmlFor="explorer-odd" className="text-sm text-muted-foreground">
                Odd da casa
              </label>
              <Input
                id="explorer-odd"
                type="number"
                step="0.01"
                min="1.01"
                value={oddInput}
                onChange={(event) => setOddInput(event.target.value)}
                className="w-28"
              />
              <span className="text-sm text-muted-foreground">
                {Number.isFinite(target) ? `≈ ${target.toFixed(1)}% implícito` : "odd inválida"}
              </span>
            </div>
          )}
        </div>

        {best ? (
          <div className="rounded-md bg-muted p-4">
            <div className="text-sm text-muted-foreground">Linha mais próxima do alvo</div>
            <div className="mt-1 text-2xl font-semibold">
              {side === "over" ? "Over" : "Under"} {best.line}
            </div>
            <div className="mt-1 text-sm">
              Probabilidade real <span className="font-medium tabular-nums">{bestProb.toFixed(1)}%</span> · odd justa{" "}
              <span className="font-medium tabular-nums">{bestOdd.toFixed(2)}</span>
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              Alvo {Number.isFinite(target) ? `${target.toFixed(1)}%` : "—"}; as linhas são discretas (.5), então a mais
              próxima entrega {bestProb.toFixed(1)}%.
            </div>
          </div>
        ) : (
          <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
            Informe uma odd válida (maior que 1,00) para ver a linha correspondente.
          </div>
        )}
      </CardContent>
    </Card>
  );
}

type ValueSelection = { group: string; label: string; prob: number };

// Espelha api/value_betting.py: p limitado a [0.001, 0.999], EV = p*odd - 1 (>0 = valor),
// odd justa = 1/p, prob implicita = 1/odd, de-vig de 2 vias opcional.
function clampProb(p: number): number {
  return Math.min(0.999, Math.max(0.001, p));
}

// Reune TODAS as selecoes apostaveis com a prob do modelo: resultado, gols, BTTS e
// cada linha O/U dos mercados de contagem (usando a grade autoritativa do backend).
function buildValueSelections(result: PredictionResponse, home: string, away: string): ValueSelection[] {
  const out: ValueSelection[] = [];
  for (const [label, prob] of Object.entries(result.vencedor.probabilidades)) {
    out.push({ group: "Resultado", label, prob });
  }
  out.push({ group: "Gols", label: "Over 2.5", prob: result.over_2_5.prob_sim });
  out.push({ group: "Gols", label: "Under 2.5", prob: 100 - result.over_2_5.prob_sim });
  out.push({ group: "Ambas marcam", label: "Sim", prob: result.ambas_marcam.prob_sim });
  out.push({ group: "Ambas marcam", label: "Nao", prob: 100 - result.ambas_marcam.prob_sim });

  const countMarkets: { group: string; market: CountPrediction }[] = [
    { group: "Finalizacoes — total", market: result.chutes },
    { group: `Escanteios — ${home}`, market: result.escanteios[home] },
    { group: `Escanteios — ${away}`, market: result.escanteios[away] },
    { group: "Escanteios — total", market: result.escanteios.total },
    { group: `Cartoes — ${home}`, market: result.cartoes[home] },
    { group: `Cartoes — ${away}`, market: result.cartoes[away] },
    { group: "Cartoes — total", market: result.cartoes.total },
  ];
  for (const { group, market } of countMarkets) {
    if (!market?.linhas) continue;
    const linhas = Object.entries(market.linhas).sort((a, b) => Number(a[0]) - Number(b[0]));
    for (const [linha, lado] of linhas) {
      out.push({ group, label: `Over ${linha}`, prob: lado.over.prob });
      out.push({ group, label: `Under ${linha}`, prob: lado.under.prob });
    }
  }
  return out;
}

function ValueBetting({ result, home, away }: { result: PredictionResponse; home: string; away: string }) {
  const selections = useMemo(() => buildValueSelections(result, home, away), [result, home, away]);
  const [index, setIndex] = useState(0);
  const [houseOdd, setHouseOdd] = useState("");
  const [oppositeOdd, setOppositeOdd] = useState("");

  const groups = useMemo(() => {
    const seen: string[] = [];
    for (const sel of selections) if (!seen.includes(sel.group)) seen.push(sel.group);
    return seen;
  }, [selections]);

  const selected = selections[index] ?? selections[0];
  const odd = Number(houseOdd);
  const oppOdd = Number(oppositeOdd);
  const oddValid = Number.isFinite(odd) && odd > 1;

  const verdict = useMemo(() => {
    if (!selected || !oddValid) return null;
    const p = clampProb(selected.prob / 100);
    const implied = 1 / odd;
    const edge = p * odd - 1;
    let fairMarket = implied;
    if (Number.isFinite(oppOdd) && oppOdd > 1) {
      const ia = 1 / odd;
      const ib = 1 / oppOdd;
      fairMarket = ia / (ia + ib);
    }
    return {
      probModelo: p * 100,
      oddJustaModelo: 1 / p,
      implied: implied * 100,
      fairMarket: fairMarket * 100,
      hasDevig: Number.isFinite(oppOdd) && oppOdd > 1,
      edgePct: edge * 100,
      valor: edge > 0,
    };
  }, [selected, odd, oppOdd, oddValid]);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Value betting</CardTitle>
        <CardDescription>
          Compara a probabilidade do modelo com a odd da casa. EV positivo = a casa paga acima do risco real.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <label htmlFor="value-selection" className="text-sm font-medium">
              Aposta
            </label>
            <select
              id="value-selection"
              value={index}
              onChange={(event) => setIndex(Number(event.target.value))}
              className="h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            >
              {groups.map((group) => (
                <optgroup label={group} key={group}>
                  {selections.map((sel, idx) =>
                    sel.group === group ? (
                      <option value={idx} key={idx}>
                        {sel.label} ({sel.prob.toFixed(1)}%)
                      </option>
                    ) : null,
                  )}
                </optgroup>
              ))}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <label htmlFor="value-odd" className="text-sm font-medium">
                Odd da casa
              </label>
              <Input
                id="value-odd"
                type="number"
                step="0.01"
                min="1.01"
                placeholder="ex.: 2.10"
                value={houseOdd}
                onChange={(event) => setHouseOdd(event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <label htmlFor="value-odd-opp" className="text-sm font-medium">
                Odd oposta <span className="font-normal text-muted-foreground">(opcional)</span>
              </label>
              <Input
                id="value-odd-opp"
                type="number"
                step="0.01"
                min="1.01"
                placeholder="de-vig"
                value={oppositeOdd}
                onChange={(event) => setOppositeOdd(event.target.value)}
              />
            </div>
          </div>
        </div>

        {verdict ? (
          <div
            className={`rounded-md border p-4 ${
              verdict.valor ? "border-emerald-200 bg-emerald-50" : "border-muted bg-muted"
            }`}
          >
            <div className="flex items-center justify-between gap-3">
              <div className="text-sm text-muted-foreground">Veredito</div>
              <Badge
                variant="outline"
                className={
                  verdict.valor
                    ? "border-emerald-300 bg-emerald-100 text-emerald-800"
                    : "border-red-200 bg-red-50 text-red-800"
                }
              >
                {verdict.valor ? "Valor (EV+)" : "Sem valor"}
              </Badge>
            </div>
            <div className="mt-1 text-2xl font-semibold tabular-nums">
              EV {verdict.edgePct >= 0 ? "+" : ""}
              {verdict.edgePct.toFixed(1)}%
            </div>
            <div className="mt-2 grid gap-1 text-sm sm:grid-cols-2">
              <div>
                Prob. modelo: <span className="font-medium tabular-nums">{verdict.probModelo.toFixed(1)}%</span>
              </div>
              <div>
                Odd justa (modelo): <span className="font-medium tabular-nums">{verdict.oddJustaModelo.toFixed(2)}</span>
              </div>
              <div>
                Prob. implícita da casa: <span className="font-medium tabular-nums">{verdict.implied.toFixed(1)}%</span>
              </div>
              {verdict.hasDevig ? (
                <div>
                  Prob. justa sem margem:{" "}
                  <span className="font-medium tabular-nums">{verdict.fairMarket.toFixed(1)}%</span>
                </div>
              ) : null}
            </div>
            <p className="mt-3 text-xs text-muted-foreground">
              Value baseado na calibração do modelo, não em histórico de mercado (odds só disponíveis 1–14 dias antes; 7
              dias de histórico). Nenhuma aposta é garantia.
            </p>
          </div>
        ) : (
          <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
            Informe a odd da casa (maior que 1,00) para avaliar o valor da aposta.
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// Combinada do MESMO jogo. A probabilidade combinada e o produto das pernas (assume
// independencia) — exibida como "teto otimista" porque pernas do mesmo jogo sao
// correlacionadas, entao a probabilidade real costuma diferir do produto ingenuo.
function ParlayBuilder({ result, home, away }: { result: PredictionResponse; home: string; away: string }) {
  const selections = useMemo(() => buildValueSelections(result, home, away), [result, home, away]);
  const groups = useMemo(() => {
    const seen: string[] = [];
    for (const sel of selections) if (!seen.includes(sel.group)) seen.push(sel.group);
    return seen;
  }, [selections]);
  const [picked, setPicked] = useState<number[]>([]);

  const toggle = (idx: number) =>
    setPicked((current) => (current.includes(idx) ? current.filter((value) => value !== idx) : [...current, idx]));

  const legs = picked.map((idx) => selections[idx]).filter(Boolean);
  const combinedProb = legs.length
    ? legs.reduce((acc, leg) => acc * clampProb(leg.prob / 100), 1) * 100
    : null;
  const combinedOdd = combinedProb ? 100 / combinedProb : null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Combinada (mesmo jogo)</CardTitle>
        <CardDescription>
          Selecione duas ou mais apostas deste jogo. A probabilidade combinada é um teto otimista (ver ressalva).
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="max-h-64 space-y-3 overflow-y-auto rounded-md border p-3">
          {groups.map((group) => (
            <div key={group} className="space-y-1">
              <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{group}</div>
              <div className="grid gap-1 sm:grid-cols-2">
                {selections.map((sel, idx) =>
                  sel.group === group ? (
                    <label key={idx} className="flex items-center gap-2 text-sm">
                      <input type="checkbox" checked={picked.includes(idx)} onChange={() => toggle(idx)} />
                      <span>
                        {sel.label} <span className="text-muted-foreground tabular-nums">({sel.prob.toFixed(1)}%)</span>
                      </span>
                    </label>
                  ) : null,
                )}
              </div>
            </div>
          ))}
        </div>

        {legs.length >= 2 && combinedProb !== null && combinedOdd !== null ? (
          <div className="rounded-md bg-muted p-4">
            <div className="text-sm text-muted-foreground">
              {legs.length} pernas · {legs.map((leg) => leg.label).join(" + ")}
            </div>
            <div className="mt-1 flex flex-wrap items-baseline gap-x-6 gap-y-1">
              <div>
                <span className="text-sm text-muted-foreground">Prob. combinada (teto): </span>
                <span className="text-2xl font-semibold tabular-nums">{combinedProb.toFixed(1)}%</span>
              </div>
              <div>
                <span className="text-sm text-muted-foreground">Odd justa combinada: </span>
                <span className="text-2xl font-semibold tabular-nums">{combinedOdd.toFixed(2)}</span>
              </div>
            </div>
            <p className="mt-3 text-xs text-amber-700">
              Teto otimista: assume independência entre as pernas. Apostas do mesmo jogo são correlacionadas (ex.: mando
              que infla escanteios também tende a vencer), então a probabilidade real costuma ser menor — trate como
              limite superior, não como valor garantido.
            </p>
          </div>
        ) : (
          <div className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">
            Marque pelo menos duas apostas para ver a probabilidade e a odd combinadas.
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ResultView({ result, home, away }: { result: PredictionResponse; home: string; away: string }) {
  const probabilities = result.vencedor.probabilidades;
  const total = Object.values(probabilities).reduce((acc, value) => acc + value, 0) || 1;
  const reliability = matchupReliability(parseInt(result.confronto_direto, 10) || 0);

  const explorerMarkets: ExplorerMarket[] = [
    { key: "chutes", label: "Finalizacoes — total", market: result.chutes },
    { key: "esc-home", label: `Escanteios — ${home}`, market: result.escanteios[home] },
    { key: "esc-away", label: `Escanteios — ${away}`, market: result.escanteios[away] },
    { key: "esc-total", label: "Escanteios — total", market: result.escanteios.total },
    { key: "card-home", label: `Cartoes — ${home}`, market: result.cartoes[home] },
    { key: "card-away", label: `Cartoes — ${away}`, market: result.cartoes[away] },
    { key: "card-total", label: "Cartoes — total", market: result.cartoes.total },
  ].filter((item) => item.market && Array.isArray(item.market.distribuicao) && item.market.distribuicao.length > 0);

  return (
    <section className="space-y-5">
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle>Resultado provavel: {result.vencedor.vencedor}</CardTitle>
              <CardDescription>Confianca do cenario principal: {result.vencedor.confianca}%</CardDescription>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted-foreground">Confiabilidade do confronto</span>
              <Badge variant="outline" className={reliability.cls}>
                {reliability.label}
              </Badge>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex h-4 overflow-hidden rounded-md bg-muted">
            {Object.entries(probabilities).map(([label, value], index) => (
              <div
                key={label}
                className={index === 0 ? "bg-primary" : index === 1 ? "bg-chart-2" : "bg-chart-3"}
                style={{ width: `${(value / total) * 100}%` }}
                title={`${label}: ${value}%`}
              />
            ))}
          </div>
          <div className="grid gap-3 md:grid-cols-3">
            {Object.entries(probabilities).map(([label, value]) => (
              <div key={label} className="rounded-lg border p-3">
                <div className="text-sm text-muted-foreground">{label}</div>
                <div className="text-2xl font-semibold">{value}%</div>
                <OddsText market={result.odds.vencedor[label]} />
              </div>
            ))}
          </div>
          <p className="text-sm text-muted-foreground">{reliability.note}</p>
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <NumericCard title="Total de gols" metric={result.gols} line={result.odds.linhas_numericas.gols} />
        <CountCard title="Total de finalizacoes" market={result.chutes} />
      </div>

      <MarketSection title="Escanteios" markets={result.escanteios} home={home} away={away} />
      <MarketSection title="Cartoes" markets={result.cartoes} home={home} away={away} />

      {explorerMarkets.length ? <LineExplorer key={`${home}-${away}`} markets={explorerMarkets} /> : null}

      <ValueBetting key={`vb-${home}-${away}`} result={result} home={home} away={away} />

      <ParlayBuilder key={`parlay-${home}-${away}`} result={result} home={home} away={away} />

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Ambas marcam</CardTitle>
            <CardDescription>Probabilidade de sim: {result.ambas_marcam.prob_sim}%</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="text-2xl font-semibold">{result.ambas_marcam.resposta}</div>
            <div>Sim: <OddsText market={result.odds.ambas_marcam.sim} /></div>
            <div>Nao: <OddsText market={result.odds.ambas_marcam.nao} /></div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Over/under 2,5 gols</CardTitle>
            <CardDescription>Probabilidade de over: {result.over_2_5.prob_sim}%</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="text-2xl font-semibold">{result.over_2_5.resposta}</div>
            <div>Over: <OddsText market={result.odds.over_under_2_5.sim} /></div>
            <div>Under: <OddsText market={result.odds.over_under_2_5.nao} /></div>
          </CardContent>
        </Card>
      </div>

      <div className="space-y-2 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
        <div className="flex items-center gap-2 font-medium">
          <AlertCircle className="h-4 w-4" />
          Avisos de risco
        </div>
        <ul className="list-disc space-y-1 pl-5">
          <li>Finalizacoes, escanteios e cartoes usam uma base de treino menor (grandes torneios), entao tendem a ter menor confianca que o resultado.</li>
          <li>Odd justa = 1/probabilidade, sem margem da casa: serve para comparar com a odd oferecida, nao como recomendacao de aposta.</li>
          <li>Combinadas do mesmo jogo sao correlacionadas — a probabilidade combinada e um teto otimista, nao um valor garantido.</li>
          <li>Existe um teto real de previsibilidade do futebol. Nenhuma previsao garante resultado; aposte com responsabilidade.</li>
        </ul>
      </div>
    </section>
  );
}

function AnomalyAlerts({ anomalies, team }: { anomalies: Anomaly[]; team: string }) {
  if (!anomalies || anomalies.length === 0) return null;
  return (
    <div className="space-y-2 mt-4">
      <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Alertas de Destaque — {team}
      </div>
      <div className="grid gap-2">
        {anomalies.map((anom, idx) => {
          const isAlert = anom.type === "alert";
          return (
            <div
              key={idx}
              className={`flex items-start gap-3 rounded-lg border p-3 text-xs leading-relaxed ${
                isAlert
                  ? "border-amber-200 bg-amber-50 text-amber-900"
                  : "border-emerald-200 bg-emerald-50 text-emerald-950"
              }`}
            >
              {isAlert ? (
                <AlertTriangle className="h-4 w-4 shrink-0 text-amber-600" />
              ) : (
                <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" />
              )}
              <div>{anom.message}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function RecentMatchesList({ matches, team }: { matches: RecentMatch[]; team: string }) {
  if (!matches || matches.length === 0) return null;
  return (
    <div className="space-y-2 mt-4">
      <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Últimos 5 Jogos Brutos — {team}
      </div>
      <div className="overflow-hidden rounded-md border text-xs">
        <table className="w-full border-collapse text-left">
          <thead>
            <tr className="border-b bg-muted/60 text-[10px] font-semibold uppercase text-muted-foreground">
              <th className="px-3 py-1.5">Data</th>
              <th className="px-3 py-1.5">Confronto</th>
              <th className="px-3 py-1.5 text-center">Placar</th>
              <th className="px-3 py-1.5 text-right">Chutes</th>
              <th className="px-3 py-1.5 text-right">Cantos</th>
              <th className="px-3 py-1.5 text-right">Cards</th>
            </tr>
          </thead>
          <tbody>
            {matches.map((m, idx) => {
              const score = `${m.goals_scored}x${m.goals_conceded}`;
              const vsText = m.is_home ? `vs ${m.opponent}` : `@ ${m.opponent}`;
              return (
                <tr key={idx} className="border-b last:border-0 hover:bg-muted/30">
                  <td className="px-3 py-2 text-muted-foreground tabular-nums">{m.date}</td>
                  <td className="px-3 py-2 font-medium">{vsText}</td>
                  <td className="px-3 py-2 text-center tabular-nums font-semibold">{score}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{m.sb_shots_on_target.toFixed(0)}/{m.sb_shots.toFixed(0)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{m.sb_corners.toFixed(0)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{m.sb_cards.toFixed(0)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function Home() {
  const [apiStatus, setApiStatus] = useState<"checking" | "ok" | "error">("checking");
  const [apiError, setApiError] = useState<string | null>(null);
  const [teams, setTeams] = useState<string[]>([]);
  const [tournaments, setTournaments] = useState<string[]>([]);
  const [home, setHome] = useState("Brazil");
  const [away, setAway] = useState("Argentina");
  const [tournament, setTournament] = useState("Copa do Mundo");
  const [neutral, setNeutral] = useState(true);
  const [homeSnapshot, setHomeSnapshot] = useState<TeamResponse | null>(null);
  const [awaySnapshot, setAwaySnapshot] = useState<TeamResponse | null>(null);
  const [homeValues, setHomeValues] = useState<EditableValues>({});
  const [awayValues, setAwayValues] = useState<EditableValues>({});
  const [h2h, setH2h] = useState<H2HResponse | null>(null);
  const [h2hGd, setH2hGd] = useState<string>("");
  const [loadingPrediction, setLoadingPrediction] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<PredictionResponse | null>(null);

  // Novas variáveis de estado da infraestrutura de UX/UI
  const [lastSuccessfulRun, setLastSuccessfulRun] = useState<string | null>(null);
  const [homeRecent, setHomeRecent] = useState<RecentMatch[]>([]);
  const [awayRecent, setAwayRecent] = useState<RecentMatch[]>([]);
  const [homeAnomalies, setHomeAnomalies] = useState<Anomaly[]>([]);
  const [awayAnomalies, setAwayAnomalies] = useState<Anomaly[]>([]);

  useEffect(() => {
    let mounted = true;
    api
      .health()
      .then(() => api.teams())
      .then((data) => {
        if (!mounted) return;
        setTeams(data.teams);
        setTournaments(data.tournaments);
        setApiStatus("ok");
        setApiError(null);
      })
      .catch((err: Error) => {
        if (!mounted) return;
        setApiStatus("error");
        setApiError(err.message || "A API pode estar acordando no Railway. Tente novamente em alguns segundos.");
      });

    api.systemStatus()
      .then((res) => {
        if (mounted) setLastSuccessfulRun(res.last_successful_run);
      })
      .catch((err) => console.error("Error fetching system status", err));

    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (!home || !teams.includes(home)) return;
    api.team(home).then((snapshot) => {
      setHomeSnapshot(snapshot);
      setHomeValues(asEditable(snapshot.defaults, PRIMARY_FIELDS));
    }).catch((err: Error) => setError(err.message));

    // Carregar histórico recente e anomalias do Mandante
    api.recentMatches(home)
      .then((res) => setHomeRecent(res.matches))
      .catch((err) => console.error("Error fetching home recent matches", err));
    api.teamAnomalies(home)
      .then((res) => setHomeAnomalies(res.anomalies))
      .catch((err) => console.error("Error fetching home anomalies", err));
  }, [home, teams]);

  useEffect(() => {
    if (!away || !teams.includes(away)) return;
    api.team(away).then((snapshot) => {
      setAwaySnapshot(snapshot);
      setAwayValues(asEditable(snapshot.defaults, PRIMARY_FIELDS));
    }).catch((err: Error) => setError(err.message));

    // Carregar histórico recente e anomalias do Visitante
    api.recentMatches(away)
      .then((res) => setAwayRecent(res.matches))
      .catch((err) => console.error("Error fetching away recent matches", err));
    api.teamAnomalies(away)
      .then((res) => setAwayAnomalies(res.anomalies))
      .catch((err) => console.error("Error fetching away anomalies", err));
  }, [away, teams]);

  useEffect(() => {
    if (!home || !away || home === away || !teams.includes(home) || !teams.includes(away)) {
      setH2h(null);
      setH2hGd("");
      return;
    }
    api
      .h2h(home, away)
      .then((data) => {
        setH2h(data);
        const auto = data.metrics?.h2h_home_gd_mean;
        setH2hGd(typeof auto === "number" && Number.isFinite(auto) ? String(auto) : "");
      })
      .catch(() => {
        setH2h(null);
        setH2hGd("");
      });
  }, [home, away, teams]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setResult(null);
    if (home === away) {
      setError("Escolha duas selecoes diferentes.");
      return;
    }
    if (!teams.includes(home) || !teams.includes(away)) {
      setError("Escolha selecoes da lista.");
      return;
    }
    setLoadingPrediction(true);
    try {
      const h2hAuto =
        typeof h2h?.metrics?.h2h_home_gd_mean === "number" ? (h2h.metrics.h2h_home_gd_mean as number) : undefined;
      const h2hOverrides: Record<string, number> = {};
      if (h2hGd.trim() !== "") {
        const value = Number(h2hGd);
        const step = FEATURE_RANGES.h2h_home_gd_mean.step;
        if (Number.isFinite(value) && (h2hAuto === undefined || Math.abs(value - h2hAuto) > step / 2)) {
          h2hOverrides.h2h_home_gd_mean = value;
        }
      }
      const prediction = await api.predict({
        home_team: home,
        away_team: away,
        neutral,
        tournament,
        home_vals: changedValues(homeValues, homeSnapshot?.defaults || {}),
        away_vals: changedValues(awayValues, awaySnapshot?.defaults || {}),
        h2h_overrides: h2hOverrides,
      });
      setResult(prediction);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Nao foi possivel gerar a previsao.");
    } finally {
      setLoadingPrediction(false);
    }
  }

  return (
    <main className="min-h-screen">
      <header className="border-b bg-card">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-5 lg:px-6">
          <div className="flex flex-col justify-between gap-3 md:flex-row md:items-center">
            <div>
              <h1 className="text-2xl font-semibold">Previsao de partidas de selecoes</h1>
              <p className="text-sm text-muted-foreground">Modelos scikit-learn com API Python no Railway e front Next.js na Vercel.</p>
              {lastSuccessfulRun ? (
                <p className="text-xs text-muted-foreground mt-1">
                  Última atualização dos dados: {lastSuccessfulRun}
                </p>
              ) : null}
            </div>
            <ApiStatus status={apiStatus} error={apiError} />
          </div>
        </div>
      </header>

      <form onSubmit={handleSubmit} className="mx-auto grid max-w-7xl gap-6 px-4 py-6 lg:px-6">
        <section className="grid gap-4 rounded-lg border bg-card p-5 shadow md:grid-cols-4">
          <TeamSelect id="home-team" label="Mandante" value={home} teams={teams} onChange={setHome} />
          <TeamSelect id="away-team" label="Visitante" value={away} teams={teams} onChange={setAway} />
          <div className="space-y-2">
            <label htmlFor="tournament" className="text-sm font-medium">
              Competicao
            </label>
            <select
              id="tournament"
              value={tournament}
              onChange={(event) => setTournament(event.target.value)}
              className="h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            >
              {tournaments.map((item) => (
                <option value={item} key={item}>
                  {item}
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-end">
            <label className="flex h-9 w-full items-center gap-3 rounded-md border px-3 text-sm">
              <input type="checkbox" checked={neutral} onChange={(event) => setNeutral(event.target.checked)} />
              Campo neutro
            </label>
          </div>
        </section>

        {h2h ? (
          <div className="space-y-3 rounded-lg border bg-card p-4 shadow">
            <div className="flex items-start gap-3 text-sm">
              <TrendingUp className="mt-0.5 h-4 w-4 text-primary" />
              <div>
                <div className="font-medium">Confronto direto</div>
                <div className="text-muted-foreground">{h2h.summary}</div>
              </div>
            </div>
            {typeof h2h.metrics?.h2h_home_gd_mean === "number" ? (
              <div className="sm:max-w-md">
                <FeatureSlider
                  id="h2h-gd"
                  label={`Saldo medio do mandante no H2H (${home})`}
                  value={h2hGd}
                  automatic={h2h.metrics.h2h_home_gd_mean as number}
                  range={FEATURE_RANGES.h2h_home_gd_mean}
                  onChange={setH2hGd}
                  onReset={() => setH2hGd(String(h2h.metrics.h2h_home_gd_mean))}
                />
              </div>
            ) : null}
          </div>
        ) : null}

        <div className="grid gap-6 xl:grid-cols-2">
          <div className="rounded-lg border bg-card p-5 shadow space-y-4">
            <TeamFields
              title={home}
              snapshot={homeSnapshot}
              values={homeValues}
              onChange={(field, value) => setHomeValues((current) => ({ ...current, [field]: value }))}
              onReset={(field) => setHomeValues((current) => ({ ...current, [field]: formatDefault(homeSnapshot?.defaults[field]) }))}
            />
            <AnomalyAlerts anomalies={homeAnomalies} team={home} />
            <RecentMatchesList matches={homeRecent} team={home} />
          </div>
          <div className="rounded-lg border bg-card p-5 shadow space-y-4">
            <TeamFields
              title={away}
              snapshot={awaySnapshot}
              values={awayValues}
              onChange={(field, value) => setAwayValues((current) => ({ ...current, [field]: value }))}
              onReset={(field) => setAwayValues((current) => ({ ...current, [field]: formatDefault(awaySnapshot?.defaults[field]) }))}
            />
            <AnomalyAlerts anomalies={awayAnomalies} team={away} />
            <RecentMatchesList matches={awayRecent} team={away} />
          </div>
        </div>

        {error ? (
          <div className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-900">
            <AlertCircle className="mt-0.5 h-4 w-4" />
            <span>{error}</span>
          </div>
        ) : null}

        <div className="flex flex-wrap gap-3">
          <Button type="submit" disabled={loadingPrediction || apiStatus !== "ok"}>
            {loadingPrediction ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            Gerar previsao
          </Button>
          <Button type="button" variant="outline" onClick={() => window.location.reload()}>
            <RefreshCcw className="h-4 w-4" />
            Recarregar API
          </Button>
        </div>
      </form>

      {result ? (
        <div className="mx-auto max-w-7xl px-4 pb-10 lg:px-6">
          <ResultView result={result} home={home} away={away} />
        </div>
      ) : null}
    </main>
  );
}
