export function getOddFromProb(prob: number): number {
  if (prob <= 0) return 999;
  // Odd justa nunca é menor que 1.00 (não existe no mercado).
  return Math.max(1, parseFloat((1 / prob).toFixed(2)));
}

export function getProbFromOdd(odd: number): number {
  if (odd <= 1) return 1;
  return parseFloat((1 / odd).toFixed(4));
}

// Faixa de "odd justa": da odd com 7% de margem para menos até a odd prevista (1/p).
// Mesmo critério usado nos cards de Mercados ("Ver Todas as Linhas").
export function fairOddRange(prob: number): string {
  if (!prob || prob <= 0) return "—";
  const odd = 1 / prob;
  if (odd > 50) return "50+";
  // Odd nunca abaixo de 1.00; se os limites colapsam em ~1.00, mostra valor único.
  const hi = Math.max(1, odd);
  const lo = Math.max(1, odd * 0.93);
  return lo.toFixed(2) === hi.toFixed(2) ? hi.toFixed(2) : `${lo.toFixed(2)}–${hi.toFixed(2)}`;
}

export function cdfFromDistribution(distribution: number[], threshold: number): number {
  let cumulative = 0;
  // distribution array contains probabilities for [0, 1, 2, ...]
  for (let i = 0; i < distribution.length; i++) {
    if (i >= threshold) break;
    cumulative += distribution[i];
  }
  return Math.min(1, Math.max(0, cumulative));
}

export function calculateOverProb(distribution: number[], line: number): number {
  // P(X > line) = 1 - P(X <= line)
  // For line like 2.5, we want P(X >= 3)
  const under = cdfFromDistribution(distribution, line + 0.5);
  return parseFloat((1 - under).toFixed(4));
}

export function calculateUnderProb(distribution: number[], line: number): number {
  // P(X < line)
  return parseFloat(cdfFromDistribution(distribution, line + 0.5).toFixed(4));
}
