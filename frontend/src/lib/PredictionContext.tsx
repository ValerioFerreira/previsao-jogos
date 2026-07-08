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
  // Lazy init a partir do localStorage (só no cliente; no SSR cai nos defaults).
  const init = loadPersisted();
  const [homeTeamId, setHomeTeamId] = useState(init.homeTeamId ?? "");
  const [awayTeamId, setAwayTeamId] = useState(init.awayTeamId ?? "");
  const [competition, setCompetition] = useState(init.competition ?? "Copa do Mundo");
  const [neutralField, setNeutralField] = useState(init.neutralField ?? false);

  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(init.analysis ?? null);
  const [h2hData, setH2hData] = useState<any>(null);
  const [mode, setMode] = useState<"independente" | "futura">(init.mode ?? "futura");
  const [fixtureId, setFixtureId] = useState<number | null>(init.fixtureId ?? null);
  const [matchDate, setMatchDate] = useState<string | undefined>(init.matchDate ?? undefined);

  // Grava o subconjunto persistível sempre que algo relevante muda.
  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const payload: Persisted = {
        homeTeamId, awayTeamId, competition, neutralField, analysis, mode, fixtureId, matchDate,
      };
      window.localStorage.setItem(LS_KEY, JSON.stringify(payload));
    } catch {
      /* localStorage cheio/indisponível — silencioso, não quebra a UI */
    }
  }, [homeTeamId, awayTeamId, competition, neutralField, analysis, mode, fixtureId, matchDate]);

  return (
    <PredictionContext.Provider
      value={{
        homeTeamId, setHomeTeamId,
        awayTeamId, setAwayTeamId,
        competition, setCompetition,
        neutralField, setNeutralField,
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
