# EXP 6 — Ratings Dinâmicos (Dixon-Coles Evolutivo / online) — 2026-07-07

## Arquitetura / matemática
Força de **ataque** `att_i` e **defesa** `def_i` de cada seleção como variáveis latentes que
evoluem no tempo (estilo Kalman/online), em vez de features rolantes num GBM:

```
λ_home = exp(μ + hfa·(1-neutral) + att[h] − def[a])
λ_away = exp(μ +                    att[a] − def[h])
P(x,y) = Poisson(λ_home)(x) · Poisson(λ_away)(y) · τ_DC(x,y; ρ)   (correção de placar baixo)
```
Atualização **online** por gradiente da log-verossimilhança Poisson, **point-in-time**
(prevê ANTES de ver o placar) e **cronológica**, com reversão à média (decay κ):
```
att[h] += η·(y_h − λ_h);  def[a] += η·(λ_h − y_h)   (idem outro lado);  att,def *= (1−κ)
```
μ e hfa fixos (log da média global de gols); ρ ≈ −0.05. Hiperparâmetros (η, κ) escolhidos por
Log-loss num split de validação temporal (η=0.06, κ=0). Script: `scripts/exp6_dynamic_ratings.py`.
Gate §6: CV temporal expanding (cortes 0.5→0.85), vs **DixonColes-NB de PRODUÇÃO**.

## Resultados
**(a) Ratings dinâmicos PUROS vs produção (LogLoss do resultado):**

| fold | prod_LL | dyn_LL | prod_ECE | dyn_ECE | prod_Brier | dyn_Brier |
|---|---|---|---|---|---|---|
| 0.50 | 0.8893 | 0.9117 | 2.04% | 3.03% | 0.520 | 0.538 |
| 0.62 | 0.8831 | 0.8944 | 1.62% | 2.10% | 0.519 | 0.527 |
| 0.73 | 0.8888 | 0.8973 | 2.51% | 2.51% | 0.524 | 0.529 |
| 0.85 | 0.8410 | 0.8563 | 2.46% | 2.01% | 0.493 | 0.503 |

**dLL médio +0.0144 (dyn melhora 0/4), dECE +0.25%, dBrier +0.010.**

**(b) Ratings dinâmicos como FEATURES no DC-NB (base vs base+dyn):**

| fold | base_LL | +dyn_LL | base_ECE | +dyn_ECE |
|---|---|---|---|---|
| 0.50 | 0.8893 | 0.8896 | 2.04% | 1.88% |
| 0.62 | 0.8831 | 0.8821 | 1.62% | 1.81% |
| 0.73 | 0.8888 | 0.8869 | 2.51% | 2.35% |
| 0.85 | 0.8410 | 0.8375 | 2.46% | 2.43% |

**dLL −0.0015 (melhora 3/4), dECE −0.04%.**

## Veredito
- **Ratings dinâmicos PUROS: REPROVADO.** Piores que o GBM+DC de produção em 4/4 folds
  (LogLoss, ECE e Brier). Um modelo de 2 parâmetros/time não bate o GBM rico em 158 features
  (Elo + forma + box-score + pace). Consistente com o histórico ("ataque×defesa força-pura"
  já reprovado, Fase 7/Exp 5).
- **Ratings dinâmicos como FEATURE: ÂMBAR / marginal.** Ganho pequeno e consistente
  (−0.0015 LogLoss, 3/4 folds, ECE não piora). Da mesma ordem do "forma-blend" que ficou
  âmbar e não foi promovido. **Não promovido** sem: (1) checagem de consistência por segmento
  (competição/equilíbrio) e (2) re-treino do DC de produção com as 5 features. É a variante
  mais próxima de valor deste experimento, mas o ganho é pequeno demais para promover às cegas.

**Conclusão:** o Elo pré-jogo NÃO é tão defasado a ponto de um rating dinâmico substituí-lo; o
valor residual (recência) que o dinâmico captura é ~o mesmo do momentum de forma (já reprovado
como sinal forte). Fica como feature candidata marginal, não como substituição do modelo.
