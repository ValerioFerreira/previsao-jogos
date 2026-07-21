"use client";
import React, { createContext, useContext, useState, useEffect, ReactNode } from "react";
import type { AnalysisResponse } from "@/lib/monetizationApi";

type PredictionContextType = {
  homeTeamId: string;
  setHomeTeamId: (id: string) => void;
  awayTeamId: string;
  setAwayTeamId: (id: string) => void;
  competition: string;
  setCompetition: (comp: string) => void;
  neutralField: boolean;
  setNeutralField: (neutral: boolean) => void;
  scope: "selecao" | "clube";
  setScope: (s: "selecao" | "clube") => void;

  // --- estado da análise atual (persiste ao navegar entre páginas e voltar) ---
  analysis: AnalysisResponse | null;
  setAnalysis: (a: AnalysisResponse | null) => void;
  h2hData: any;
  setH2hData: (d: any) => void;
  mode: "independente" | "futura";
  setMode: (m: "independente" | "futura") => void;
  fixtureId: number | null;
  setFixtureId: (f: number | null) => void;
  matchDate: string | undefined;
  setMatchDate: (d: string | undefined) => void;
};

const PredictionContext = createContext<PredictionContextType | undefined>(undefined);

// Persistência em localStorage: garante que a análise (e a configuração do confronto)
// sobreviva a um reload cheio da página — não só à navegação client-side do Next. Sem
// isso, um F5 ou uma navegação que remontasse o provider zerava a análise, forçando o
// usuário a gastar outro crédito.
const LS_KEY = "apostai:prediction:v1";

type Persisted = {
  homeTeamId: string; awayTeamId: string; competition: string; neutralField: boolean;
  analysis: AnalysisResponse | null; mode: "independente" | "futura";
  fixtureId: number | null; matchDate: string | undefined;
  scope: "selecao" | "clube";
};

function loadPersisted(): Partial<Persisted> {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(LS_KEY);
    return raw ? (JSON.parse(raw) as Partial<Persisted>) : {};
  } catch {
    return {};
  }
}

export function PredictionProvider({ children }: { children: ReactNode }) {
  // Init sempre com os defaults (iguais ao SSR) para não divergir na hidratação.
  // Os valores persistidos são aplicados depois do mount (useEffect abaixo).
  const [homeTeamId, setHomeTeamId] = useState("");
  const [awayTeamId, setAwayTeamId] = useState("");
  const [competition, setCompetition] = useState("Copa do Mundo");
  const [neutralField, setNeutralField] = useState(false);
  const [scope, setScope] = useState<"selecao" | "clube">("selecao");

  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [h2hData, setH2hData] = useState<any>(null);
  const [mode, setMode] = useState<"independente" | "futura">("futura");
  const [fixtureId, setFixtureId] = useState<number | null>(null);
  const [matchDate, setMatchDate] = useState<string | undefined>(undefined);

  // Só passa a persistir depois que a carga inicial (efeito abaixo) rodar —
  // sem isso, o efeito de gravação dispara no mount com os defaults e
  // sobrescreve o localStorage antes da leitura acontecer.
  const hydratedRef = React.useRef(false);

  // Aplica o localStorage só depois do mount — no SSR/primeira pintura do
  // cliente o estado é sempre o default acima, evitando hydration mismatch
  // (React error #418) quando a análise salva diverge dos defaults.
  useEffect(() => {
    const init = loadPersisted();
    if (init.homeTeamId !== undefined) setHomeTeamId(init.homeTeamId);
    if (init.awayTeamId !== undefined) setAwayTeamId(init.awayTeamId);
    if (init.competition !== undefined) setCompetition(init.competition);
    if (init.neutralField !== undefined) setNeutralField(init.neutralField);
    if (init.scope !== undefined) setScope(init.scope);
    if (init.analysis !== undefined) setAnalysis(init.analysis);
    if (init.mode !== undefined) setMode(init.mode);
    if (init.fixtureId !== undefined) setFixtureId(init.fixtureId);
    if (init.matchDate !== undefined) setMatchDate(init.matchDate);
    hydratedRef.current = true;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Grava o subconjunto persistível sempre que algo relevante muda.
  useEffect(() => {
    if (typeof window === "undefined" || !hydratedRef.current) return;
    try {
      const payload: Persisted = {
        homeTeamId, awayTeamId, competition, neutralField, analysis, mode, fixtureId, matchDate, scope,
      };
      window.localStorage.setItem(LS_KEY, JSON.stringify(payload));
    } catch {
      /* localStorage cheio/indisponível — silencioso, não quebra a UI */
    }
  }, [homeTeamId, awayTeamId, competition, neutralField, analysis, mode, fixtureId, matchDate, scope]);

  return (
    <PredictionContext.Provider
      value={{
        homeTeamId, setHomeTeamId,
        awayTeamId, setAwayTeamId,
        competition, setCompetition,
        neutralField, setNeutralField,
        scope, setScope,
        analysis, setAnalysis,
        h2hData, setH2hData,
        mode, setMode,
        fixtureId, setFixtureId,
        matchDate, setMatchDate,
      }}
    >
      {children}
    </PredictionContext.Provider>
  );
}

export function usePrediction() {
  const context = useContext(PredictionContext);
  if (context === undefined) {
    throw new Error("usePrediction must be used within a PredictionProvider");
  }
  return context;
}
