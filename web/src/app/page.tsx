"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { AlertCircle, Loader2, RefreshCcw, RotateCcw, Server, TrendingUp } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api, H2HResponse, NumericLineMarket, NumericPrediction, OddsMarket, PredictionResponse, TeamResponse } from "@/lib/api";

const PRIMARY_FIELDS = [
  "elo_pre",
  "gf_l5",
  "ga_l5",
  "gd_l5",
  "ppg_l5",
  "winrate_l5",
  "win_streak",
  "unbeaten_streak",
  "days_rest",
  "sb_shots_l5",
  "sb_shots_on_target_l5",
  "sb_corners_l5",
  "sb_cards_l5",
  "sb_possession_l5",
];

const LABELS: Record<string, string> = {
  elo_pre: "Rating Elo atual",
  gf_l5: "Gols feitos ult. 5",
  ga_l5: "Gols sofridos ult. 5",
  gd_l5: "Saldo de gols ult. 5",
  ppg_l5: "Pontos por jogo ult. 5",
  winrate_l5: "Taxa de vitoria ult. 5",
  win_streak: "Sequencia de vitorias",
  unbeaten_streak: "Sequencia invicto",
  days_rest: "Dias de descanso",
  sb_shots_l5: "Finalizacoes/jogo ult. 5",
  sb_shots_on_target_l5: "Chutes ao gol/jogo ult. 5",
  sb_corners_l5: "Escanteios/jogo ult. 5",
  sb_cards_l5: "Cartoes/jogo ult. 5",
  sb_possession_l5: "Posse de bola % ult. 5",
};

type EditableValues = Record<string, string>;

function formatDefault(value: number | undefined) {
  return value === undefined || value === null || Number.isNaN(Number(value)) ? "" : Number(value).toFixed(2);
}

function asEditable(defaults: Record<string, number>, fields: string[]) {
  return Object.fromEntries(fields.map((field) => [field, formatDefault(defaults[field])]));
}

function changedValues(values: EditableValues, defaults: Record<string, number>) {
  const output: Record<string, number> = {};
  for (const [key, value] of Object.entries(values)) {
    if (value.trim() === "") continue;
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) continue;
    const original = defaults[key];
    if (original === undefined || value !== formatDefault(original)) {
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
  const fields = useMemo(() => PRIMARY_FIELDS.filter((field) => snapshot?.bases.includes(field)), [snapshot]);

  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-base font-semibold">{title}</h2>
        <p className="text-sm text-muted-foreground">Campos vazios ou sem alteracao usam o valor automatico da API.</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        {fields.map((field) => {
          const automatic = snapshot?.defaults[field];
          const edited = values[field] !== undefined && automatic !== undefined && values[field] !== formatDefault(automatic);
          return (
            <div key={field} className="rounded-lg border bg-card p-3">
              <div className="mb-2 flex items-start justify-between gap-2">
                <label htmlFor={`${title}-${field}`} className="text-sm font-medium leading-5">
                  {LABELS[field] || field}
                </label>
                <Badge variant="outline" className={edited ? "border-primary text-primary" : "text-muted-foreground"}>
                  {edited ? "editado" : "automatico"}
                </Badge>
              </div>
              <div className="flex gap-2">
                <Input
                  id={`${title}-${field}`}
                  type="number"
                  step="0.01"
                  value={values[field] ?? ""}
                  placeholder={automatic === undefined ? "sem valor" : String(automatic)}
                  onChange={(event) => onChange(field, event.target.value)}
                />
                <Button type="button" variant="outline" size="icon" title="Restaurar valor automatico" onClick={() => onReset(field)}>
                  <RotateCcw className="h-4 w-4" />
                </Button>
              </div>
            </div>
          );
        })}
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

function ResultView({ result, home, away }: { result: PredictionResponse; home: string; away: string }) {
  const probabilities = result.vencedor.probabilidades;
  const total = Object.values(probabilities).reduce((acc, value) => acc + value, 0) || 1;
  const homeCorners = result.escanteios[home];
  const awayCorners = result.escanteios[away];

  return (
    <section className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle>Resultado provavel: {result.vencedor.vencedor}</CardTitle>
          <CardDescription>Confianca do cenario principal: {result.vencedor.confianca}%</CardDescription>
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
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <NumericCard title="Total de gols" metric={result.gols} line={result.odds.linhas_numericas.gols} />
        <NumericCard title="Total de finalizacoes" metric={result.chutes} line={result.odds.linhas_numericas.chutes} />
        <NumericCard title={`Escanteios ${home}`} metric={homeCorners} line={result.odds.linhas_numericas.escanteios[home]} />
        <NumericCard title={`Escanteios ${away}`} metric={awayCorners} line={result.odds.linhas_numericas.escanteios[away]} />
      </div>

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

      <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
        Finalizacoes e escanteios usam uma base menor de treino, restrita a grandes torneios, e por isso tendem a ter menor confianca.
      </div>
      <div className="rounded-lg border bg-card p-4 text-sm text-muted-foreground">
        Odd justa = 1/probabilidade, sem margem da casa. Ela serve para comparar com odds oferecidas, nao como recomendacao de aposta. Nenhuma previsao garante resultado.
      </div>
    </section>
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
  const [loadingPrediction, setLoadingPrediction] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<PredictionResponse | null>(null);

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
  }, [home, teams]);

  useEffect(() => {
    if (!away || !teams.includes(away)) return;
    api.team(away).then((snapshot) => {
      setAwaySnapshot(snapshot);
      setAwayValues(asEditable(snapshot.defaults, PRIMARY_FIELDS));
    }).catch((err: Error) => setError(err.message));
  }, [away, teams]);

  useEffect(() => {
    if (!home || !away || home === away || !teams.includes(home) || !teams.includes(away)) {
      setH2h(null);
      return;
    }
    api.h2h(home, away).then(setH2h).catch(() => setH2h(null));
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
      const prediction = await api.predict({
        home_team: home,
        away_team: away,
        neutral,
        tournament,
        home_vals: changedValues(homeValues, homeSnapshot?.defaults || {}),
        away_vals: changedValues(awayValues, awaySnapshot?.defaults || {}),
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
          <div className="flex items-start gap-3 rounded-lg border bg-card p-4 text-sm shadow">
            <TrendingUp className="mt-0.5 h-4 w-4 text-primary" />
            <div>
              <div className="font-medium">Confronto direto</div>
              <div className="text-muted-foreground">{h2h.summary}</div>
            </div>
          </div>
        ) : null}

        <div className="grid gap-6 xl:grid-cols-2">
          <TeamFields
            title={home}
            snapshot={homeSnapshot}
            values={homeValues}
            onChange={(field, value) => setHomeValues((current) => ({ ...current, [field]: value }))}
            onReset={(field) => setHomeValues((current) => ({ ...current, [field]: formatDefault(homeSnapshot?.defaults[field]) }))}
          />
          <TeamFields
            title={away}
            snapshot={awaySnapshot}
            values={awayValues}
            onChange={(field, value) => setAwayValues((current) => ({ ...current, [field]: value }))}
            onReset={(field) => setAwayValues((current) => ({ ...current, [field]: formatDefault(awaySnapshot?.defaults[field]) }))}
          />
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
