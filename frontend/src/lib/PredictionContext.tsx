"use client";
import React, { createContext, useContext, useState, ReactNode } from "react";
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

export function PredictionProvider({ children }: { children: ReactNode }) {
  const [homeTeamId, setHomeTeamId] = useState("");
  const [awayTeamId, setAwayTeamId] = useState("");
  const [competition, setCompetition] = useState("Copa do Mundo");
  const [neutralField, setNeutralField] = useState(false);

  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [h2hData, setH2hData] = useState<any>(null);
  const [mode, setMode] = useState<"independente" | "futura">("futura");
  const [fixtureId, setFixtureId] = useState<number | null>(null);
  const [matchDate, setMatchDate] = useState<string | undefined>(undefined);

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
