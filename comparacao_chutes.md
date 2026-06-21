# Comparacao CHUTES — Quantilica vs NB independente (com varredura de decay)

- Corte 2024-10-12 | treino 3286 | teste 816 | grade M=55
- Vies = media prevista - real (negativo = subestima). H = meia-vida (anos).

## Mandante (linha O12.5)
| Abordagem | r | Vies | LogLoss | ECE |
|---|---|---|---|---|
| Quantilica (atual) | – | -1.345 | 3.1323 | 6.75% |
| NB sem decay | 21.7 | -0.798 | 3.0310 | 5.33% |
| NB decay H=3 | 20.4 | -0.605 | 3.0215 | 3.02% |
| NB decay H=2 | 19.7 | -0.524 | 3.0235 | 2.45% |
| NB decay H=1 | 17.6 | -0.391 | 3.0007 | 2.94% |
## Visitante (linha O10.5)
| Abordagem | r | Vies | LogLoss | ECE |
|---|---|---|---|---|
| Quantilica (atual) | – | -0.519 | 2.9546 | 5.31% |
| NB sem decay | 20.2 | -0.029 | 2.8657 | 4.77% |
| NB decay H=3 | 18.7 | +0.153 | 2.8707 | 5.13% |
| NB decay H=2 | 18.0 | +0.220 | 2.8703 | 4.90% |
| NB decay H=1 | 16.6 | +0.286 | 2.8757 | 5.32% |
## Total (linha O22.5)
| Abordagem | r | Vies | LogLoss | ECE |
|---|---|---|---|---|
| Quantilica (atual) | – | -1.018 | 3.3172 | 6.67% |
| NB sem decay | 21.0 | -0.827 | 3.2415 | 5.60% |
| NB decay H=3 | 19.6 | -0.451 | 3.2415 | 3.55% |
| NB decay H=2 | 18.8 | -0.304 | 3.2451 | 2.50% |
| NB decay H=1 | 17.1 | -0.105 | 3.2460 | 2.50% |