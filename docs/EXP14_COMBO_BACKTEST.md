# EXP 14 — Validação prática: a cópula melhora combos de 2 pernas? — 2026-07-07

## Objetivo
Teste decisivo do valor da cópula (EXP7/EXP13): num combo "over A + over B", comparar
- `P_indep = p_A · p_B` (independência — como o "Monte sua Aposta" faz hoje)
- `P_cópula = P(Z_A>z_A, Z_B>z_B; ρ)` (normal bivariada, ρ estimado no passado)
e medir o **log-loss/Brier do desfecho REAL do combo** (as duas pernas baterem), CV temporal.
Script: `scripts/exp14_combo_backtest.py`. Linhas centrais (gols 2.5, finalizações 22.5, escanteios 9.5).

## Resultado
| Combo (over+over) | LL indep → cópula | dLL (folds↓) | Brier i→c | ρ |
|---|---|---|---|---|
| **gols + finalizações** | 0.5870 → 0.5820 | **−0.0050 (4/4)** | 0.2013→0.1987 | +0.216 |
| **finalizações + escanteios** | 0.5450 → 0.5435 | **−0.0016 (3/4)** | 0.1834→0.1815 | +0.282 |
| gols + escanteios | 0.4907 → 0.4902 | −0.0005 (2/4) | ~igual | −0.047 |

## Veredito: **APROVADO** — melhoria concreta e quantificada para combinadas
- Nos pares **correlacionados** (gols+finalizações, finalizações+escanteios) a cópula **reduz o
  log-loss do desfecho do combo** de forma consistente. O par **independente** (gols+escanteios)
  não muda — exatamente o esperado.
- Como o "Monte sua Aposta" multiplica odds assumindo **independência**, ele **superestima a
  dificuldade** de combos over+over positivamente correlacionados → oferece odds piores que a
  justa. A cópula corrige isso (probabilidade do combo maior → odd combinada mais justa).

**Recomendação de produção (a melhoria nº1 da bateria, validada 4×: EXP7, EXP7-ext, EXP13, EXP14):**
persistir uma matriz Σ do bloco {gols, finalizações, a-gol, escanteios} (por corte recente) e,
no cálculo da odd combinada, substituir o produto independente pela probabilidade conjunta da
cópula quando as pernas forem contagens correlacionadas. **Atenção:** isso altera a odd/liability
da promoção "ParcerIA" — requer sign-off do dono antes de ir para produção.
