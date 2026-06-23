// Dados simulados para a plataforma preditiva

export const TEAMS = [
  { id: 1, name: "Brasil", code: "BRA", elo: 2140 },
  { id: 2, name: "Argentina", code: "ARG", elo: 2120 },
  { id: 3, name: "França", code: "FRA", elo: 2085 },
  { id: 4, name: "Alemanha", code: "ALE", elo: 2050 },
  { id: 5, name: "Espanha", code: "ESP", elo: 2070 },
  { id: 6, name: "Inglaterra", code: "ING", elo: 2060 },
  { id: 7, name: "Portugal", code: "POR", elo: 2030 },
  { id: 8, name: "Itália", code: "ITA", elo: 2010 },
  { id: 9, name: "Bélgica", code: "BEL", elo: 1990 },
  { id: 10, name: "Holanda", code: "HOL", elo: 2000 },
  { id: 11, name: "Uruguai", code: "URU", elo: 1960 },
  { id: 12, name: "Colômbia", code: "COL", elo: 1940 },
  { id: 13, name: "Croácia", code: "CRO", elo: 1970 },
  { id: 14, name: "México", code: "MEX", elo: 1900 },
  { id: 15, name: "Dinamarca", code: "DIN", elo: 1920 },
  { id: 16, name: "Japão", code: "JAP", elo: 1880 },
  { id: 17, name: "Suíça", code: "SUI", elo: 1910 },
  { id: 18, name: "Marrocos", code: "MAR", elo: 1870 },
  { id: 19, name: "Senegal", code: "SEN", elo: 1840 },
  { id: 20, name: "Estados Unidos", code: "EUA", elo: 1850 },
];

export const COMPETITIONS = [
  "Copa do Mundo FIFA",
  "Eliminatórias Copa do Mundo",
  "Copa América",
  "Eurocopa",
  "Liga das Nações UEFA",
  "Amistoso Internacional",
  "Copa das Confederações",
  "Copa Asiática",
  "Copa Africana de Nações",
];

const RESULTS = ['V', 'E', 'D'];
const OPPONENTS_MAP = {
  "Brasil": ["Chile", "Paraguai", "Bolívia", "Peru", "Equador"],
  "Argentina": ["Venezuela", "Colômbia", "Peru", "Chile", "Uruguai"],
  "França": ["Bélgica", "Alemanha", "Espanha", "Itália", "Portugal"],
  "Alemanha": ["Holanda", "Polônia", "Áustria", "Suíça", "Hungria"],
  "Espanha": ["Portugal", "Itália", "Marrocos", "Suíça", "Geórgia"],
  "Inglaterra": ["Escócia", "País de Gales", "Irlanda", "Sérvia", "Dinamarca"],
};

