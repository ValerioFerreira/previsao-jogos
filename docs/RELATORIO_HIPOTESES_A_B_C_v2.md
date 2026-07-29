# Relatório Técnico-Estratégico v2: Hipóteses A, B e C (reexecução honesta)

> **Data de execução**: 2026-07-28/29
> **Substitui**: `docs/RELATORIO_HIPOTESES_A_B_C.md` (v1, retirado — ver aviso no topo daquele
> arquivo e `DOCUMENTACAO_CENTRAL.md` §23/§24).
> **Diferença central vs v1**: modelo de produção real (`Predictor.predict_from_row`, artefato
> congelado `model_artifacts_clubes_2025frozen/`, cutoff 2025-07-01, **250.682 jogos de treino /
> 5.365 times**, sem vazamento) + odds 100% reais (`data-test/`) — nada fabricado.
> **Leia junto**: `DOCUMENTACAO_CENTRAL.md` §25 (o benchmark correto e o poder estatístico).

---

## 0. Escopo real desta rodada (leia antes dos números)

A máquina onde isto rodou tinha, no espelho local, apenas **4 competições de clube**
(Brasileirão A/B, Premier League, Champions League — 21.130 jogos), não as 83 competições que
alimentam a produção. Dessas 4, só **2 têm odds reais** em `data-test/`: **Premier League**
(380/380 casadas) e **Brasileirão Série A** (342/380). Champions League e Série B não têm fonte
de odds e ficaram de fora.

**N final: 722 partidas reais, temporada 2025/26, 2 ligas.** É uma fração pequena da promessa
original da v1 ("31 mil partidas, 89 competições, 2010-2026") — mas é honesto.

⚠️ **Ressalva de poder estatístico que atravessa TODO este relatório**: detectar um edge de 2%
com 80% de poder exigiria **~19.400 apostas**. Temos 722. **Nenhuma conclusão sobre lucro/edge
aqui é conclusiva, em nenhuma direção.** O que é sólido é a Hipótese A (alfa de cotação), cujo
efeito é grande e o intervalo, estreito.

---

## 1. Hipótese A — Alfa de cotação (melhor casa vs pior casa, odds reais)

**Metodologia**: para cada partida, o pick do modelo é confrontado com a odd `Max` real (melhor
cotação rastreada) e a pior odd individual real entre as casas rastreadas. Fechamento preferido,
abertura como fallback. IC 95% via bootstrap (20.000 reamostragens).

| Recorte | N | ROI melhor casa | ROI pior casa | **Alfa** | IC 95% |
|---|---:|---:|---:|---:|---|
| 1x2 (pooled) | 722 | −4.70% | −11.85% | **+7.15%** | [+6.05%, +8.31%] |
| O/U 2.5 (Premier League) | 380 | −8.41% | −10.53% | **+2.12%** | [+1.78%, +2.46%] |
| 1x2 / Brasileirão Série A | 342 | +2.52% | −0.59% | +3.11% | [+2.54%, +3.74%] |
| 1x2 / Premier League | 380 | −11.20% | −21.98% | +10.78% | [+8.82%, +12.87%] |
| **Tudo (pooled)** | 1102 | −5.98% | −11.39% | **+5.41%** | [+4.67%, +6.21%] |

**Leitura honesta**: o alfa é real e robusto — todos os intervalos excluem zero com folga. Mas é
**dispersão estrutural de mercado**, quase independente da qualidade do modelo: existe porque
casas diferentes precificam o mesmo evento de forma diferente. Note que o ROI **continua
negativo mesmo na melhor casa** em 3 dos 4 recortes. A mensagem correta é *"escolher a melhor
cotação reduz a perda esperada em ~5 a 11 pontos percentuais"*, **não** *"o comparador dá lucro"*.

---

## 2. Hipótese B — Modelo vs 3 perfis de apostador "de feeling"

**Metodologia**: os 3 perfis pedidos originalmente — **favoritista** (menor odd 1x2),
**emocional por gols** (sempre Over 2.5 — BTTS não existe em `data-test`) e **faixa de odd**
(lado do 1x2 com odd em [1.70, 2.20]) — vs o pick do modelo, todos com a **mesma fonte de
preço** (`book="Avg"`) para isolar habilidade de seleção da vantagem de comparar casas (medida
na Hipótese A). Bootstrap + Bonferroni/BH-FDR sobre 8 combinações liga×estratégia.

**O benchmark não é zero.** Com vig médio de 6.05%, o ROI esperado de *qualquer* apostador sem
vantagem alguma é **−5.71%**. Toda a tabela deve ser lida contra isso (ver §25.1 do doc-mestre).

