# Bateria de melhorias — CONSOLIDADO (2026-07-06/07)

Todos sob o **gate §6**: CV temporal expanding, point-in-time, reduzir Log-loss sem piorar ECE
vs produção, consistência em folds/segmentos. Cada experimento tem script isolado + relatório.

## Placar geral

| # | Experimento | Veredito | Ganho / observação |
|---|---|---|---|
| — | Momentum de EQUIPE (resultado) | ❌ Reprovado | Elo satura; pior nos equilibrados |
| — | Momentum de JOGADOR (goleador) | ✅ **Em produção** | AUC 0.71→0.75; mercado "Jogador a Marcar" lançado |
| — | Força da escalação (personnel) | 🟡 Promissor | dRMSE −0.007 além do Elo; limitado à cobertura |
| 6 | Ratings Dinâmicos (DC evolutivo) | ❌ Puro reprovado / 🟡 feature âmbar | GBM+features bate rating de 2 params; feature −0.0015 |
| 7 | **Contagem multivariada (cópula)** | ✅ **APROVADO** | fator ofensivo (fin↔a-gol +0.57, ↔esc +0.30); NLL conjunto −0.28 |
| 8 | **Player props (finalizações)** | ✅ **APROVADO** | ≥2 chutes AUC 0.76; a-gol ≥1 AUC 0.74 (cartão fraco) |
| 9 | Goleiro adversário no scorer | 🟡 Negligível | +0.0003 AUC (redundante com opp_gc) |
| 10 | Correlação 1º×2º tempo | 🟡 Negligível | corr +0.066; NLL −0.0016 (tempos ~independentes) |
| 11 | Cobrador de pênalti no scorer | 🟡 Marginal | +0.0011 AUC (base já embute) |

## As DUAS oportunidades claras para produção

### 1. Cópula para apostas COMBINADAS (EXP 7) — maior ganho, baixo risco
As contagens ofensivas (finalizações, a-gol, escanteios) partilham um fator latente
("intensidade territorial"): correlações residuais **+0.28 a +0.57** DEPOIS dos modelos de
produção. Hoje o "Monte sua Aposta" multiplica odds assumindo **independência**, o que
**superestima muito** a dificuldade de combos ofensivos positivamente correlacionados.
**Ação:** persistir Σ (matriz de correlação da cópula, por corte recente) e aplicar na odd
combinada quando as seleções forem de contagens correlacionadas. Não mexe nos marginais.

### 2. Família de props de finalizações do jogador (EXP 8)
Além do goleador já em produção, "Over/Under finalizações do jogador" e "finalização a gol"
têm AUC 0.74–0.76, bem calibrados (ECE ~1%), com o cruzamento **forma × concessão do adversário**.
**Ação:** modelo análogo ao `scorer_model` com linhas 0.5/1.5/2.5.

## Padrão geral / conclusão
O núcleo de **resultado/gols agregados está saturado** (Elo domina; ratings dinâmicos, momentum
de equipe e goleiro adversário não passam). O valor novo está em **(a) estrutura de dependência
para combos** e **(b) granularidade de jogador** — ambos abrem mercados/correções novas em vez de
disputar o sinal já saturado do Elo. Cartões (equipe e jogador) seguem os menos previsíveis
(idiossincráticos/árbitro, sem dado de árbitro por jogador).

Relatórios detalhados: `docs/EXP6..EXP11_*.md`, `docs/BATERIA_HIPOTESES_MOMENTUM_2026-07.md`.
