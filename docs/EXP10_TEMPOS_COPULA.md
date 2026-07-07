# EXP 10 — Correlação entre gols do 1º e 2º tempo (cópula) — 2026-07-07

## Hipótese
Os modelos de meio-tempo (gols_1t_nb, gols_2t_nb) preveem os tempos de forma INDEPENDENTE.
Haveria correlação entre o total de gols do 1º e do 2º tempo (jogos "abertos" com gols nos
dois; ou cansaço no 2º)? Se sim, combos "gols nos dois tempos" seriam mal precificados.

## Método
Cópula gaussiana sobre as PMFs dos totais 1ºT e 2ºT (mesmo método do EXP7), point-in-time,
CV temporal. Script: `scripts/exp10_halves_copula.py`. 6.218 jogos.

## Resultado
**corr(z_1ºT, z_2ºT) = +0.066** (global). NLL conjunto:

| fold | NLL indep | NLL cópula | dNLL | corr |
|---|---|---|---|---|
| 0.50 | 2.798 | 2.799 | +0.0012 | 0.076 |
| 0.62 | 2.838 | 2.836 | −0.0020 | 0.060 |
| 0.73 | 2.851 | 2.848 | −0.0030 | 0.062 |
| 0.85 | 2.922 | 2.920 | −0.0027 | 0.064 |

**dNLL −0.0016 (3/4 folds; o 1º regride).**

## Veredito: NEGLIGÍVEL — não vale
A correlação entre os tempos é **fraca (+0.066)** e o ganho conjunto é minúsculo (−0.0016, com
um fold regredindo). Ao contrário das contagens OFENSIVAS (EXP7: fator latente forte, +0.28 a
+0.57, dNLL −0.28), os dois tempos são **praticamente independentes** — modelá-los em conjunto
não agrega. Confirma que o "fator territorial" é específico das contagens ofensivas da mesma
partida, não uma dependência temporal genérica.
