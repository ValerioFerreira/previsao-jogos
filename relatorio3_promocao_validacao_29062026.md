# Relatório 3 — Promoção sob gate + validação rigorosa + nova rodada de experimentos

_29/06/2026 · branch `claude-testing` · CV temporal expanding (4 folds, cuts 0.50/0.62/0.73/0.85), seed=42, point-in-time (apenas features pré-jogo). Nada promovido apenas por "parecer melhor"._

## 0. Resumo executivo (responde a Parte 5.7)
- **O que entrou em produção:** **NADA.** Nenhuma das mudanças propostas passou no gate de não-regressão sob validação temporal.
- **Por quê:** a produção **já usa as melhores escolhas** (NB para finalizações/escanteios/a-gol; Generalized-Poisson para cartões; Dixon-Coles-NB para gols) e **já é bem calibrada** (ECE ~3–4%). Os "ganhos" dos relatórios 1–2 eram contra **baselines que não são a produção** (Poisson construído do zero; CV **aleatória**). Sob o protocolo correto (temporal, vs produção real), os ganhos **não se confirmam**.
- **Quanto melhorou / onde:** ganhos robustos = ~0. Sinais marginais e **inconsistentes** por segmento (não promovíveis).
- **Valeu a complexidade?** Não para promoção agora; **valeu como blindagem científica** — evitou promover ruído para produção.
- **Próximos passos:** ver §6.

## 1. Premissa corrigida (investigação de divergência — exigida pela diretriz)
Os relatórios anteriores sugeriam "trocar Poisson→NB" em finalizações/escanteios. **Verificação no código de produção** (`backend/`):
| Mercado | Produção hoje |
|---|---|
| Finalizações | `ShotsNB` = **Negative Binomial** |
| Escanteios | `CornersNB` r-fixo = **Negative Binomial** |
| Finalizações a gol | `shots_on_target_nb` (ShotsNB) = **Negative Binomial** |
| Cartões | `CardsGP` = **Generalized Poisson** |
| Gols / resultado | `DixonColesNBRegressor` = **DC-NB** |

→ A produção **não usa Poisson**. O ganho "Poisson→NB" do relatório 2 era vs um **baseline Poisson do experimento**, não vs produção. A pergunta científica real vira **"GP bate a NB de produção?"**.

## 2. PARTE 1 — Promoções (decisão sob gate)

### Item 1 — Resultado (H/D/A) com forma de jogador → **REPROVADO**
Gate honesto: a forma agrega **além do base_feats** (que já contém forma de resultado)? CV temporal nos 2.123 jogos com forma:
| Segmento | Elo (LR) | Elo+forma | base_feats | base+forma |
|---|---|---|---|---|
| Todos | **0.8479** | 0.8510 | 1.0088 | 1.0117 |
| Alta cobertura (≥0.7) | **0.9233** | 0.9343 | 2.389 | 2.439 |
| Equilibrados \|elo\|≤100 | **1.0940** | 1.1056 | 1.466 | 1.479 |
Adicionar forma **piora** LogLoss e ECE em **todos** os segmentos. **Divergência vs Relatório 1:** lá a CV era `RepeatedStratifiedKFold` **aleatória** (ganho minúsculo −0.0013); sob **CV temporal** (point-in-time) o sinal some/inverte. Conclusão: **não promover.**

### Itens 2–4 — Finalizações / Escanteios / Finalizações a gol → **MANTER NB (não promover GP)**
Validação segmentada (GBR + dist; pooled OOF temporal). GP vs **NB (produção)**, LogLoss de contagem:
| Mercado | lado | NB | GP | GP−NB | veredito |
|---|---|---|---|---|---|
| Finalizações | total | 3.2780 | 3.2801 | **+0.0021** | GP pior |
| Finalizações | mand/vis | 3.019/2.932 | 3.013/2.922 | −0.006/−0.010 | inconsistente |
| Escanteios | total | 2.6393 | 2.6388 | −0.0004 | empate |
| Finalizações a gol | total | 2.6014 | 2.6010 | −0.0004 | empate |
Por segmento (equilíbrio/competição/continente) o sinal **alterna** (ex.: finalizações total — favorito_forte +0.007, UEFA +0.010, amistoso −0.006). **NB esmaga Poisson** (confirma o relatório 2), mas **GP não bate a NB de produção** de forma consistente. **Gate: não promover** (manter NB).

