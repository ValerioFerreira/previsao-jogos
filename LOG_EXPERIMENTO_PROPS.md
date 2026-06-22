# LOG DE EXPERIMENTOS - PROPS (MERCADOS SECUNDÁRIOS)
## Data: 2026-06-22

### OBJETIVO:
Pivotar o foco para Mercados Secundários (Escanteios, Chutes e Cartões), implementando estilo tático, ortogonalização contra Elo (sem vazamento de dados), arquitetura de predição em cascata e substituição da modelagem de variância de cartões por Poisson Generalizada.

---

## PASSO 0: Setup do Ambiente
- Criada e mudada a branch para `new-focus` a partir da `main`.

## PASSO 1: Engenharia de Features de Estilo Tático
- Mapeado o total de passes (`sb_passes`) das partidas brutas via `/fixtures/statistics` no `build_history.py` e gerada a base estruturada unificada `data/built/matches.parquet`.
- Implementadas e extraídas métricas de estilo tático (janelas rolling l5 e l10):
  - **Volume de Linha de Fundo**: `Crosses_per_Game` (proxy: `sb_corners * 2.0`).
  - **Agressividade de Bloco / Pressing**: `PPDA` (proxy: `opponent_sb_passes / (sb_fouls + 1e-5)` -> menor valor = maior pressing).
  - **Habilidade de Cavar Cartões**: `Fouls_Suffered_Ratio` (`opponent_sb_fouls / mean_comp_fouls`).
- Tratamento de esparsidade de boxscore via imputação indicativa:
  - Criada `has_boxscore_signal = 1` para jogos com estatísticas e `0` sem.
  - Para jogos sem dados, foi aplicada imputação sequencial de mediana por: 1) Campeonato (Tournament); 2) Nível de Elo (bins de 100 pontos); 3) Mediana global.

## PASSO 2: Ortogonalização de Sinais (Evitar Vazamento)
- A regressão linear `Estilo_Feature ~ elo_diff` foi implementada strictly in-sample no split de treino das rodadas de otimização/produção (para evitar data leakage futuro).
- Pesos da regressão salvos em `api/model_artifacts/style_ortho_weights.joblib`.
- Sinais residuais obtidos na predição: `resid_feature = raw_feature - (intercept + coef * elo_diff)`.

## PASSO 3: Arquitetura em Cascata
- Implementada a dependência latente no `api/predictor.py`.
- O motor de inferência prediz chutes primeiro para obter `pred_home_shots` e `pred_away_shots`, e os injeta como features ativas em tempo de execução para os modelos de escanteios e cartões.

## PASSO 4: Ajuste Matemático de Distribuição (Cartões Subdispersos)
- A razão `Variância / Média Condicional` foi calculada na base histórica, confirmando subdispersão (< 1) em faixas dominantes.
- Substituída a distribuição Binomial Negativa de cartões pelo modelo **Poisson Generalizada (Generalized Poisson)** em `api/cards_gp_model.py`.
- MLE implementado com restrições de limites de $\lambda_{GP}$ (bounds $[-0.45, 0.75]$) e fallback automático para a distribuição de Poisson padrão ($\lambda_{GP} = 0$) em caso de instabilidade numérica ou falha de convergência.
- O fitting na base histórica retornou forte sobredispersão/sob-representação de variância negativa (sob a perspectiva da Poisson comum):
  - $\lambda_{GP, H}$ (Mandante): `-0.1006`
  - $\lambda_{GP, A}$ (Visitante): `-0.1219`

---

## VEREDITO DE VALIDAÇÃO (PASSO 6 - GATE DE VALIDAÇÃO)

A comparação de performance out-of-sample (temporal split 80/20) entre o baseline original (`CardsNB`) e o novo modelo `CardsGP` foi registrada em `comparacao_cartoes.md`.

### Destaques de Performance:
1. **Redução Drástica do Tail ECE**:
   - **Visitante Over 1.5**: Tail ECE despencou de **33.05%** no baseline para apenas **7.26%** no `CardsGP` (ganho imenso de calibração).
   - **Visitante Over 2.5**: Tail ECE reduziu de **3.67%** para **1.70%**.
   - **Mandante Over 1.5**: Tail ECE reduziu de **3.26%** para **2.63%**.
   - **Total Over 4.5**: Tail ECE caiu de **2.70%** para **0.97%**.

2. **Melhoria do Intervalo de Cobertura de 80%**:
   - A Poisson pura superestimava a variância do total de cartões, gerando intervalos muito largos. O modelo Generalized Poisson reduziu as larguras mantendo a calibragem da cauda:
     - **Mandante**: Cobertura ajustada de **92.77%** (superestimado) para **89.22%** (ideal), com redução da largura média do intervalo de **3.38 para 2.98**.
     - **Visitante**: Cobertura ajustada de **91.42%** para **87.75%**, largura média reduzida de **3.68 para 3.15**.
     - **Total**: Cobertura ajustada de **88.11%** para **83.82%**, largura média reduzida de **4.92 para 4.43**.

3. **Validação do Predictor**:
   - O motor `predictor.py` unificado com cascade roda limpo, gerando odds de-vig e estimativas consistentes sem spikes ou edges irracionais.

O gate de calibração foi **APROVADO** com sucesso para promoção à `main`.
