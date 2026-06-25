"use client";
import React, { createContext, useContext, useState, ReactNode } from 'react';

type PredictionContextType = {
  homeTeamId: string;
  setHomeTeamId: (id: string) => void;
  awayTeamId: string;
  setAwayTeamId: (id: string) => void;
  competition: string;
  setCompetition: (comp: string) => void;
  neutralField: boolean;
  setNeutralField: (neutral: boolean) => void;
};

const PredictionContext = createContext<PredictionContextType | undefined>(undefined);

export function PredictionProvider({ children }: { children: ReactNode }) {
  const [homeTeamId, setHomeTeamId] = useState('');
  const [awayTeamId, setAwayTeamId] = useState('');
  const [competition, setCompetition] = useState('Copa do Mundo');
  const [neutralField, setNeutralField] = useState(false);

  return (
    <PredictionContext.Provider value={{
      homeTeamId, setHomeTeamId,
      awayTeamId, setAwayTeamId,
      competition, setCompetition,
      neutralField, setNeutralField
    }}>
      {children}
    </PredictionContext.Provider>
  );
}

export function usePrediction() {
  const context = useContext(PredictionContext);
  if (context === undefined) {
    throw new Error('usePrediction must be used within a PredictionProvider');
  }
  return context;
}
