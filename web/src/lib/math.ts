export function getOddFromProb(prob: number): number {
  if (prob <= 0) return 999;
  return parseFloat((1 / prob).toFixed(2));
}

export function getProbFromOdd(odd: number): number {
  if (odd <= 1) return 1;
  return parseFloat((1 / odd).toFixed(4));
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