function randInt(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

function randFloat(min, max, dec = 2) {
  return parseFloat((Math.random() * (max - min) + min).toFixed(dec));
}

export function generateRecentForm(teamName) {
  const opponents = OPPONENTS_MAP[teamName] || ["Adversário A", "Adversário B", "Adversário C", "Adversário D", "Adversário E"];
  return Array.from({ length: 5 }, (_, i) => {
    const result = RESULTS[randInt(0, 2)];
    const golsPro = result === 'V' ? randInt(1, 4) : result === 'E' ? randInt(0, 2) : randInt(0, 1);
    const golsContra = result === 'D' ? randInt(1, 4) : result === 'E' ? golsPro : randInt(0, golsPro - 1 < 0 ? 0 : golsPro - 1);
    return {
      result,
      score: `${golsPro}-${golsContra}`,
      opponent: opponents[i % opponents.length],
      stats: {
        golsPro,
        golsContra,
        chutes: randInt(8, 22),
        chutesNoAlvo: randInt(3, 10),
        escanteios: randInt(2, 12),
        cartoes: randInt(0, 5),
      }
    };
  });
}

export function generateAnomalies(teamName) {
  const anomalies = [
    `${teamName} tomou 5 cartões nos últimos 2 jogos, 4x sua média histórica`,
    `Média de finalizações caiu 40% nos últimos 3 jogos em relação à temporada`,
    `${teamName} não sofre gols há 3 partidas consecutivas — sequência incomum`,
    `Taxa de conversão de chutes em gol subiu para 28%, 2.5x acima da média`,
    `Escanteios a favor caíram para 2.3/jogo, muito abaixo da média de 5.8`,
  ];
  const hasAnomalies = Math.random() > 0.3;
  if (!hasAnomalies) return [];
  const count = randInt(1, 3);
  const shuffled = [...anomalies].sort(() => Math.random() - 0.5);
  return shuffled.slice(0, count);
}

export function generateProjection(homeTeam, awayTeam) {
  const homeStrength = (homeTeam?.elo || 2000) / 2000;
  const awayStrength = (awayTeam?.elo || 2000) / 2000;
  const diff = homeStrength - awayStrength;

  const homeGoals = Math.max(0.5, 1.5 + diff * 2 + randFloat(-0.3, 0.3));
  const awayGoals = Math.max(0.3, 1.2 - diff * 1.5 + randFloat(-0.3, 0.3));

  return {
    predictedScore: {
      home: Math.round(homeGoals),
      away: Math.round(awayGoals),
    },
    confidence: {
      totalGames: randInt(5, 35),
    },
    markets: {
      gols: {
        label: "Gols Totais",
        mean: parseFloat((homeGoals + awayGoals).toFixed(1)),
        distribution: generateDistribution(homeGoals + awayGoals, 0, 8),
      },
      finalizacoes: {
        label: "Finalizações Totais",
        mean: randFloat(18, 28, 1),
        distribution: generateDistribution(22, 8, 38),
      },
      escanteios: {
        label: "Escanteios Totais",
        mean: randFloat(8, 14, 1),
        distribution: generateDistribution(10.5, 2, 20),
      },
      cartoes: {
        label: "Cartões Totais",
        mean: randFloat(3, 7, 1),
        distribution: generateDistribution(4.5, 0, 12),
      },
    },
    h2h: generateH2H(homeTeam, awayTeam),
    eloHistory: generateEloHistory(homeTeam, awayTeam),
  };
}

function generateDistribution(mean, min, max) {
  const points = [];
  for (let x = min; x <= max; x += 0.5) {
    const z = (x - mean) / (mean * 0.35);
    const prob = Math.max(0, Math.exp(-0.5 * z * z) / (mean * 0.35 * Math.sqrt(2 * Math.PI)));
    points.push({ value: x, probability: parseFloat(prob.toFixed(4)) });
  }
  // Normalize
  const total = points.reduce((s, p) => s + p.probability, 0);
  points.forEach(p => p.probability = parseFloat((p.probability / total).toFixed(4)));
  return points;
}

function cdfFromDistribution(distribution, threshold) {
  let cumulative = 0;
  for (const point of distribution) {
    if (point.value >= threshold) break;
    cumulative += point.probability;
  }
  return Math.min(1, Math.max(0, cumulative));
}

export function getOddFromProb(prob) {
  if (prob <= 0) return 999;
  return parseFloat((1 / prob).toFixed(2));
}

export function getProbFromOdd(odd) {
  if (odd <= 1) return 1;
  return parseFloat((1 / odd).toFixed(4));
}

export function calculateOverProb(distribution, line) {
  const under = cdfFromDistribution(distribution, line + 0.5);
  return parseFloat((1 - under).toFixed(4));
}

export function calculateUnderProb(distribution, line) {
  return parseFloat(cdfFromDistribution(distribution, line + 0.5).toFixed(4));
}

function generateH2H(homeTeam, awayTeam) {
  const games = randInt(5, 15);
  const matches = [];
  for (let i = 0; i < Math.min(games, 8); i++) {
    const hg = randInt(0, 4);
    const ag = randInt(0, 3);
    matches.push({
      year: 2024 - i,
      competition: COMPETITIONS[randInt(0, COMPETITIONS.length - 1)],
      homeGoals: hg,
      awayGoals: ag,
      homeTeam: homeTeam?.name || "Mandante",
      awayTeam: awayTeam?.name || "Visitante",
    });
  }
  const totalHomeGoals = matches.reduce((s, m) => s + m.homeGoals, 0);
  const totalAwayGoals = matches.reduce((s, m) => s + m.awayGoals, 0);
  return {
    totalGames: games,
    avgGoalDiff: parseFloat(((totalHomeGoals - totalAwayGoals) / matches.length).toFixed(2)),
    matches,
  };
}

function generateEloHistory(homeTeam, awayTeam) {
  const years = [];
  let homeElo = (homeTeam?.elo || 2000) - randInt(50, 200);
  let awayElo = (awayTeam?.elo || 1950) - randInt(50, 200);
  for (let y = 2016; y <= 2024; y++) {
    homeElo += randInt(-40, 60);
    awayElo += randInt(-40, 60);
    years.push({
      year: y,
      [homeTeam?.name || "Mandante"]: Math.round(homeElo),
      [awayTeam?.name || "Visitante"]: Math.round(awayElo),
    });
  }
  return years;
}

export function generateScatterData(homeTeam, awayTeam) {
  const homeData = Array.from({ length: 20 }, () => ({
    attack: randFloat(0.8, 2.8),
    defense: randFloat(0.3, 2.2),
    team: homeTeam?.name || "Mandante",
  }));
  const awayData = Array.from({ length: 20 }, () => ({
    attack: randFloat(0.6, 2.5),
    defense: randFloat(0.4, 2.4),
    team: awayTeam?.name || "Visitante",
  }));
  return { homeData, awayData };
}

export function generateFrequencyData(teamName, metric) {
  const maxVal = metric === 'escanteios' ? 16 : 10;
  return Array.from({ length: maxVal + 1 }, (_, i) => {
    const mean = metric === 'escanteios' ? 5.5 : 3.2;
    const z = (i - mean) / (mean * 0.45);
    const freq = Math.max(0, Math.round(20 * Math.exp(-0.5 * z * z) / (mean * 0.45 * 2.5)));
    return { value: i, frequency: freq, label: `${i}` };
  });
}