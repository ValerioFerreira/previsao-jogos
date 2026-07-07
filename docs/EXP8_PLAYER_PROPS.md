# EXP 8 — Player Props: finalizações e cartões do jogador — 2026-07-07

## Arquitetura
Protótipo de props individuais a partir do `match_detail_cache` (~74k player-games de 9.902
jogadores, histórico 2010+ das 48 seleções). Features **point-in-time**: taxa-base encolhida
do jogador + forma recente (janelas 5/10) + **concessão defensiva do adversário** (finalizações
que o adversário costuma permitir; faltas do jogo = intensidade). Modelo GBM; taxa-base como
baseline. Props: P(chutes ≥2), P(chutes a gol ≥1), P(recebe cartão). Script:
`scripts/exp8_player_props.py`. Gate §6: CV temporal expanding; AUC/LogLoss/ECE vs taxa-base.

## Resultados (CV temporal, 4 cortes)
| Prop | taxa | AUC base→modelo | folds↑ | dLogLoss | ECE |
|---|---|---|---|---|---|
| **Finalizações ≥ 2** | 0.16 | 0.741 → **0.758** (+0.017) | **4/4** | −0.0096 | 0.98% |
| **Finalização a gol ≥ 1** | 0.22 | 0.719 → **0.735** (+0.016) | **4/4** | −0.0094 | 1.10% |
| Recebe cartão | 0.12 | 0.582 → 0.588 (+0.006) | 3/4 | −0.0020 | 1.41% |

## Veredito
- **Finalizações do jogador (≥2) e finalização a gol (≥1): APROVADO.** AUC usável (0.74–0.76),
  ganho consistente (4/4 folds), bem calibrado (ECE ~1%). O cruzamento **forma do jogador ×
  finalizações concedidas pelo adversário** adiciona sinal real. São mercados construíveis
  (mesma infra do goleador), de boa liquidez.
- **Cartão do jogador: REPROVADO/fraco.** AUC base 0.58 (quase moeda) e o modelo mal ajuda
  (+0.006). Cartão individual é **idiossincrático** (depende do árbitro, que não temos a nível
  de jogador) — coerente com o histórico (cartões = mercado menos previsível). Não vale construir
  sem dados de árbitro.

**Conclusão:** a granularidade do endpoint de jogadores é, de fato, subutilizada — dá para
abrir uma família de props de **finalizações** (além do goleador já em produção) com boa
qualidade. Props de **cartão** individual não têm previsibilidade suficiente.

**Próximo passo de produção (opcional):** modelo de "Over/Under finalizações do jogador"
(análogo ao scorer_model), com as mesmas features + linhas 0.5/1.5/2.5.
