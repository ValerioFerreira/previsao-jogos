// Nomes de competição em PT-BR. Os nomes de liga vêm da API em inglês
// (ex.: "World Cup", "Friendlies", "UEFA Nations League"). Só para exibição.
const COMP: Record<string, string> = {
  'World Cup': 'Copa do Mundo',
  'Friendlies': 'Amistosos',
  'Friendly': 'Amistoso',
  'UEFA Nations League': 'Liga das Nações da UEFA',
  'CONCACAF Nations League': 'Liga das Nações da CONCACAF',
  'Euro Championship': 'Eurocopa',
  'UEFA Euro Championship': 'Eurocopa',
  'Copa America': 'Copa América',
  'African Cup of Nations': 'Copa Africana de Nações',
  'Africa Cup of Nations': 'Copa Africana de Nações',
  'AFC Asian Cup': 'Copa da Ásia',
  'Gold Cup': 'Copa Ouro da CONCACAF',
  'CONCACAF Gold Cup': 'Copa Ouro da CONCACAF',
  'COSAFA Cup': 'Copa COSAFA',
  'Premier League': 'Premier League',
  'Olympics Men': 'Olimpíadas (Masculino)',
  'CECAFA': 'Copa CECAFA',
};

// Sufixos/variações de "eliminatórias" por confederação.
const QUALIF_PT: [RegExp, string][] = [
  [/world cup.*qualif.*(europe)/i, 'Eliminatórias da Copa do Mundo (Europa)'],
  [/world cup.*qualif.*(south america|conmebol)/i, 'Eliminatórias da Copa do Mundo (América do Sul)'],
  [/world cup.*qualif.*(africa|caf)/i, 'Eliminatórias da Copa do Mundo (África)'],
  [/world cup.*qualif.*(asia|afc)/i, 'Eliminatórias da Copa do Mundo (Ásia)'],
  [/world cup.*qualif.*(concacaf|north)/i, 'Eliminatórias da Copa do Mundo (CONCACAF)'],
  [/world cup.*qualif.*(oceania|ofc)/i, 'Eliminatórias da Copa do Mundo (Oceania)'],
  [/world cup.*qualif/i, 'Eliminatórias da Copa do Mundo'],
  [/euro.*qualif/i, 'Eliminatórias da Eurocopa'],
  [/asian cup.*qualif/i, 'Eliminatórias da Copa da Ásia'],
  [/african cup.*qualif|africa cup.*qualif/i, 'Eliminatórias da Copa Africana'],
];

export function competitionPt(name?: string | null): string {
  if (!name) return '';
  // remove ano final (ex.: "Premier League 2024")
  const base = name.replace(/\s+\d{4}(\/\d{2,4})?$/, '').trim();
  if (COMP[base]) return COMP[base];
  for (const [re, pt] of QUALIF_PT) if (re.test(base)) return pt;
  if (COMP[name]) return COMP[name];
  return base;
}