| Estratégia | N | ROI | IC 95% | vs zero | **vs benchmark s/ edge** |
|---|---:|---:|---|---|---|
| modelo_1x2 (pooled) | 722 | −8.51% | [−15.77%, −1.17%] | exclui 0 | **−0.76σ — não significativo** |
| favoritista (pooled) | 722 | −6.35% | [−13.24%, +0.81%] | inclui 0 | dentro do ruído |
| faixa_odd_1.70-2.20 (pooled) | 281 | −11.57% | [−22.66%, −0.29%] | exclui 0 | ~−1σ, não significativo |
| modelo_ou (pooled) | 380 | −11.40% | [−20.33%, −2.48%] | exclui 0 | ~−1.2σ, não significativo |
| emocional_sempre_over (pooled) | 380 | −4.24% | [−13.25%, +4.54%] | inclui 0 | dentro do ruído |
| modelo_1x2 / Premier League | 380 | −15.04% | [−24.57%, −5.45%] | exclui 0 | **−1.99σ — limítrofe** |
| modelo_1x2 / Brasileirão A | 342 | −1.24% | [−12.12%, +9.56%] | inclui 0 | +0.86σ |

Correção de múltiplas comparações (8 combos): p<0.05 bruto = 3 | Bonferroni = 2 | BH/FDR = 3
— **mas todos contra zero**, o benchmark errado. Contra o benchmark correto, nenhum é
significativo com folga.

**Leitura honesta — o resultado mais importante para não vender errado**: **não há evidência de
que o modelo bata os apostadores de feeling.** Lido contra o benchmark correto, o pick do modelo
fica a −0.76σ da expectativa de quem não tem vantagem nenhuma — ou seja, indistinguível de "sem
edge". O caso mais negativo (Premier League, −1.99σ) é limítrofe e não sobreviveria à correção
de múltiplas comparações; interpretá-lo como "o modelo é anti-preditivo na Premier League" seria
sobreajustar ruído.

Vale registrar sem maquiar: **nesta amostra o pick do modelo teve ROI pior que o do apostador
favoritista** (−8.51% vs −6.35%). Com erro padrão de ~3.7pp, os dois são estatisticamente
indistinguíveis — mas o dado não autoriza, de forma alguma, a mensagem "com a ApostaInfo você
ganha mais que o apostador comum".

---

## 3. Hipótese C — Desagregação por liga e por ano

Piso de amostra N≥100 (nenhum grupo caiu no bucket "insuficiente" nesta rodada).

| Liga | N | Winrate | ROI | IC 95% |
|---|---:|---:|---:|---|
| Brasileirão Série A | 342 | 50.9% | −1.24% | [−12.12%, +9.56%] |
| Premier League | 380 | 46.8% | −15.04% | [−24.57%, −5.45%] |

| Ano (calendário) | N | Winrate | ROI | IC 95% |
|---|---:|---:|---:|---|
| 2025 | 528 | 51.5% | −1.79% | [−10.46%, +7.02%] |
| 2026 | 194 | 41.2% | −26.78% | [−39.45%, −13.83%] |

**Leitura honesta**: a "desagregação por ano" aqui é a **mesma temporada 2025/26** cortada pelo
calendário civil — **não** um teste de consistência multi-temporada como a v1 fabricou ("10 de
11 anos lucrativos, 2010-2026"). Com uma só temporada real, nada pode ser concluído sobre
estabilidade ano a ano. O 2026 (N=194) é meia temporada e o intervalo é enorme.

---

## 4. Reconciliação com §20 e §25

A bateria §20 (8.117 partidas reais, bootstrap 20k, correção de múltiplas comparações) concluiu
**sem edge robusto**. Esta rodada chega à **mesma conclusão de fundo**. O §25 explica *por quê*
e mostra que o modelo não está quebrado: em log-loss ele captura **~78%** da informação que o
mercado inteiro precifica, com ECE de 0.0207 (bem calibrado). A única descoberta nova e sólida
é a **Hipótese A** — vantagem estrutural de mercado, não vantagem do modelo.

---

## 5. Mensagens de produto defensáveis

1. **Pode comunicar** (Hipótese A, robusto): *"comparar a odd entre casas reduz a perda esperada
   em vários pontos percentuais."*
2. **Não pode comunicar** (Hipótese B, sem evidência): *"o modelo bate o apostador comum"* ou
   qualquer promessa de ROI/lucro do pick do modelo.
3. **Não pode comunicar** (Hipótese C): consistência ao longo dos anos — só há uma temporada.
4. **Próximo passo real**: concluir o backfill de competições e ampliar `data-test/` para
   temporadas antigas (§24.5 e §25.3), e migrar a métrica primária de ROI para **CLV**.

## 6. Arquivos gerados

- `backend/scripts/adhoc_hipotese_{a,b,c}_*.py`, `adhoc_diagnostico_modelo_vs_mercado.py`
- `backend/data/reports/hipotese_{a,b,c}_*.csv`, `diagnostico_modelo_vs_mercado.csv`
- `backend/data/built/backtest_{odds_normalized,matched,predictions}.parquet` (intermediários,
  regeráveis: `backtest_odds_ingest.py` → `backtest_match_games.py` →
  `backtest_generate_predictions.py`)