### Item 5 — Gols → **MANTER** (Dixon-Coles-NB). Item 6 — Cartões → **MANTER** (CardsGP); **árbitro não promovido** (relatório 2: sem ganho; amostra rasa por árbitro).

## 3. PARTE 2 — Nova rodada de experimentos

### Exp 1 — Calibração → **sem ganho robusto (não promover)**
Isotonic · Platt · Beta nas probabilidades O/U (NB de produção), split temporal. Média sobre mercados/lados:
| Método | Brier | LogLoss | ECE |
|---|---|---|---|
| **base (produção)** | **0.2082** | **0.6007** | **3.99%** |
| isotonic | 0.2093 | 0.6041 | 4.44% |
| platt | 0.2096 | 0.6049 | 4.61% |
| beta | 0.2096 | 0.6034 | 4.96% |
Os modelos **já são bem calibrados**; calibração pós-hoc **piora na média** (sobreajusta o split). Ganho só marginal e pontual (Platt em finalizações: ECE 5.8%→4.0%). Reliability bins em `calibration_reliability.csv`.

### Exp 2 — Features de posse/passes/faltas → **sem ganho consistente (não promover)**
Posse/passes/faltas rolling (pré-jogo) **não** estão no base_feats hoje. Adicioná-los (NB, CV temporal) dá Δ **alternante**: escanteios vis −0.004 mas mand +0.0035; finalizações total −0.0035 mas mand +0.011; etc. Nenhum mercado melhora em mand+vis+total juntos. **Gate: não promover.**

### Exp 3 (multi-output/cadeias), Exp 4 (bivariada/cópulas), Exp 5 (ataque×defesa) — **desenhados, próxima fase**
Não executados nesta rodada (priorizei os bounded de maior valor e o rigor da Parte 1). Justificativa baseada em evidência: **o Dixon-Coles de produção já modela ataque×defesa e a correlação mandante×visitante (Exp 4/5) para gols**; trabalho anterior mediu correlação fraca em escanteios (β≈−0.04). Expectativa de ganho baixa, mas ficam como experimentos formais (ver `novo_contexto.md`).

## 4. PARTE 3 — Segmentação
As avaliações de contagem foram segmentadas por **equilíbrio** (|elo|≤80 / 80–150 / >150), **competição** (Copa do Mundo, Eliminatórias, Nations League, Amistoso, Continental) e **continente** (UEFA/CONMEBOL/AFC/CAF/CONCACAF). Não há um segmento onde GP supere NB de forma estável; idem para forma no resultado e para posse. Dados por linha em `backend/data/reports/market_promotion_pooled.csv`.

## 5. PARTE 4 — Gates (todos aplicados)
| Gate | Resultado |
|---|---|
| Reduz LogLoss vs produção | ❌ nenhuma mudança |
| Não piora calibração (ECE) | mudanças tendiam a piorar |
| Passa CV temporal | ❌ (forma reprovou; GP empata) |
| Sem leakage (point-in-time) | ✅ garantido (residualização por fold; features pré-jogo) |
| Tempo de inferência | sem impacto (nada mudou) |
→ Conforme regra, **reverter/não promover** todas. Produção permanece intacta.

## 6. Próximos passos
1. **Exp 3/4/5** como bateria formal: bivariada/cópula para escanteios×escanteios e finalizações; multi-output (posse→finalizações→escanteios→gols) com cadeia de regressão; comparar vs independentes.
2. **Feature importance (SHAP/permutação)** dos modelos de produção para interpretabilidade (Parte 5.5) — rodar `permutation_importance` por mercado.
3. Reavaliar a **forma de jogador** apenas como possível **blend de alta-cobertura** no resultado, com gate temporal (não como substituição).
4. Manter o pipeline atual — ele se mostrou **robusto e bem calibrado**; o valor desta rodada foi **confirmar isso com rigor** e impedir promoções de ruído.
