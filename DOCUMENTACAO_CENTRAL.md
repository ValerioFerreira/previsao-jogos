# DOCUMENTAÇÃO CENTRAL — Previsão de Jogos (ApostAI)

> **Documento-mestre único e vivo.** Substitui e consolida todos os relatórios, contextos,
> handoffs e resumos anteriores. Descreve o que o projeto é, o que prevê, quais dados e
> modelos usa (e **por quê**), o que cada métrica significa (em linguagem clara), e **todo o
> histórico de desenvolvimento em ordem cronológica** com o resultado de cada tentativa e o
> motivo de cada aprovação/reprovação. Atualize este arquivo a cada nova sessão.
>
> Última atualização: **2026-07-18**. Branch de trabalho: `main` (pesquisa de clubes da branch
> `clubs`, §13, incorporada por merge) · produção: `main`.
> Companheiros mantidos: `README.md` (porta de entrada), `ARCHITECTURE.md` (infra/banco/e-mail)
> e `ESTADO_ATUAL_E_PROXIMOS_PASSOS.md` (handoff vivo — **leia primeiro ao retomar**).

---

## 1. O que é o projeto

Plataforma de **previsão probabilística de partidas de seleções** (futebol internacional
masculino adulto). Não prevê só "quem ganha": entrega a **distribuição de probabilidade** de
cada mercado, para comparar com odds de casas de aposta e medir valor.

**Monorepo:**
- **`/frontend`** — Next.js (TypeScript), deploy na **Vercel** (domínio de produção **`apostainfo.com.br`**).
- **`/backend`** — FastAPI (Python), deploy no **Render** (`api-previsoes-jogos.onrender.com`),
  venv em `backend/.venv`, porta 8000.
- **Banco** — **Neon** (PostgreSQL serverless). O disco do Render/Vercel é efêmero → todo o
  estado de produção vive no Neon + nos artefatos versionados em `backend/model_artifacts/`.

`npm run dev` na raiz sobe front+back juntos. Detalhes de infra/deploy/banco: `ARCHITECTURE.md`.

---

## 2. O que o sistema prevê (mercados)

Tudo é orquestrado por `backend/predictor.py::predict(home, away, neutral, tournament)`.

| Grupo | Mercados | Origem |
|---|---|---|
| Resultado | Vencedor 1X2, Ambas Marcam (BTTS), Over/Under 2.5, Total de gols, Gols por equipe, **Placar exato** (top-3 + alerta de desvio) | **matriz conjunta do Dixon-Coles-NB** |
| Contagem | Finalizações, Finalizações a gol, Escanteios, Cartões, **Impedimentos** — **total, por equipe e por tempo (1º/2º)** | modelos **NB/GP em cascata** |
| Derivados | Dupla chance, Empate anula (DNB), Handicap (linhas .5), Clean sheet, Vitória sem sofrer, Gols par/ímpar, Faixas de gols | **cortes exatos da matriz DC / PMFs de gols** |
| Apoio | Confiabilidade do jogo (cobertura de box-score), Confronto direto (H2H) | derivado |

> **Impedimentos** (`offsides_nb.joblib`, NB, exposto **cru** — a calibração isotônica não passou o gate) e os **mercados derivados** (transformações exatas de distribuições já validadas, sem gate próprio) foram adicionados em 2026-07-06 na fase de expansão de mercados.

Cada mercado de contagem expõe a **PMF completa** (distribuição de probabilidade de massa,
"fonte de verdade") e, dela, as linhas Over/Under com **odd justa = 1/probabilidade** (sem
margem da casa). As linhas O/U do **total** de escanteios/a-gol/cartões passam por uma
**calibração isotônica** validada (ver §6 e §9, item 2026-06-30).

---

## 3. Dados

### 3.1 Fonte e dataset de treino
- **`international_features_enriched_apifootball.csv`** (raiz do backend, **gitignored**; espelhado
  na tabela `features_enriched` do Neon). **~9.976 jogos**, 2016→2026, **~319 colunas**.
- Resultados e Elo ancorados na base histórica **martj42** (49.477 jogos, 1872+); estatísticas
  avançadas (box-score: chutes, a-gol, escanteios, cartões, faltas, posse, passes) da **API-Football**.
- **Cobertura de box-score (`has_advanced_stats==1`): 4.102 jogos (~41%)** — só recente e
  concentrada nas competições de elite (ver §3.3). Os modelos de contagem treinam nesse subconjunto.
- **Não há colunas de xG** no dataset (o xG existe no raw da API para ~41% dos jogos, mas nunca
  foi extraído; tentativas de usá-lo falharam — ver histórico).

### 3.2 Features (158 base + estilo/cascade)
- **`base_feats` (158)** usadas pelo Dixon-Coles: **Elo** (`home_elo_pre`, `elo_diff`,
  `elo_home_winprob` — domina tudo), descanso (`*_days_rest`), mando (`neutral`,
  `real_home_advantage`), H2H, streaks, e taxas **gf/ga/gd/ppg/winrate/csrate/ftsrate/bttsrate**
  em janelas l3/l5/l10 (home/away/diff), pesos de torneio, e **pace** (somas l10).
- Os modelos de contagem usam um conjunto maior (**~274 feats**): base + rolling de box-score
  (`sb_shots_l5`...) + **resíduos de estilo ortogonalizados** (`resid_*_style_*` via
  `style_ortho_weights.joblib`, removendo o que o Elo já explica) + **cascade** (finalizações
  previstas `pred_*_shots` + interações de mando `rha_x_*`).
- **Regra de ouro:** toda feature é **point-in-time** (`shift(1)`, só dados pré-jogo) — sem leakage.

### 3.3 Cobertura de box-score por competição (por que a contagem só usa ~41%)
Quase perfeita (>90% utilizável) em **Copa do Mundo, Euro, Copa América, Nations League,
Eliminatórias UEFA/CONMEBOL**; baixa/nula em amistosos (~22%), eliminatórias africanas/asiáticas
antigas e torneios regionais (COSAFA, Gulf Cup etc.). É por isso que features dependentes de
box-score (e xG) não generalizam para seleções fora da elite.

### 3.4 Tabelas no Neon (produção lê)
`matches` (forma/histórico), `features_enriched` (treino), `fixture_index`, `past_fixtures`
(seletor), `referees`/`team_ids`, `odds_registry` (jogos futuros + snapshot de previsão),
`match_detail_cache` (detalhe sob demanda). `data/` local é **gitignored** e não existe no Render.

### 3.5 Coletas (máquina local, Windows Task Scheduler → Neon)
- **`CollectOdds`** (3/3h): odds de consenso + snapshot da previsão (destrava backtest de valor).
- **`CollectResolved`** (diária): resolve jogos disputados (mantém a forma atual).
- **`CollectPlayerForm`** (diária): forma de clube/lesões dos convocados — **EXPERIMENTAL**, não
  em produção; aponta para caminho pré-monorepo (`api/.venv`) e pode estar quebrada (inócua, a
  coleta já está completa). Cota API ~75k/dia.

---

## 4. Modelos em produção

| Mercado | Artefato (`backend/model_artifacts/`) | Modelo |
|---|---|---|
| Resultado / Gols / BTTS / Over 2.5 / Placar | `dixon_coles_goals.joblib` | **Dixon-Coles NB** (matriz conjunta) |
| Escanteios | `corners_cascade_rfixo.joblib` | **NB** r-fixo (r_H=10, r_A=8.5) + cascade |
| Finalizações | `shots_nb.joblib` | **NB** (r≈18) + time-decay H=2 |
| Finalizações a gol | `shots_on_target_nb.joblib` | **NB** |
| Cartões | `cards_gp.joblib` | **Generalized Poisson** |
| Gols/Cartões 1º/2º tempo | `gols_1t/2t_nb`, `cartoes_1t/2t_nb` | **NB** |
| **Calibração O/U** (novo 2026-06-30) | `ou_calibrators.joblib` | **Isotônico** p/ escanteios/a-gol/cartões |
| Apoio | `style_ortho_weights.joblib`, `meta.json` | ortogonalização de estilo + metadados |

**Legado em disco, NÃO servido:** `dynamic_corners_nb` (REPROVADO), `corners_nb`, `cards_nb`,
`clf_result/btts/over25`, `quantile_models` (todos substituídos).

### 4.1 Dixon-Coles NB — por que esse modelo
`dixon_coles_model.py`. **λ_home e μ_away** são estimados por **GradientBoostingRegressor do
sklearn** (100 árvores, profundidade 3, lr 0.05) sobre as 158 features — um regressor para casa,
outro para fora, cada um vendo todas as features. As marginais são **Binomial-Negativa**
(dispersão r_H, r_A) com a **correção Dixon-Coles `rho`** (≈−0.046) nas células de placar baixo
(0-0/0-1/1-0/1-1), tudo ajustado por **máxima verossimilhança**. Da matriz conjunta normalizada
saem coerentemente todos os mercados de resultado.
- **Por quê:** o futebol de seleções é dominado por **força relativa** (Elo) e tem **correlação
  conhecida nos placares baixos** (empates 0-0/1-1 mais frequentes do que a independência prevê);
  o Dixon-Coles modela exatamente isso. O GBM captura interações não-lineares entre as 158 features
  melhor que um modelo log-linear. Para gols, o `r` da NB colapsou em região quase-Poisson (r>100)
  → o ganho vem do **acoplamento DC**, não da sobredispersão.

### 4.2 Mercados de contagem — NB/GP em cascata — por que
- **Negative Binomial (NB)** para finalizações, a-gol e escanteios porque essas contagens são
  **sobredispersas de verdade** (variância > média; r≈18-21). A Poisson (variância=média)
  subestimaria a incerteza e descalibraria as caudas.
- **Generalized Poisson (GP)** para cartões: contagem baixa (média ~2-3) onde a NB e a GP empatam;
  a GP foi escolhida por melhor cobertura de cauda. (Honestamente: cartões **não têm
  sobredispersão real** — o `r` da NB colapsa em ~1000 = Poisson; o ganho vem de usar uma
  distribuição de **contagem própria** em vez da Normal, não da sobredispersão.)
- **Cascade:** finalizações são previstas primeiro e entram como feature de escanteios e cartões
  (a permutação confirma: `pred_shots` é a 2ª/3ª feature mais importante em escanteios e a 1ª em
  cartões). Estilo ortogonalizado (PPDA de pressing) também sobrevive como sinal.
- **Time-decay** (peso 0.5^(Δdias/H)) foi testado em todos os alvos e **só ajudou finalizações**
  (H=2: viés temporal −0.80→−0.31, ECE 5.6%→2.5%). Em gols o viés é estrutural (invariante ao
  decay); em escanteios/cartões o viés já era ~zero.

---

## 5. Métricas — o que são e por que usamos cada uma

O sistema é avaliado por **qualidade probabilística**, não por "acertou/errou". Um modelo que
diz "60% de vitória" e o time perde **não errou** — só não era certeza. As métricas medem se as
probabilidades são **honestas e bem calibradas**.

- **Log-loss (entropia cruzada)** — penaliza a probabilidade que o modelo deu ao que **de fato
  aconteceu**: `−log(p_observado)`. Diz "70% Over" e deu Over → custo baixo; diz "95% Over" e deu
  Under → custo altíssimo. **Por quê:** pune **excesso de confiança errado** com força, que é
  exatamente o erro caro em aposta. É a métrica **primária** de todos os mercados.
- **ECE (Expected Calibration Error)** — mede **calibração**: agrupa as previsões por faixa de
  probabilidade e compara "o que o modelo disse" com "a frequência real". Se em todos os jogos
  onde disse ~70% o Over saiu ~70% das vezes, ECE≈0. **Por quê:** log-loss baixo não garante que
  "70%" signifique 70% na prática; o ECE é o que valida que as **odds justas** são confiáveis.
  (Reportamos em %; produção fica em ~2-4%.)
- **Bernoulli log-loss** — o log-loss específico de um mercado binário (uma linha Over/Under).
  Usado na validação da calibração O/U.
- **Brier score** — erro quadrático médio entre probabilidade e desfecho (0/1). Alternativa ao
  log-loss, menos sensível a previsões extremas; usado como métrica secundária de calibração.
- **MAE / RMSE** — erro absoluto/quadrático médio da **estimativa pontual** de contagem (ex.:
  "esperado 9.3 escanteios"). **Por quê:** complementa as métricas probabilísticas com uma noção
  intuitiva de "quão longe a média ficou".
- **Cobertura de intervalo (80%)** — fração das vezes em que o valor real caiu dentro do intervalo
  de 80% previsto. Deve ficar perto de 80% (bem calibrado). **Por quê:** valida que a **largura**
  da distribuição (a incerteza) está correta, não só o centro.
- **Tail-ECE** — ECE restrito às **caudas** (linhas extremas, ex. Over 11.5 escanteios). **Por
  quê:** foi o que reprovou o modelo de dispersão dinâmica (caudas estreitas demais); apostas em
  linhas extremas exigem caudas honestas.
- **Estabilidade walk-forward** — o ganho tem de aparecer **em vários cortes temporais
  sucessivos** (treina no passado, testa no futuro), não num único split. **Por quê:** evita
  promover ruído (foi assim que descobrimos que ganhos de CV aleatória eram falsos).
- **RPS (Ranked Probability Score)** e **ROI/yield** — ainda **não** computados em produção (RPS é
  trivial de adicionar; ROI depende de acumular odds de fechamento — ver §9).

**Por que essas e não "acurácia":** acurácia ignora a confiança. Em mercados de aposta o que
importa é se a probabilidade bate com a frequência real (calibração) e se o modelo não erra com
excesso de confiança (log-loss). Por isso o **gate de promoção** exige reduzir log-loss **sem
piorar ECE**, de forma **consistente em folds e segmentos**.

---

## 6. Protocolo de validação (o gate)

Padrão obrigatório para promover qualquer mudança:
1. **CV temporal expanding** (treina no passado, testa no bloco seguinte; cortes ~0.50→0.85),
   seed=42. (CV **aleatória** superestima ganhos — proibida para veredito.)
2. **Point-in-time**: só features pré-jogo; ortogonalização/residualização **ajustada por fold**.
3. **Métrica nativa**: contagem → log-loss da PMF + ECE da linha O/U + MAE; resultado → log-loss
   multiclasse + ECE + acurácia; + Brier nos binários.
4. **Comparar contra a PRODUÇÃO REAL** (NB/GP/DC-NB), nunca contra um baseline strawman (ex.: Poisson).
5. **Segmentar sempre**: equilíbrio (|elo|≤80 / 80–150 / >150), competição, continente, cobertura.
6. **Gate**: reduzir log-loss + não piorar ECE + passar CV temporal + sem leakage + sem degradar
   inferência — **consistente em folds E segmentos**. Senão, **não promover**.

---

## 7. Estado de produção (resumo)
Pipeline **robusto e bem calibrado** (ECE de resultado ~3%, contagem ~2-4%). O Elo satura o
resultado; o `base_feats`+cascade satura a contagem. **A única melhora promovida nas últimas
baterias foi a calibração isotônica das linhas O/U** (2026-06-30). Tudo o mais testado foi
medição que confirmou a robustez do que já existe.

---

## 8. Histórico de desenvolvimento (cronológico, com achados e veredito)

### Fase 0 — Migração de dataset (StatsBomb → API-Football)
Recalibração do Elo (K-factors reais por torneio + multiplicador de margem de vitória → divergência
de Elo <46 para seleções FIFA) e correção de um bug de merge no gamelog (pares válidos saltaram de
48 para 9.958, correlação >0.9999 vs base original). Base de box-score expandida de **242 → 4.102**
jogos. **Veredito:** modelo base equivalente ou ligeiramente melhor em resultado; **ganhos grandes**
em contagem (finalizações MAE 6.15→4.99, cobertura 80% de 69%→79%). API-Football adotada.

### Fase 1 — Migração quantílica → distribuições de contagem próprias
Os mercados de contagem usavam regressão quantílica + aproximação Normal (péssima para contagem
baixa). Migrados para distribuições próprias, **cada um validado vs a quantílica**:
- **Escanteios → NB independente** (r_H=18.2, r_A=16.7). Sobredispersão real confirmada. A
  **bivariada acoplada** convergiu para β=−0.04 (correlação negativa real mas **fraca**) e **perdeu**
  no total (ECE 5.11% vs 2.75% da convolução independente) → **acoplamento aposentado**.
- **Cartões → contagem própria** (depois GP). Correlação entre lados **+0.07** (positiva, "jogo
  pegado cartoneia os dois", mas fraca → acoplada empatou). Achado honesto: `r`≈1000 → **cartões ≈
  Poisson** (sem sobredispersão); o ganho vem da distribuição própria vs Normal.
- **Finalizações → NB + time-decay H=2** (r≈18). Único alvo onde o decay ajudou (viés −0.80→−0.31).
- **Veredito:** todas batem a quantílica em log-loss e ECE; promovidas. Casas não oferecem odds de
  chutes → fora do value betting, mas exibido.

### Fase 2 — Dixon-Coles NB para resultado/gols
Substituiu classificadores binários por uma **matriz conjunta**. Resultado **log-loss 0.874→0.830,
ECE 7.57%→3.16%**. O ganho vem do **acoplamento DC**, não da NB (r de gols colapsou em quase-Poisson).
**Veredito:** promovido; serve resultado/gols/BTTS/over/placar de forma coerente.

### Fase 3 — Features e regressores testados (gate walk-forward)
- **PACE** (somas l10 de gf/ga): **único grupo de features que passou** (BTTS 8/9 janelas) → **EM
  PRODUÇÃO**. Reprovados: forma por mando, SoS-Elo, momentum, EWMA, interações explícitas (instáveis).
- **Regressor de λ (XGBoost/LightGBM/HistGBM)**: 9 configs × 8 janelas × 4 mercados — **nenhum bate o
  sklearn GBM** (boosters potentes overfitam). Janela fechada.
- **Calibração post-hoc do BTTS / resultado** (Platt/isotônica/temperatura): **piora** (DC já calibrado).
- **xG como feature, time-decay em gols, peso de competição, confiabilidade de rating, remover
  martj42**: todos reprovados (muro de dados do xG; viés de gols estrutural; manter martj42 evita
  ~80% da perda irredutível).

### Fase 4 — Dispersão dinâmica de escanteios (DynamicCornersNB) — REPROVADO
Tentou parametrizar a dispersão r jogo-a-jogo (GAMLSS-style, MLE em dois estágios). Passou MAE/log-loss
mas **reprovou Tail-ECE** (Over 8.5 = 13.9%/22.4% vs limite 4%; Over 11.5 = 3.4% vs 2.5%). O MLE
estreitou a cauda para maximizar a verossimilhança do corpo, subestimando eventos raros. **Rollback**
para o NB r-fixo (r_H=10, r_A=8.5), que minimiza ECE diretamente. (Detalhe técnico preservado no commit.)
> **Nota:** o problema que ele tentou resolver (calibração de cauda dos escanteios) foi **resolvido
> em 2026-06-30 por outro caminho** — calibração isotônica post-hoc da prob. O/U (ver abaixo).

### Fase 5 — Player ranking / forma de jogador
- **Ranking de temporada** (força via clube dos convocados, agregado): **redundante com o Elo**
  (corr +0.55..+0.72), gate falhou. Aposentado.
- **Forma-por-jogo** (point-in-time, 2.123 jogos: rating de clube, minutos, fadiga, momentum,
  xG-clube, disponibilidade/lesões via `/sidelined`): coleta concluída. Testada exaustivamente
  (relatórios 1, 3, 4) — ver abaixo.

### Fase 6 — Baterias de validação 2026-06-29 (relatórios 1–3)
- **Relatório 1** (forma no resultado, CV **aleatória**): ganho **minúsculo** (−0.001 a −0.006
  log-loss), maior em jogos equilibrados/alta cobertura, com rating-residual e momentum. *Caveat:
  CV aleatória.*
- **Relatório 2** (contagem do zero): NB/GP **>> Poisson** em finalizações/escanteios. *Caveat: o
  Poisson do experimento NÃO é a produção.*
- **Relatório 3** (promoção sob gate, **CV temporal** — o veredito que vale): premissa corrigida (a
  produção já é NB/GP/DC-NB). **GP não bate a NB de produção** (empate/ruído por segmento). **Forma
  no resultado REPROVA** sob CV temporal (o ganho do rel. 1 era artefato de CV aleatória).
  **Calibração** pós-hoc piora. **Posse/passes/faltas** inconsistente. **Árbitro** não ajuda
  (amostra rasa por árbitro em seleções). **Promovido: NADA.**

### Fase 7 — Os 6 próximos passos 2026-06-30 (relatório 4)
Executados sob gate temporal. **Nada promovido:**
- **xG de clube** (além do base_feats): ganho só em finalizações, **~7× menor que o ruído** entre
  folds. Resultado inconsistente. Não passa.
- **Forma como blend de cobertura no resultado**: sinal "âmbar" no proxy HGB (melhora 3 segmentos),
  mas **decai por fold** e some no fold mais recente. → follow-up: testar no DC real.
- **Feature importance dos modelos de PRODUÇÃO** (permutação sobre os artefatos deployados): **elo
  (`elo_home_winprob`) domina tudo** (#1 em finalizações, a-gol, escanteios e DC-resultado); o
  **cascade finalizações→escanteios é real** (`pred_shots` top em escanteios e #1 em cartões); PPDA
  de estilo sobrevive; **cartões** é o mercado menos guiado por elo (mais idiossincrático).
- **Exp 3 cadeia de regressão** (posse→finalizações→escanteios→gols): ΔLL≈0 (o base_feats já tem o
  histórico rolante). **Exp 4 cópula bivariada**: dependência pequena (gols/cartões +, escanteios
  −0.17/finalizações −0.09, confirma β≈−0.04), sem ganho no total. **Exp 5 ataque×defesa→λ**
  (força pura estilo DC): **pior** que GBR+features em tudo (+0.03 a +0.18).

### Fase 8 — Calibração O/U + fechamento da forma 2026-06-30 (relatório 5) — **MELHORA PROMOVIDA**
- **Forma blendada no Dixon-Coles REAL** (não proxy): dLL −0.0006, ECE pior; **forma no resultado
  encerrada** — o sinal âmbar era artefato da família HGB; o DC já extrai o sinal.
- **Calibração isotônica das linhas O/U do total dos mercados de contagem** (validada por
  walk-forward expanding, ajustando o calibrador no passado e avaliando no futuro):

  | Mercado | ECE (cru→calibrado) | ΔBernoulli-LL | Folds que melhoram | Veredito |
  |---|---|---|---|---|
  | **Escanteios** | 4.5% → **2.8%** | −0.0072 | **4/4** | ✅ **Promovido** |
  | **Finalizações a gol** | 3.0% → **2.5%** | −0.0029 | 3/4 (recente ✓) | ✅ **Promovido** |
  | **Cartões** | 2.8% → **2.1%** | −0.0017 | 2/4 (recente ✓) | ✅ **Promovido** |
  | Finalizações (chutes) | 6.3% → 7.5% | +0.0015 | 1/4 | ❌ Excluído (piora) |

  **Por que isotônico:** a miscalibração de cauda da NB/GP é uma curva monótona irregular, não uma
  rotação logística — o isotônico é a recalibração monótona livre que a captura, preservando a
  ordenação entre linhas. Platt/temperatura não capturaram (já reprovados no resultado).
  **Integração:** `ou_calibrators.joblib` + `predictor._corners_market(calibrator=)`; aplicado **só
  ao TOTAL** validado (não a mandante/visitante nem a chutes); distribuição/estimativa seguem da PMF
  crua; linhas O/U marcadas com `"calibrado": true`; retrocompatível (sem o artefato = comportamento
  antigo). É a **primeira melhora aprovada desde o início das baterias de validação**.

**Meta-conclusão:** os modelos estão no teto in-sample — o Elo domina e quase tudo que se tenta é
redundante com ele. O ganho real veio de **calibrar** (não de novas features). Salto maior de
qualidade exigiria **dados de outra natureza** (tracking/xG denso) ou o **backtest de odds ao vivo**
como árbitro empírico de valor.

---

## 9. Janelas de oportunidade abertas (onde há retorno)
1. **Backtest financeiro (ROI/yield) + RPS** — a validação que mais falta. Hoje só temos log-loss/
   ECE/Brier; ROI exige acumular odds de **fechamento** × resultados (coletor de odds é recente,
   poucos snapshots). Deixar `CollectOdds` rodando e usar `value_backtest.py`. **Maior prioridade.**
2. ~~**Estender a calibração isotônica**~~ — **FEITO 2026-07-06.** Avaliados mandante/visitante e
   meio-tempo sob o mesmo gate walk-forward. **Promovidos (4/4 folds cada):** escanteios-mandante,
   gols_1t-total, gols_2t-total, cartões_1t (total+mandante+visitante), cartões_2t (total+mandante+
   visitante) — maior ganho em cartões de meio-tempo (ex.: cartões_1t-visitante ECE 6,8%→2,7%).
   Reprovados (BLL piora/inconsistente): escanteios-visitante, a-gol e finalizações por lado, gols
   de meio-tempo por lado. `ou_calibrators.joblib` agora tem 12 chaves `<mercado>_<home|away|total>`;
   `predictor._half(prefix)` aplica por lado. Chutes segue fora.
3. **xG denso / dados de tracking** (fora da API-Football) — única fonte plausível de sinal novo
   ortogonal ao Elo; o xG da API é esparso demais (~6%, só elite/2024).
4. **Ratings dinâmicos** (Dixon-Coles dinâmico / filtro de Kalman de força ataque-defesa evoluindo no
   tempo) — maior esforço, potencial incerto para placar exato.

**Já testado e fechado (não repetir):** GP vs NB de produção; forma de jogador no resultado;
calibração post-hoc do resultado; posse/passes/faltas; árbitro; XGBoost/LightGBM no λ; cadeia de
regressão; cópula bivariada; ataque×defesa força-pura; dispersão dinâmica de escanteios; time-decay
fora de finalizações; remover martj42; **prop "jogador a levar cartão"** (2026-07-08,
`scripts/test_player_cards.py`): bem calibrado (ECE 0,6%) e bate a taxa-base 4/4, mas **AUC 0,62**
(base 0,59) — muito abaixo do padrão do goleador (~0,74). Cartão de jogador é idiossincrático
(árbitro desconhecido pré-jogo + faltas aleatórias). **Não promovido** — não vale abrir o mercado.

> **Padrão dos props de jogador (2026-07-09):** ações **OFENSIVAS** (gols, finalizações) são
> **previsíveis** (AUC 0,74–0,77) porque refletem o papel no ataque, que é estável → **construídas
> (goleador + finalizações)**. Ações **defensivas/disciplinares** (cartões AUC 0,62; **faltas AUC
> 0,58** — `scripts/test_player_fouls.py`; assistência 0,64) são **aleatórias jogo-a-jogo → não
> passam**. O espaço de props de jogador está **exaurido**: só valem os ofensivos, já em produção.

---

## 10. Como rodar / reproduzir
```bash
cd backend
# subir API:      .venv/Scripts/python -m uvicorn app.main:app --port 8000
# (raiz) front+back: npm run dev

# experimentos sob gate temporal (resumíveis; CSVs em data/reports/, gitignored):
.venv/Scripts/python scripts/promotion_validation.py          # GP vs NB de producao
.venv/Scripts/python scripts/result_forma_validation.py       # forma no resultado
.venv/Scripts/python scripts/xg_club_experiment.py            # xG de clube
.venv/Scripts/python scripts/forma_dc_blend.py                # forma blendada no DC real
.venv/Scripts/python scripts/exp3_chain.py                    # cadeia de regressao
.venv/Scripts/python scripts/exp4_copula.py                   # copula bivariada
.venv/Scripts/python scripts/exp5_attack_defense.py           # ataque x defesa -> lambda
.venv/Scripts/python scripts/feature_importance_prod.py       # importancia dos modelos deployados
.venv/Scripts/python scripts/count_calibration_walkforward.py # calibracao O/U (validacao)
.venv/Scripts/python scripts/build_ou_calibrators.py          # gera ou_calibrators.joblib
```
Re-treino do DC após validar uma feature: `scripts/retrain_dc_pace.py` (cirúrgico; os scripts
`train_*_apifootball.py` têm caminhos pré-monorepo quebrados).

---

## 11. Gotchas (aprendidos)
- **CORS↔500:** uma exceção 500 no FastAPI não leva header CORS → o browser mascara como "erro de
  CORS". Se CORS aparece só num endpoint, é 500 nele. (Foi como descobrimos `requests` ausente no
  Render → trocado por `httpx`.)
- `truncate_and_append` preserva schema → **coluna nova no Neon exige DROP da tabela** uma vez.
- `pandas==3.0.3` exige **SQLAlchemy ≥ 2.0.36** (senão `to_sql` quebra).
- Ordem de `base_feats` deve ser idêntica treino↔`meta.json` (append no fim).
- Modelos picklados (`shots_nb_model`, `corners_nb_model`...) ficam na **raiz do backend** — scripts
  em `scripts/` precisam de `sys.path.insert(0, backend_root)` para `joblib.load`.
- Console Windows é cp1252 — evitar caracteres Unicode (Δ, →) em `print` de scripts.
- Jobs em background morrem no teardown de sessão → fazer scripts **resumíveis** (checkpoint).
- `nbinom.ppf` é lento para r alto; amostrar via **CDF em grade + searchsorted**.
- Coletores de longa duração (>100min) derrubam a conexão do pooler do Neon
  ("server closed the connection unexpectedly") perto do fim — não perde dado
  (cache-first, resumível), mas é esperado ver esse erro em prefetches muito
  longos; não é bug do coletor.
- Controle negativo (rótulos embaralhados) por **acurácia** contra "acaso
  uniforme" (1/N classes) é **errado** quando há desequilíbrio de classe real
  (ex.: 1x2 tem H≈45% por vantagem de mandante, não 33%) — compare contra o
  baseline **constante** (prever sempre a frequência de classe do treino), não
  contra o acaso uniforme, senão vazamento falso-positivo (ver §19).

---

## 12. Camada de Usuários / Monetização (2026-07)

Além do motor de previsão, o produto ganhou uma **camada completa de usuários, créditos,
seleções promocionais e administração**, construída na branch `feat/monetizacao` (mergeada na
`main`). O motor de previsão e seus modelos **não mudaram** (só ganharam a calibração O/U já
descrita e a odd mínima 1.00 na exibição).

### 12.1 O que existe
Backend **modular por domínio** (`backend/app/domains/*`), ORM 2.0 + **Alembic** (só tabelas
`app_*`, isoladas do pipeline de dados), **36 tabelas** já criadas no Neon (23 originais + 13 da
monetização de conversão, §12.7). Fluxo completo:
```
cadastro→OTP→senha→login  →  compra de créditos  →  análise (consome/reserva 1 crédito)
   →  "Monte sua Seleção" (odd ≤2,00, auto ~2,00, imutável)  →  processamento resultado
      (validada: consome o crédito · não validada/anulada: estorna)  —  Painel Admin gerindo tudo
```
- **Auth:** argon2, JWT de acesso + refresh rotativo, **OTP por e-mail real (ZeptoMail/Zoho)**,
  CPF (dígitos verificadores) + telefone, rate limiting, lockout, auditoria.
- **Carteira:** ledger de créditos (saldo só via lançamento, idempotência), disponível/reservado.
- **Pagamentos:** gateway abstrato — **Mercado Pago (Checkout Pro) implementado** (branch
  `monetization`, §12.7), mock segue disponível para dev; webhooks idempotentes com verificação de
  assinatura HMAC. 1 crédito = R$1,00. Cupons de desconto/bônus e comissão de afiliado aplicados no
  checkout, independentes entre si.
- **Análise:** grava **snapshot imutável** + versão do algoritmo/dados; independente consome 1
  crédito, partida futura reserva 1.
- **Seleção ("Monte sua Seleção"):** combina mercados da análise (O/U em colunas Acima/Abaixo),
  odd combinada **≤ 2,00**, **auto-seleção ~2,00** se o usuário não escolher, imutável.
- **Liquidação:** worker `scripts/settle_bets.py` / `POST /api/cron/settle-bets` — pós-jogo via
  API-Football, consome (validada) ou estorna (não validada/indeterminável) — promoção "Só Paga se Acertar".
- **Admin (backend + UI):** usuários (bloquear, creditar), financeiro, promoções, **cupons,
  pacotes, afiliados, banners, configurações, suporte** (§12.7), documentos legais versionados,
  **auditoria completa**.
- **Afiliados, campanhas, analytics, notificações, suporte** (§12.7): domínios novos da
  monetização de conversão.
- **Frontend:** página única **Análise** (`/`) com config → gerar (crédito) → previsão completa →
  **Construção da Seleção** (Monte sua Seleção + Explorador de Linha + Value Betting/De-Vig);
  `/carteira` (redesenhada, §12.7), `/perfil`, `/admin`, `/afiliado` (portal), `/documentos/[type]`,
  **`/como-funciona`** (doc interativo). Persistência da análise no `PredictionContext` (não some
  ao navegar). Auth no `AuthContext`.

### 12.2 Estado dos adapters (importante)
- **E-mail OTP:** adapter **real implementado** (2026-07-08, commit `e517740`) —
  `EMAIL_PROVIDER` = `mock` | `zeptomail` | `smtp`. **ZeptoMail** (transacional da Zoho) é o
  provedor de produção; SMTP do Zoho Mail é o fallback. Em dev o default segue `mock` (OTP no
  console). Desenho completo em **`ARCHITECTURE.md` §6**.
  - Provider desconhecido ou credencial ausente **levanta erro** em vez de cair em mock.
  - Falha de envio → **HTTP 502 + rollback** (nenhum usuário órfão); ver §6.2 do `ARCHITECTURE.md`.
  - `APP_ENV=production` faz o backend **recusar o boot** com config de e-mail/JWT inválida.
  - Validar antes de expor a usuários: `cd backend && python -m scripts.send_test_email voce@dominio.com`.
- **Gateway de pagamento:** adapter **Mercado Pago implementado** (`payments/gateways/
  mercadopago.py`, branch `monetization`) — falta só `MP_ACCESS_TOKEN`/`MP_WEBHOOK_SECRET` reais e
  `PAYMENT_PROVIDER=mercadopago` para sair do mock. `POST /payments/mock/confirm/{id}` continua
  disponível, mas só funciona quando `PAYMENT_PROVIDER=mock` (guarda de segurança). Ver §12.7.
- **Nota fiscal:** adapter **noop** (`payments/invoicing.py`) — marca `invoice_status="pending"`
  sem emitir nada; trocar por NFE.io/Focus NFe quando decidido com o contador. **Emissão automática
  mantida para toda venda paga** (best-effort); desde 2026-07-13 a **exibição ao cliente é sob
  demanda** (`invoice_requested_at` + botão "Solicitar nota fiscal" na Carteira) — ver §12.8.

### 12.3 Onde está a documentação
- Desenho/arquitetura da camada: **`docs/ARQUITETURA_MONETIZACAO.md`**.
- Infra/deploy/env: **`ARCHITECTURE.md` §5**.
- **E-mail transacional (Zoho/ZeptoMail):** **`ARCHITECTURE.md` §6** — adapters, o porquê do 502
  com rollback, validação de boot, env vars e scripts de verificação.
- Estado atual + próximos passos (handoff vivo): **`ESTADO_ATUAL_E_PROXIMOS_PASSOS.md`** (raiz).

### 12.4 Integração com a Zoho (2026-07-08)
Decidido: **Zoho entra como cliente de e-mail, não como repositório de dados.** O ledger de
créditos (`app_credit_transactions`) depende de transação multi-registro e de `idempotency_key`
com unicidade atômica — garantias que uma API REST de CRM/Creator não oferece; movê-lo para lá
abriria caminho para gasto duplicado de crédito. O Postgres/Neon segue como system of record
transacional.

Envio de OTP: implementado (commit `e517740`), verificado contra um ZeptoMail simulado e
**confirmado em produção em 2026-07-08** — cadastro real concluído no site com o código chegando
por e-mail. Recebimento de e-mail: **não implementado**, decisão pendente (caixa no Zoho Mail é
configuração; leitura programática exigiria IMAP ou Zoho Mail API com OAuth2).

### 12.5 Sessão 2026-07-08 (parte 2) — UX da Análise + regras de crédito/seleção
Produção agora em **`apostainfo.com.br`**; cadastro por e-mail (ZeptoMail) **funcional**.

- **Bônus de boas-vindas:** toda conta nova nasce com **8 créditos grátis** — lançamento `bonus`
  no ledger na ativação (`auth/service.py::set_password`), idempotente por conta
  (`welcome-bonus:<user_id>`). Verificado no `verify_signup_flow`.
- **Persistência da análise (bug corrigido):** o `PredictionContext` agora persiste em
  `localStorage` (`apostai:prediction:v1`) — a análise sobrevive a **reload cheio**, não só à
  navegação client-side. Antes um F5/remontagem zerava a análise e forçava gasto de outro crédito.
- **Seleção — palpites interdependentes bloqueados:** `bets/markets.py::base_market()` +
  `resolve_selections`/`auto_select` recusam duas seleções do **mesmo mercado-base** (ex.: Menos
  de 1,5 + Menos de 2,5 gols; duas linhas de escanteios/cartões), como as casas. Guarda no backend
  (autoritativa) + no `BetBuilder` (um por mercado-base no toggle).
- **"Jogador a levar cartão":** testado sob o gate (`scripts/test_player_cards.py`) e **reprovado**
  (AUC 0,62; ver §9). Mercado não aberto.
- **Redesign da página de Análise (frontend):** mercados secundários com **colapso individual**
  (título sempre visível); **"Jogador a Marcar" movido para dentro dos secundários**; cards de
  mercado com **só o nome da seleção, centralizado**; **Handicaps** com texto explicativo novo +
  cabeçalhos de coluna; **"Configuração do Confronto" recolhe** ao escolher a partida, com
  "Alterar Equipes" no cabeçalho flutuante; **FUNÇÕES AVANÇADAS acima do MONTE SUA SELEÇÃO**;
  **últimos 5 jogos em linhas** num bloco (Resumo do Confronto Direto à esquerda, equipes
  empilhadas à direita, mesma largura/altura).

### 12.6 Sessão 2026-07-09 — props de finalizações, cópula, Série A
Duas melhorias VALIDADAS foram promovidas, e a coleta de seleções saturou.

- **Mercado "Jogador a finalizar" (PROMOVIDO):** modelo de finalizações do jogador
  (`scripts/build_shots_prop_model.py` → `model_artifacts/shots_prop_model.joblib`): P(≥0,5/1,5/2,5
  finalizações | joga), calibrado. Validação temporal (linha ≥2): **AUC 0,773 (base 0,758), ECE
  1,06%, 4/4 folds** — no padrão do goleador. Serving em `app/services/shots_prop_service.py`;
  `get_scorers` anexa `finalizar` a cada jogador. Frontend: card **"Jogador"** com colunas
  **MARCAR | FINALIZAR (0,5/1,5/2,5)** separadas. Rebuild diário no `prefetch_wc.cmd`.
- **Cópula gaussiana na odd combinada (PROMOVIDO — EXP7/13/14):** `bets/markets.py::combined_odd`
  aplica a cópula às seleções ofensivas correlacionadas (gols/finalizações/a-gol/escanteios) —
  overs correlacionados têm odd combinada MENOR (mais justa/conservadora); demais mercados por
  independência. Σ = correlações residuais validadas, encolhidas. Ex.: over gols + over
  finalizações 3,60→3,20; over fin + over a-gol 3,61→2,71.
- **Fator Árbitro no modelo de cartões de EQUIPE (REPROVADO):** `scripts/exp15_referee_cards.py` —
  `ref_strictness` como feature dá dNLL +0,007 (3/7 folds), inconsistente. Cartão idiossincrático.
- **Coleta de seleções SATUROU:** o prefetch `--all-nations` parou por "tudo coberto" (todas as
  ~230 seleções, histórico 2010+). Sobra ~70k/75k de cota ociosa/dia. Por isso, conforme o foco,
  **começou a coleta do Campeonato Brasileiro Série A** (próxima adição) em tabela SEPARADA
  `serie_a_detail_cache` (`scripts/prefetch_serie_a.py`, anexado ao cron), sem contaminar os
  modelos de seleção.

### 12.7 Sessão 2026-07-11 — Monetização de conversão completa (7 fases), branch `monetization`

Objetivo: transformar a plataforma numa venda de créditos pronta para produção, com foco em
conversão (estilo e-commerce). Todas as 7 fases foram implementadas **reaproveitando** a
arquitetura existente (wallet ledger, `payment_orders`, `AdminAuditLog`) e testadas ponta a ponta
contra o Neon real — não é código não-verificado. Confirmado antes de implementar: o modelo é **só
consumo** (créditos gastos em análises, sem saque de dinheiro), o que evita a barreira de outorga
de apostas de quota fixa (Lei 14.790/2023) — a plataforma é ferramenta de análise paga por crédito,
não uma casa de apostas licenciada.

**Fase 1 — Gateway Mercado Pago real:** `payments/gateways/mercadopago.py` implementa o mesmo
`Protocol` do `MockGateway` (Checkout Pro — redirect, evita escopo de PCI compliance). Webhook
(`POST /payments/webhook/mercadopago`) valida assinatura HMAC (`x-signature`) contra
`MP_WEBHOOK_SECRET`; sem ela, a notificação é rejeitada. `confirm_mock` (usado só em dev) já era
gated por `payment_provider == "mock"` — nenhuma mudança necessária ali, mas o frontend foi
corrigido para só chamá-lo em modo mock; com gateway real, redireciona para o `init_point` do
Checkout Pro e faz polling do saldo ao voltar (`?status=success|pending|failure`).

**Fase 2 — Cupons + Carteira redesenhada:** `Coupon` (`app_coupons`) ganhou campos tipados
(`discount_type: percentage|fixed|bonus_credits`, `discount_value`, `bonus_credits`,
`min_purchase_brl`, `package_id`, `valid_from/valid_to`). Novo `promotions/service.py`:
`validate_coupon()` (preview, não incrementa uso) + `mark_redeemed()` (só quando o pagamento
confirma). `PaymentOrder` ganhou `coupon_id`. Carteira (`/carteira`) reorganizada: banner
promocional → pacotes com selos (`featured_badge`: mais_vendido/melhor_oferta/oferta_limitada) e
% de economia → campo de cupom → resumo de saldo → histórico. `CreditPackage` ganhou
`featured_badge`/`sort_order`.

**Fase 3 — Analytics:** domínio novo `analytics/` — tabela `app_events` (signup, login,
checkout_started, coupon_applied, credit_purchase, payment_failed, analysis_started/finished, etc.)
instrumentada inline nos services existentes (`auth`, `payments`, `analysis`), sem reescrever esses
fluxos. `GET /admin/analytics/dashboard` agrega faturamento hoje/mês/ano, ticket médio, receita por
pacote, créditos vendidos/promocionais/usados, funil de conversão, usuários ativos/pagantes — via
queries SQL diretas (padrão de `aggregates.py`), sem pipeline novo.

**Fase 4 — Afiliados + Portal + Campanhas:** domínio novo `affiliates/` — `Affiliate` (código,
comissão % ou fixa), `AffiliateAttribution` (clique/cadastro, janela de dias configurável via
`app_platform_settings`, chave `affiliate_attribution_days`), `AffiliateCommission` (calculada só
quando o pagamento confirma, hook em `_credit_if_paid`). **Cupom e afiliado são independentes**:
`PaymentOrder.coupon_id` (benefício ao usuário) e `affiliate_attribution_id` (comissão ao
influenciador) coexistem sem se afetar — um pedido pode ter os dois, um só, ou nenhum. Portal
próprio em `/afiliado` (link exclusivo, cliques, cadastros, compradores, faturamento, comissão
devida/paga). Domínio novo `campaigns/` — `Campaign` (banner+pacotes+cupons+afiliados+prioridade,
entidade guarda-chuva para não espalhar configuração de promoção entre módulos) + scaffold de A/B
testing (`Experiment`/`ExperimentVariant`, `assign_variant()` determinístico por hash de
`user_id`+`experiment_key` — mesmo usuário sempre cai na mesma variante).

**Fase 5 — Painel admin expandido:** `frontend/src/app/admin/page.tsx` ganhou 6 abas novas
(Dashboard, Cupons, Pacotes, Afiliados, Banners, Configurações), além das 4 que já existiam
(Usuários, Financeiro, Promoções, Auditoria). Endpoints admin novos delegam para os services dos
domínios novos, sem duplicar regra de negócio (`app/domains/admin/service.py`).

**Fase 6 — Histórico, PIX pendente, notificações, suporte:** `GET /wallet/transactions` ganhou
filtros (`type`/`status`/`since`/`until`). `PaymentOrder.raw_payload` agora persiste o checkout
(init_point/QR) na criação do pedido — antes só era gravado na confirmação, o que impedia
recuperar um PIX pendente; `GET /payments/orders/pending` alimenta o banner "Continuar pagamento"
na Carteira, `GET /payments/orders` alimenta "Minhas compras". Domínios novos `notifications/`
(`app_notifications`, disparada automaticamente em `payment_approved`) e `support/`
(`app_support_tickets`, `POST /support/tickets` + CRUD admin).

**Fase 7 — Nota fiscal, recomendação, A/B, UX:** `payments/invoicing.py` — `NoopInvoiceProvider`
roda após todo pagamento confirmado (best-effort, nunca bloqueia a liberação do crédito), marca
`invoice_status="pending"`; trocar por adapter real (NFE.io/Focus NFe/Asaas) é troca de classe, sem
mexer no fluxo de pagamento. `recommend_package()` em `payments/service.py` — heurística (não-ML):
consumo médio dos últimos 90 dias → pacote mais próximo; sem histórico, sugere o de maior % de
bônus. `GET /campaigns/experiments/{key}/variant` expõe `assign_variant()` para o frontend.

**Migrations aplicadas no Neon** (nesta ordem): `7a1f3c9e2b40` (cupons/pacotes/pedidos),
`9c2e5a7b1d33` (`app_events`), `3f7d9b2c4e11` (afiliados+campanhas, 9 tabelas),
`5e8a1f4c7d22` (notificações+suporte). Total: **+13 tabelas `app_*`** (23→36).

**O que falta para vender de verdade** — não é código, são decisões/credenciais do dono:
credenciais reais do Mercado Pago, deploy + migração em produção, revisão jurídica dos
documentos legais (ainda são templates), decisão do emissor de nota fiscal com o contador. Detalhe
completo em `ESTADO_ATUAL_E_PROXIMOS_PASSOS.md` §2.1.

### 12.8 Sessão 2026-07-13 — merge da `monetization` na `main` + nota fiscal sob demanda

**Merge:** a branch `monetization` e a `main` compartilhavam o mesmo merge-base — a branch era
literalmente `main` + os 3 commits da §12.7 (mais o throttle de coleta `13a6954`). Fast-forward
puro, sem conflitos, com push para `origin/main`. A partir daqui, tudo descrito em §12.7 está na
`main` — só falta **deploy** (Render/Vercel) e rodar `alembic upgrade head` em produção.

**Nota fiscal sob demanda:** o dono pediu para o cliente só ver/receber a nota quando pedir
explicitamente, em vez de expor automaticamente para toda compra. Decisão de arquitetura adotada
(mais segura do ponto de vista fiscal): a emissão em si **continua automática** em
`_credit_if_paid` (best-effort, via `issue_invoice`) — o documento fiscal existe para 100% das
vendas, evitando faturamento sem nota. O que passou a ser sob demanda é só a **exposição ao
cliente**: nova coluna `app_payment_orders.invoice_requested_at` (migração `b4d6e1f8a9c2`), novo
`payments/service.py::request_invoice()` (idempotente — marca o pedido do cliente e tenta emitir
de novo se ainda não `issued`), rota `POST /payments/orders/{id}/request-invoice`, e botão
"Solicitar nota fiscal" na Carteira (`carteira/page.tsx`) que só aparece para pedidos pagos sem
`invoice_requested_at`.

Por quê essa decisão e não emissão 100% sob demanda: no Brasil, a obrigação de emitir NFS-e por
venda de serviço normalmente **independe** de o cliente pedir uma cópia — a prefeitura em geral
exige o documento para toda venda concluída, para fins de ISS/declaração de faturamento. "Só
emitir se o cliente pedir" arriscaria configurar faturamento sem nota fiscal para o resto das
vendas. Um texto foi preparado e enviado ao contador do dono para confirmar isso especificamente
para o município/CNAE dele — se ele confirmar que dá para declarar por outra via, a mudança para
emissão 100% sob demanda é trivial (só mover a chamada de `issue_invoice()` de `_credit_if_paid`
para dentro do `request_invoice()`).

**Fora de escopo (deliberado):** escolha do emissor real (NFE.io vs Focus NFe) — aguardando
resposta do contador sobre CNAE/Fator R/regime tributário (sócio único, sem funcionários CLT,
pró-labore conta para o Fator R). `NoopInvoiceProvider` segue em uso.

### 12.9 Sessão 2026-07-16 — Mercado Pago real + nota fiscal automática (NFE.io)

O dono decidiu o emissor (**NFE.io**) e já tem todos os dados fiscais. Código implementado e
testado (sem gastar dinheiro/nota real); falta só o runbook manual do dono (credenciais/painéis)
e `alembic upgrade head` em produção.

**Mercado Pago:** nenhuma mudança de código no gateway (já estava pronto). Único código novo:
`startup.py::_payment_problems()` — guarda de boot fatal em produção se `PAYMENT_PROVIDER=
mercadopago` e faltar `MP_ACCESS_TOKEN`/`MP_PUBLIC_KEY`/`MP_WEBHOOK_SECRET` (mesmo padrão do
e-mail). Runbook do dono: Render → env vars de produção (painel MP → Developers → Credenciais de
produção) + configurar o webhook no painel MP apontando para
`/payments/webhook/mercadopago` → copiar o segredo de assinatura para `MP_WEBHOOK_SECRET`.

**Nota fiscal (NFE.io):** construído do zero (não existia adapter nenhum):
- `payments/invoicing.py` — `InvoiceProvider` expandido (`customer_name`/`customer_cpf`/
  `competency_date`/`description` no `issue()`; novo `check_status()` para polling, já que a
  emissão da NFE.io é **assíncrona**: o POST devolve `pending` com um id, o status final
  (`issued`/`failed`) só existe segundos/minutos depois). `get_invoice_provider()` ramifica por
  `INVOICE_PROVIDER` (`nfeio` | `noop`), mesmo formato do `get_gateway()`.
- `payments/invoicing_nfeio.py` (novo) — adapter REST espelhando `gateways/mercadopago.py`
  (httpx, Basic Auth com a API Key, tabela de status). **Nomes exatos de campo não confirmados
  contra o Swagger real da NFE.io** (escrito a partir da doc pública) — conferir na primeira
  chamada real antes de apontar para a empresa/API key de produção; não afeta o resto do desenho.
- Migração `f7c1b2e9d4a3` (down_revision `e1f2a3b4c5d6`) — `app_payment_orders` ganha
  `invoice_provider_id` (id no provedor, chave de idempotência/polling) e `invoice_number`
  (número do município, só após `issued`).
- `request_invoice()` agora reconsulta (`check_status()`) em vez de reemitir quando já existe
  `invoice_provider_id` — nunca duplica a nota do mesmo pedido.
- Polling: `scripts/invoice_poll.py` + `POST /api/cron/poll-invoices` (mesmo formato do
  `settle_bets.py`/`cron_settle_bets`), já que não dá para confiar só num webhook da NFE.io de
  imediato — itera pedidos `invoice_status=pending` com `invoice_provider_id` setado.
- Guarda de boot (`startup.py::_invoice_problems()`): fatal em produção se `INVOICE_PROVIDER=
  nfeio` e faltar `NFEIO_API_TOKEN`/`NFEIO_COMPANY_ID`/dados fiscais da empresa. **`noop` em
  produção não é fatal** (diferente de e-mail/pagamento) — só `logger.warning`, porque não emitir
  nota real não deveria bloquear o lançamento das vendas.
- Dados fiscais da empresa (CNPJ, razão social, endereço, inscrição municipal, CNAE, código de
  serviço municipal, regime tributário) viram env vars em `config.py` (não `PlatformSetting`) —
  são dados legais raramente alterados e precisam estar disponíveis no boot para a guarda fatal,
  mesmo padrão do `EMAIL_FROM`.

**Testes novos** (mesmo padrão do `verify_signup_flow.py` — servidor HTTP local fake, sem rede
real): `scripts/verify_startup_config.py` (7 cenários da validação de boot, cobrindo os dois
guardas novos) e `scripts/verify_invoice_flow.py` (checkout mock → paga → nota `pending` → poll
→ `issued`, caminho de erro do provedor, e não-duplicação do `request_invoice()`) — os dois
passam 100%. `verify_signup_flow.py` também rodado de novo como regressão.

**Runbook do dono (fora de código):**
1. Painel NFE.io (`app.nfe.io`): cadastrar/confirmar a empresa com os dados fiscais já prontos;
   subir o certificado digital A1 (só pelo painel, não por API); copiar Company ID + API Key.
2. Render → env vars: `PAYMENT_PROVIDER=mercadopago` + credenciais MP; `INVOICE_PROVIDER=nfeio` +
   `NFEIO_API_TOKEN`/`NFEIO_COMPANY_ID` + os `COMPANY_*` (ver `backend/.env.example`, seção nova).
3. Redeploy; conferir no log `[config] OK — ... payment_provider=mercadopago
   invoice_provider=nfeio` ou o `ConfigError` listando o que falta.
4. `alembic upgrade head` em produção (pendente desde a sessão anterior + a migração desta).
5. Cron novo: `POST /api/cron/poll-invoices?token=$CRON_TOKEN` a cada 15-30 min (mesma cadência
   do `settle-bets`).

---

## 13. Pesquisa de Modelos para Clubes (2026-07-15, branch `clubs`)

Com a coleta de seleções saturada, a coleta de **clubes** (13 competições, Brasil→Europa→América
do Sul, 2010→2026) chegou a **54.072 jogos**. Isso abriu uma pesquisa dedicada — **duas linhas
paralelas, sob o mesmo protocolo único** (5 folds temporais expanding, seed 42; métricas
log-loss/RPS/Brier/ECE/tail-ECE/cobertura80) — para responder duas perguntas: *(1) a arquitetura
atual de seleções continua a melhor quando treinada com muito mais dados? (2) o conhecimento de
clubes melhora as previsões de seleções?* Diário completo, literatura revisada e todos os números
em **`backend/docs/PESQUISA_CLUBES.md`**; relatório consolidado automático em
**`backend/docs/RELATORIO_FINAL_PESQUISA_CLUBES.md`**. Infra reprodutível: **§7 do
`ARCHITECTURE.md`**.

### 13.1 Linha A — arquitetura atual retreinada em clubes
Mesma classe `DixonColesNBRegressor` (GBM→λ/μ + acoplamento DC + NB), sem mudança estrutural,
treinada nas mesmas 158 `base_feats`. **Venceu tudo**: bateu os 7 candidatos da Linha B (Fase 1),
a bateria avançada (Fase 6) e o tuning de hiperparâmetros (Fase 2.5, 18 configs × 5 folds)
confirmou que a config de produção (100 árvores, prof.3, lr=0.05) já é a **melhor do grid**
(log-loss 0,9938) — 5-9× mais dados de clubes não deslocou o ponto ótimo de complexidade.
Cascata de contagem (finalizações/a-gol/escanteios/cartões) replicada com sucesso sobre 35.208
jogos com box-score (8,6× mais que seleções), cobertura de intervalo 80% honesta em todos os
mercados (83,9%-88,2%).

**9 hipóteses reprovadas/inconclusivas em seleções, revisitadas com a base maior**: 8 continuam
reprovadas/inconclusivas (time-decay, momentum, XGBoost/LightGBM p/ λ, calibração pós-hoc,
árbitro, perfil Elo-condicionado, xG-feature — prejudicado por baixa cobertura histórica —, GP≈NB
em escanteios). **1 achado novo**: o blend DC+HistGBM no mercado de **BTTS passou a valer**
(4/5 folds, era só marginal em seleções) — candidato a investigar no pipeline de seleções (fora
do escopo desta pesquisa).

**Transferência clubes→seleções (Fase 3): NÃO ajudou.** Zero-shot (só clubes) piora bastante
(0/5 folds); treino combinado (pooled) é um empate estatístico (delta≈0); hiperparâmetros já são
os mesmos. **Sem exceção de push** — nada bateu a produção real de seleções sob o gate §6.

### 13.2 Linha B — pesquisa aberta (sem viés da arquitetura atual)
Revisão de literatura (Soccer Prediction Challenges 2017/2023, Bunker/Yeung/Fujii 2024,
Koopman-Lit): confirma que **GBM sobre ratings dinâmicos (CatBoost+pi-ratings) é o SOTA** em
datasets só-de-gols — implementado e testado, mas **perdeu** para a arquitetura de produção
mesmo após sweep extensivo de hiperparâmetros (melhor config 0,9970 vs 0,9938 do DC-NB).
Também testados e reprovados: Dixon-Coles clássico (estático e com time-decay), Poisson
bivariado Karlis-Ntzoufras, ratings GAP (Wheatcroft) plugados direto como λ de NB (empata com a
cascata GBM, não bate), **state-space score-driven** (GAS, na linha de Koopman-Lit — único
modelo da literatura com lucro comprovado contra odds; 0/5 folds aqui), **stacking/ensemble**
(quase empate) e **MLP tabular** (torch CPU; confirma a literatura — DL não bate GBM em futebol).

**Engenharia de atributos própria de clubes** (congestão de calendário, altitude+viagem,
mata-mata ida/volta, rotação de elenco, xG over/under-performance, GAP ratings, importância da
partida via tabela corrente simulada): só **GAP ratings passou isolado** (5/5 folds, delta
-0,0022 — pequeno mas consistente); os demais deram resultado misto ou nulo.

### 13.3 Backtest de valor (Fase 8) — achado operacional
`odds_registry` tinha **ZERO cobertura de clubes** (só Copa do Mundo) — o backtest de ROI real
de clubes é hoje impossível. Corrigido nesta sessão: `backend/scripts/collect_club_odds_forward.py`
(novo) passa a coletar odds futuras das ligas de clubes. Backtest de papel (proxy contra
frequência histórica, **não é ROI real**) deu edge positivo em 5/5 folds, yield médio +5,64% —
só diagnóstico de calibração relativa, não validação de rentabilidade.

### 13.4 Conclusão
**Meta-achado da pesquisa:** a arquitetura de produção não só sobrevive à escala — ela é
**comprovadamente ótima** dentro do espaço de hipóteses testado (estatístico clássico, GBM+ratings,
state-space, ensemble, deep learning), mesmo com quase 10× mais dados e diversidade de ligas/
continentes. Não há promoção para `main`; todo o trabalho fica documentado e commitado (agora mesclado na
`main`) para referência futura (evita retestar as mesmas hipóteses).

### 13.5 Sessão 2026-07-18 — expansão de coleta (34 novas competições) + merge na `main`
Com a assinatura da API-Football expirando em 2026-07-19T01:21 UTC, a cota diária ociosa (seleções
saturadas) foi usada para diversificar ainda mais a coleta de clubes: **+34 competições** (26→60
no total), priorizadas por fama editorial em 4 tiers (grandes ligas asiáticas/2ªs divisões
europeias → ligas europeias tradicionais → ligas sul-americanas → outras ligas notáveis) — ver
lista completa em `backend/scripts/prefetch_clubs.py::LEAGUES`.

**Gargalo de throughput identificado e corrigido:** o prefetch sequencial mede ~15-20 chamadas/min
na prática (não ~450/min teórico do plano Ultra) porque `httpx.get()` sem keep-alive paga
handshake TCP/TLS completo a cada chamada. Novo `backend/scripts/prefetch_clubs_parallel.py`
(N workers + rate limiter compartilhado, mesmo padrão do `mirror_club_cache.py`) recupera a banda
real (~380 req/min sustentado). Duas armadilhas encontradas e corrigidas durante o ajuste: (1)
`--rps` acima de 450/min real (teto do plano) causa tempestade de 429 — default seguro fixado em
6.5 rps (390/min) + retry com backoff exponencial; (2) escritor único fazia Neon+SQLite por
registro e virava gargalo sob paralelismo — corrigido paralelizando a escrita no Neon dentro de
cada worker (pool de conexões do SQLAlchemy suporta, `pool_size=5 + max_overflow=10`), mantendo só
o espelho SQLite local serializado no escritor único (não aceita escrita concorrente).

**Merge `clubs` → `main` (2026-07-18):** sem sobreposição de arquivos com o trabalho recente da
`main` (parceiros/nota fiscal/frontend, §12.8/§12.9) — branches divergiram no mesmo ponto e
tocaram áreas totalmente distintas, merge automático limpo (só conflito nos docs de índice, por
edição concorrente das mesmas seções). Pesquisa de clubes (§13.1-§13.4) e infra de coleta agora
vivem na `main`.

## 14. Mercados de Clubes em Produção (2026-07-18)

Mesmo dia do merge (§13.5), na sequência: o site já anunciava publicamente (cronômetro na home)
o lançamento dos mercados de clubes. Como a pesquisa (§13) já tinha provado que a arquitetura de
produção (DC-NB + cascata de contagem) é ótima também para clubes, faltava só **empacotar isso
como artefato servível** e ligar o backend/frontend a um segundo escopo — zero modelo novo.

### 14.1 Artefato de produção

`backend/scripts/build_clubs_production_artifacts.py` (novo) — mesmo padrão de
`train_and_save_apifootball.py`/`train_dc_apifootball.py` (fit na base INTEIRA, sem holdout,
hiperparâmetros já confirmados pela pesquisa), reaproveitando 100% das classes de produção
(`DixonColesNBRegressor`, `ShotsNB`, `CornersNB`, `CardsGP`, `ortho_sinais`) e os helpers já
validados em `clubs_train_counts.py`. Resultado em `backend/model_artifacts_clubes/`:
**1.197 times, 54.072 jogos, 13 competições** (as que já tinham `has_advanced_stats` suficiente
das 60 em coleta — o restante entra num re-run futuro conforme a coleta expandida for
processada por `build_clubs_dataset.py`). Mercados incluídos: vencedor/empate, BTTS, over/under
gols, finalizações, finalizações a gol, escanteios, cartões — os mesmos que a pesquisa validou
para clube. **Fora desta rodada** (não validados para clube, artefato ausente = mercado não
exposto, mesmo padrão já usado para `offsides_nb`/`ou_calibrators`): mercados por-tempo
(1º/2º tempo de gols/cartões), impedimentos, props de jogador.

**Duas armadilhas de dado encontradas e corrigidas** (não são bug de modelo, são de nome/id):
1. `build_clubs_dataset.py` grava cada time internamente como `"Nome#id"` (chave anti-colisão
   da COLETA entre países/ligas) — isso vazava cru pro artefato/UI. Corrigido: nome exibido é
   limpo (`"Nome"`), e só os casos de colisão REAL (mesmo nome limpo, `team_id` diferente —
   3 casos encontrados: Athletic Club, Drita, Santa Cruz) ganham sufixo `"Nome (Liga)"`.
2. A tabela `team_ids` do Neon (usada pro escudo do time) é preenchida só por
   `build_referees_and_team_ids.py`, que lê só o cache de seleção — nunca teve dado de clube.
   Corrigido sem tocar o Neon: `meta.json` de clube agora carrega seu próprio `team_ids`
   (extraído do `home_team_id`/`away_team_id` já presentes no dataset), e
   `get_team_ids(scope="clube")` lê dali em vez de consultar o Neon.

### 14.2 Backend — escopo `scope: "selecao" | "clube"`

`predictor.py` já aceitava `art_dir` no `__init__` — nenhuma mudança estrutural, só tornar os 4
loads por-tempo (`gols_1t/2t`, `cartoes_1t/2t`) opcionais (mesmo padrão de `offsides_nb`), já que
a pesquisa não validou esses mercados pra clube. `app/services/predictor_service.py` ganhou
`get_club_predictor()`/`_predictor_for(scope)` e um parâmetro `scope` (default `"selecao"`,
retrocompatível) em `predict_match`, `get_team_ids`, `get_pmf_preview`, `get_injuries` e nas rotas
de `app/main.py` (`/predict`, `/teams`, `/team/{nome}`, `/h2h`, `/api/team-ids`,
`/api/competition-benchmark`, `/api/pmf-preview`, `/api/scorers`, além das 5 rotas team-scoped).

**Achado que quase passou despercebido:** o fluxo real de análise PAGA (`POST /analysis`) não
passa por `/predict` — tem seu próprio `_generate_snapshot()` em
`app/domains/analysis/service.py` com sua própria chamada a `get_predictor()`. Corrigido junto
(schema `AnalysisRequest` ganhou `scope`), senão toda análise de clube comprada teria saído
errada (dado de seleção) mesmo com o resto do backend correto.

**Cortes de escopo desta entrega (documentados, não esquecidos)** — endpoints cuja fonte de dado
hoje é exclusiva de seleção degradam para resposta vazia/desabilitada em vez de quebrar quando
`scope=="clube"`: recentes/histórico de time, goal-timing, benchmark de competição, radar de
anomalias, props de jogador (goleador/finalizador — modelos treinados só com seleção). A tabela
`club_odds_registry` (usada por `get_upcoming_fixtures()` pro seletor de "Partida Agendada")
existe no código (`collect_club_odds_forward.py`) mas nunca foi populada — hoje o seletor de
partida agendada só lista jogos de seleção; isso não bloqueia o fluxo principal porque o CTA do
banner de lançamento abre direto a "Análise Independente" (escolha livre de dois clubes), que
funciona 100%.

### 14.3 Frontend

Toggle "Seleções / Clubes" na Análise Independente (`page.tsx`), `scope` propagado em
`PredictionContext`/`api.ts`/`monetizationApi.ts`, banner de lançamento (`ClubMarketsBanner`) com
CTA funcional (`onExplore` → muda pro modo Análise Independente + escopo clube). Seleção de
"Partida Agendada" já reaproveita o `MatchPickerModal` existente sem mudança estrutural (só o
tipo `PickerFixture` ganhou `scope`). Tooltips de cards (`H2HCard`, `KeyPlayerMatchup`,
`GoalTiming`, `StyleRadar`, `DestaquesRecentes`, `BoletimDesfalques`) trocaram "seleção(ões)" por
"equipe(s)" (texto neutro, funciona pros dois escopos sem precisar de lógica condicional).

### 14.4 Verificação

Smoke test direto (`predict_match(..., scope="clube")` com confronto real do
`results_slim.csv`) retornou todos os mercados com probabilidades válidas (somam ~100%, sem
NaN). Fluxo de UI testado no browser: banner → Análise Independente → toggle Clubes → busca de
time (nomes limpos, sem `#id`) → H2H real (Flamengo x Palmeiras, 35 confrontos diretos) →
seções sem dado de clube degradam com "sem jogos recentes" em vez de erro. `tsc --noEmit` limpo.
Não foi possível validar visualmente o card de mercados pós-geração (login da conta demo
retornou 401 — credencial desatualizada no ambiente local, não relacionado a esta mudança).

## 15. Partidas agendadas de clube + Elo histórico real + retreino 60 ligas (2026-07-18)

Fecha os cortes de escopo deixados em aberto pela §14: `club_odds_registry` populada, artefato
de clube retreinado com a coleta expandida, gráfico de Elo com histórico real (não mais o
fallback fixo 1500), e um bug sério (não relacionado a esta rodada, pré-existente desde a §14)
achado e corrigido na página `/estatisticas`.

### 15.1 Retreino do artefato de clube (13 → 46 competições)

`build_clubs_dataset.py` + `build_clubs_production_artifacts.py` re-executados sobre o cache já
expandido (backfill das 34 ligas de expansão da §13, concluído antes desta sessão). Resultado:
**174.697 jogos, 2.192 times, 46 competições** entraram no treino (das 60 coletadas — as 14
restantes ainda não tinham jogos suficientes mesmo após o backfill, ficam para um próximo
re-run). Mesma arquitetura/hiperparâmetros da §13/§14, zero mudança de lógica — só mais dado.
String `source` do `meta.json` era hardcoded "13 competições"; virou `f"...{len(tournament_weights)}
competições..."` em `build_clubs_production_artifacts.py`, e o artefato já gerado foi corrigido
via patch pontual (sem re-treinar, só editando o campo).

### 15.2 Elo histórico real (backend + frontend, os dois escopos)

O gráfico "Evolução de Elo" em `/estatisticas` estava efetivamente morto: a tabela `matches` do
Neon nunca teve colunas de Elo, e o fallback do backend caía sempre no valor fixo 1500 rotulado
"Atual" (bug de nome de chave, não investigado até agora). Não precisou recalcular nada — o Elo
já existe linha-a-linha em `international_features_enriched_apifootball.csv` (seleção) e
`data/built/club_features_enriched.parquet` (clube), usado como feature de treino
(`home_elo_pre`/`away_elo_pre`), só nunca tinha sido exposto pra API de histórico.

Novo `backend/scripts/build_elo_history.py`: derrete home/away em long format, resample mensal
(último valor do mês), grava `elo_history.csv` em cada `model_artifacts{,_clubes}/` (colunas
`team, date, elo`). `predictor_service.py::get_team_history()` reescrito: lê o CSV do escopo
certo (memoizado em módulo), filtra por janela de **7 anos (seleção) / 3 anos (clube)**, devolve
`elo_history` no formato que o frontend já esperava (schema inalterado). Frontend: eixo X do
gráfico (`estatisticas/page.tsx`) trocado de 1 ponto/ano pra granularidade mensal com
`tickFormatter` (`MM/AA`).

### 15.3 club_odds_registry populada + priorização

`collect_club_odds_forward.py` reestruturado em duas fases (padrão já usado do lado seleção):
**Fase 1 (descoberta)** — 1 requisição/dia da janela, varre todos os campeonatos treinados e
monta a lista de candidatos; **Fase 2 (odds)** — 1 requisição/fixture, candidatos ordenados por
prioridade editorial (`PRIORITY_LEAGUES`: Brasileirão A, Brasileirão B, Copa do Brasil, Champions
League, Premier League, La Liga — depois o resto por volume de jogos em aberto), com
`--quota-buffer` parando o loop antes de estourar a cota. Rodado com `--days 14
--quota-buffer 100`: **103 partidas de clube** sincronizadas na tabela (cota final 611/75.000,
faltando ~4h30 pra assinatura da API-Football expirar em 2026-07-19).

**Bug de dado encontrado e corrigido na mesma rodada:** o coletor gravava o nome cru do time
retornado pela API-Football, ignorando a desambiguação por colisão (`"Nome (Liga)"`) que
`build_clubs_production_artifacts.py` já aplica no treino — resultado: partidas de times
colididos (ex. "Athletic Club", que existe em duas ligas) ficavam com nome que o preditor não
reconhecia, escudo e H2H quebrados na UI. Corrigido com `_canonical_name(raw_name, team_id)`:
resolve o nome pelo `team_id` contra o `team_ids` do `meta.json` treinado (fonte da verdade),
com fallback pro nome cru só se o `team_id` não estiver no artefato.

### 15.4 MatchPickerModal redesenhado

Reescrito na ordem pedida: escopo (Seleções/Clubes) + data (vazia por padrão, mostrando todas as
competições em aberto) na mesma linha → busca única (competição OU equipe) → grid de
competições com logo, ordenadas por `PRIORITY_LEAGUES` e depois por volume de jogos → lista de
partidas da competição escolhida, ordenada cronologicamente (mais próxima primeiro). Botão
"Escolher partida agendada" centralizado no card (`page.tsx`/`MatchModePicker.tsx`).

### 15.5 Bug pré-existente achado nesta verificação: `/estatisticas` não era scope-aware

Não fazia parte do escopo original da sessão, mas bloqueava a verificação do Elo de clube: a
página `/estatisticas` (usada tanto pela Análise quanto pelas Estatísticas) nunca propagava
`scope` para as 9 chamadas de API que dependem dele (`teamHistory` ×2, `h2h`, `recentMatches`
×2, `goalTiming` ×2, `competitionBenchmark`, `injuries` ×2, `scorers`, `pmfPreview`) — todas
caíam no default `"selecao"` mesmo com um confronto de clube selecionado, gerando 404 em cascata
e a página inteira ficava em branco (`homeHistory`/`awayHistory` nulos bloqueiam o
`bothSelected && !loading && homeHistory && awayHistory` que guarda toda a seção de resultado).
Além disso `MatchModePicker.tsx` (o seletor usado só por `/estatisticas`, distinto da
implementação própria do `page.tsx`) não tinha toggle de escopo no modo "Análise Independente" e
buscava a lista de times sempre em `scope=selecao`. Corrigido: `scope`/`setScope` do
`PredictionContext` propagados nas duas pontas, toggle Seleções/Clubes adicionado ao
`MatchModePicker`, e a escolha de partida futura/passada agora atualiza `scope` a partir do
`fx.scope` da partida escolhida (mesmo padrão que `page.tsx` já usava). Verificado no browser:
página `/estatisticas` completa (H2H, radar, Elo, quadrantes, escanteios, cartões) renderizando
para um confronto de clube (Atletico Goianiense x Athletic Club) numa aba nova e limpa, sem
erros de console além de um warning pré-existente não relacionado (`<script>` tag).

### 15.6 Verificação

Backend: `Predictor(art_dir="model_artifacts_clubes")` carrega (2.192 times, 46 competições em
`tournament_weights`); `get_upcoming_fixtures()` retorna itens `scope="clube"` com `league_id`
em ambos os branches; `get_team_history(..., scope="clube")` retorna Elo real (ex.: Athletic
Club, 17 pontos mensais 2024-02→2026-07). Frontend: `tsc --noEmit` limpo nos dois momentos
(antes e depois do fix do §15.5); fluxo completo testado no browser (modal → grid de
competições → seleção de partida → confronto carregado → `/estatisticas` completo).

## 16. Bateria de 12 hipóteses (dataset 60 ligas) + 3 mercados novos + fix de coleta (2026-07-19)

Pedido do dono: subir a coleta pra 16 workers, testar exaustivamente uma lista de 12 hipóteses
de modelo pra clube, e implementar os mercados novos identificados na sessão anterior. Trabalho
executado localmente (worktree `../previsao-jogos-clubs-research` na branch `clubs`, dataset
copiado — evita reprocessar/reescrever o `main` e evita Neon pra computação, só a coleta grava
lá). **Nenhuma hipótese passou o gate §6 desta vez** — produção continua sem exceção de push.

### 16.1 Coleta — bug real encontrado e corrigido

`quota_tracker.throttle()` (criado na sessão anterior pro fix de cota diária) liberava rajada
até o teto de 440/min em vez de espaçar as chamadas — com 8 workers o jitter não estourava o
limite por-segundo real da api-football, mas com **16 workers** (pedido desta sessão) gerou
centenas de `429 Too Many Requests` (chamadas desperdiçadas, não afeta cota diária mas atrasa).
Corrigido: `throttle()` agora aplica um espaçamento mínimo (`MIN_GAP = 60/PER_MINUTE_CAP`) entre
liberações, além do teto por janela — rajada inicial eliminada. `PER_MINUTE_CAP` também reduzido
de 440→380 (margem maior pro jitter de 16 threads). `DOWNLOAD_WORKERS` em
`backfill_history_priority.py`: 8→16.

Resultado: `data/built/club_matches.parquet`/`club_fixtures.parquet`/`club_lineups.parquet`
reconstruídos do zero sobre o espelho local (`club_raw_cache.sqlite`, 5,2 GB, 100% local) —
**191.580 fixtures, cobertura box-score 71%, cobertura xG 14,1%**. Coleta do dia rodou em duas
levas (relançada após o fix): 44 ligas completas (tier1+tier2), cota final ~39.6k/75k restante
(sobrou pra amanhã). `club_lineups.parquet` novo: 378.291 escalações em 189.150 jogos (nunca
tinha sido regenerado desde a expansão pras 60 ligas).

**Nota:** o artefato de PRODUÇÃO (`model_artifacts_clubes/`, DC-NB principal) continua o do §15
(174.697 jogos/46 competições) — não foi retreinado nesta rodada porque nenhuma hipótese testada
abaixo passou o gate de promoção; o dataset de 191.580 jogos foi usado só pra pesquisa e pros 3
mercados novos por-tempo/vermelhos/marcador-primeiro (que treinam modelos independentes, não
tocam o DC-NB principal).

### 16.2 As 12 hipóteses — vereditos

Protocolo reusado de `research_clubs/protocol.py` (splits temporais expanding, gate: **≥4/5
folds melhoram logloss E delta<-0.001** pra "PASSA"). Scripts novos em
`backend/scripts/clubs_hyp{3,4,5,6,10}_*.py` + `clubs_new_hyp_ablation.py` (H3+H8), todos na
branch `clubs` (worktree).

| # | Hipótese | Veredito | Nota |
|---|---|---|---|
| 1 | Re-rodar Fase 4/5/6 completas no dataset 60 ligas | **NÃO EXECUTADO** | dataset rebuildado a tempo, mas a bateria completa (13 testes da §13) não foi re-rodada nesta sessão — fica pro próximo round |
| 2 | Blend com odds reais de clube | **BLOQUEADO** | `club_odds_registry` só começou a popular hoje (103→ mais odds na Fase A do mega_collect); volume insuficiente pra backtest |
| 3 | Pooling hierárquico Elo-diff por liga (shrinkage empírico-Bayesiano) | **misto** | 5/5 folds melhoram mas delta=-0.0004 (abaixo do limiar -0.001) — direção certa, efeito pequeno demais |
| 4 | Lineup novelty (desfalque real vs XI habitual, não só turnover) | **REPROVADO** | 3/5 folds, delta~0.0000 |
| 5 | Correlação ida-volta em mata-mata | **CONFIRMADO (diagnóstico)** | corr(margem leg1, leg2)=-0,132 (n=1.702), regressão mostra efeito de motivação real (coef_deficit=-0,069, R²=0,096) — vale construir mercado de qualificação agregada com modelo correlacionado (não feito ainda, ver §16.4) |
| 6 | xG como mercado próprio (O/U, não feature) | **VIÁVEL, aguardar mais dado** | cobertura80=0,975, MAE=0,89 gol — amostra de 14% ainda pequena pra servir com confiança |
| 7 | Proxy de lesões no resultado | **BLOQUEADO** | zero dado de `/injuries` cacheado pra clube; coletar 190k+ jogos custaria cota alta sem garantia (já marginal em seleção) |
| 8 | Efeito derby/rivalidade (mesma cidade-sede) | **misto** | 4/5 folds melhoram mas delta~0,0000 — sem sinal incremental sobre Elo |
| 9 | GAP-ratings revisitado (60 ligas) | **NÃO EXECUTADO** | mesmo caso do #1 — fica pro próximo round de pesquisa |
| 10 | Calibração isotônica por bucket de \|elo_diff\| | **REPROVADO** | logloss piora em 5/5 folds (+0,003 a +0,014) vs baseline no mesmo dataset/folds — diferente do O/U de contagem (calibração lá já promovida), não ajuda o resultado H/D/A |
| 11 | Home advantage por lotação/capacidade de estádio | **BLOQUEADO** | api-football não expõe `attendance` no bloco `fixture.venue` (só id/nome/cidade) |
| 12 | Momentum de goleiro pra BTTS/clean-sheet | **NÃO EXECUTADO** | dado de saves por goleiro existe no box-score (`players[].statistics.goals.saves`), mas não foi extraído/testado nesta rodada |

### 16.3 Mercados novos entregues (backend + frontend, ambos escopos)

Todos seguem o padrão opcional/retrocompatível já usado por `impedimentos` (`if os.path.exists`
no `Predictor.__init__`, artefato ausente = mercado não aparece — zero risco pra produção atual):

- **1º/2º tempo pra CLUBE** (`gols_1t/2t`, `cartoes_1t/2t`) — já existia pra seleção (§ antiga,
  nunca documentada como "gap"); só faltava treinar pro escopo clube. Novo
  `build_clubs_halftime_targets.py` (extrai placar/cartões por tempo dos eventos brutos do
  espelho local, 191.392 jogos) + `train_clubs_halftime_markets.py` (mesma classe `CornersNB` da
  cascata de escanteios). 174.544 jogos casados. Frontend **não precisou mudar** — `tempos` já
  era servido de forma agnóstica de escopo.
- **Cartões vermelhos isolados** (`cartoes_vermelhos`) — hoje `cartoes` soma amarelo+vermelho;
  novo mercado separado (`CornersNB`, grade pequena `max_corners=4`, raro: ~0,10-0,13/time/jogo).
  `build/train_redcards_market.py --scope {selecao,clube}`, artefato em ambos
  `model_artifacts{,_clubes}/cartoes_vermelhos_nb.joblib`. Frontend: card novo em `page.tsx`
  (mesmo padrão de "Impedimentos"), tipo `cartoes_vermelhos` em `api.ts`.
- **Time a marcar primeiro** (`time_marca_primeiro`) — P(mandante/visitante marca o 1º gol /
  nenhum gol). Novo `build_first_scorer_targets.py` (extrai do 1º evento `type=Goal` ordenado por
  minuto, ambos os espelhos locais) + `train_first_scorer_market.py` (classificador multinomial
  `HistGradientBoostingClassifier` sobre `base_feats`, salvo como `{pipe, feats}` via joblib — não
  é `CornersNB`, é probabilidade direta). 191.305 jogos (clube) / 6.317 (seleção, amostra menor —
  poucos jogos de seleção têm eventos completos). Frontend: card de 3 vias no padrão "Ambas
  Marcam" (`page.tsx`), tipo `{ prob, odd_justa }` em `api.ts`.

Todos os 3 verificados ponta a ponta: smoke test do `Predictor` isolado + fetch real contra o
`/predict` do dev server + `tsc --noEmit` limpo. **Gotcha encontrado:** `uvicorn --reload` no
Windows por vezes não detecta mudança em `predictor.py` (WatchFiles perde o evento) — se um
`fetch` novo não trouxer o campo esperado, reiniciar o servidor manualmente antes de suspeitar de
bug de código.

**Handicap de escanteios/cartões por time**: checado e já existia (não era gap real) —
`escanteios`/`cartoes` sempre expuseram O/U por time (`home_team`/`away_team`) além do total,
renderizado em `page.tsx` desde sempre.

### 16.4 Não executado nesta rodada (fica documentado pro próximo round)

- Mercado de **qualificação/agregado de mata-mata** (depende da hipótese #5, confirmada — falta
  o modelo bivariado condicional e a UI de "confronto agregado").
- Mercado de **assistências** (marcador de assistência) — dado existe
  (`players[].statistics.goals.assists`), mas replicar a arquitetura de
  `build_scorer_model.py`/`build_shots_prop_model.py` pro escopo clube é um trabalho maior
  (painel jogador-partida, features de defesa do adversário, validação temporal) que não coube
  nesta sessão.
- Hipóteses #1/#9 (rerun completo da bateria §13 no dataset de 60 ligas) e #12 (momentum de
  goleiro) — não executadas, dado/infra prontos pro próximo round.

## 17. Fecha pendências do §16: GAP ratings promovido, mercados amarelos/agregado, 8 ligas novas (2026-07-19, mesmo dia)

Continuação direta da sessão do §16 — fecha os 3 itens que ficaram "não executado" lá
(hipóteses #1/#9/#12) e os 2 mercados adiados em §16.4 (qualificação agregada, cartões
amarelos não estava listado mas foi pedido nesta rodada). Trabalho de pesquisa 100% na
worktree `../previsao-jogos-clubs-research` (branch `clubs`, commit `622080c`); promoção
pra produção direto no `main`.

### 17.1 Hipóteses #1/#9/#12 — fechadas

Diário completo em `backend/docs/PESQUISA_CLUBES.md` §7 (branch `clubs`). Resumo:

| Hipótese | Veredito | Nota |
|---|---|---|
| #12 momentum de goleiro (BTTS/clean-sheet) | REPROVADO/misto | 3 targets, nenhum bate o gate (btts 4/5 delta -0,0001; home_cs 3/5 delta -0,0004; away_cs 2/5 delta +0,0005) |
| #1/#9 `gap_ratings` revisitado (60 ligas, 191.580 jogos) | **PASSA — PROMOVIDO** | 5/5 folds, delta -0,0022 (mesmo achado da base de 13 ligas, agora confirmado com 3,4x mais dado) |
| #1 `blend_btts` revisitado | misto (mais forte) | 5/5 folds (era 4/5), mas delta -0,0005 — ainda abaixo do limiar -0,001. Candidato a reteste futuro, não promovido |
| #1 `xg_feature`/`ensemble` revisitados | REPROVADO | 1/5 folds, delta ~0,0000 em ambos |
| #1 `gap_counts` (finalizações) | inconclusivo | sem cascata GBM (fase 2) disponível pra comparar |

**Bug de infra encontrado nas duas tentativas anteriores de rodar esta bateria** (por isso
ficou "não executado" no §16 apesar de já ter sido tentado): o worktree de pesquisa não tem
`.venv` próprio (não é versionado); os scripts foram lançados com `.venv/Scripts/python.exe`
relativo, que falha silenciosamente (ou cai num Python312 global sem numpy/pandas
instalados) — os logs ficavam com conteúdo real de uma tentativa anterior misturado com o
erro da nova, parecendo "em andamento" sem nunca terminar. Corrigido lançando com o caminho
absoluto do `.venv` do repo principal.

### 17.2 GAP ratings promovido para produção (DC-NB de clube, 158→170 features)

`gap_ratings` (Fase 5.6 — ratings Wheatcroft de ataque/defesa em casa/fora, separados para
chutes e escanteios) passou o gate §6 com folga (delta -0,0022, mais que o dobro do limiar
-0,001) em 5/5 folds temporais, no dataset de 191.580 jogos/60 ligas — o mesmo protocolo e
hiperparâmetros exatos de produção (`DixonColesNBRegressor(n_estimators=100, max_depth=3,
learning_rate=0.05, max_goals=12)`), então a promoção é direta (sem exceção nenhuma — bateu o
gate normal).

**Desafio de serving**: `compute_gap_ratings` (`research_clubs/ratings.py`) é um rating
*sequencial com estado* (como Elo, mas 4 números por time — ataque/defesa em casa e fora),
atualizado jogo a jogo; não dá pra recomputar a cada predição. Resolvido com o mesmo padrão
já usado pro Elo (`elo_history.csv`, §15): snapshot do estado FINAL por time, servido junto
do artefato.

- `research_clubs/ratings.py::compute_gap_ratings` ganhou `return_state=True` — devolve
  também os dicts finais `{Ha, Hd, Aa, Ad, running_mean}` (ataque-casa/defesa-casa/
  ataque-fora/defesa-fora por time) após processar o histórico inteiro em ordem.
- `scripts/build_clubs_production_artifacts.py`: computa `gap_shots_*`/`gap_corners_*` (12
  colunas) pro dataset de treino inteiro, adiciona ao `base_feats` do DC-NB (só do DC-NB —
  não entra na cascata de chutes/escanteios/cartões, que não foi testada com esse sinal), e
  grava o estado final em `meta["gap_ratings_state"]` (`{"shots": {...}, "corners": {...}}`,
  chaveado por nome de time).
- `predictor.py::build_row()`: bloco novo, opcional (só roda se `self.meta.get(
  "gap_ratings_state")` existir — seleção não tem a chave, zero impacto lá). Pra um novo
  confronto, busca `Ha/Hd[home_team]` e `Aa/Ad[away_team]` no snapshot (fallback = média
  corrente da liga se o time nunca jogou) e recalcula `exp_home`/`exp_away` na hora — mesma
  fórmula do treino, só que pro par de times específico da predição.

Retreino completo: **2.326 times, 52 torneios** (subiu de 46 no §16 — as 34 ligas de
expansão do §16.1 já tinham dado suficiente pra algumas entrarem no `tournament_weights`
desta vez). Build demorou ~2h (mais que o usual — cascata de chutes/escanteios/cartões
continua em `GradientBoostingRegressor` clássico, não trocado; não é regressão, é só o
dataset maior). Verificado ponta a ponta: `Predictor` isolado, `/predict` e `/api/aggregate`
via `TestClient`, times obscuros aleatórios sem erro.

### 17.3 Mercado novo: cartões amarelos isolados (ambos escopos)

Espelha `cartoes_vermelhos` (§16.3) — hoje `cartoes` soma amarelo+vermelho, faltava isolar o
lado amarelo (maioria dos cartões). `scripts/train_yellowcards_market.py --scope
{selecao,clube}` (mesma arquitetura `CornersNB`, `max_corners=6`, alvo
`home_cur_sb_yellow`/`away_cur_sb_yellow`, já existente no box-score de ambos os escopos).
Artefato `cartoes_amarelos_nb.joblib` em `model_artifacts{,_clubes}/`. `predictor.py`:
`YELLOWCARD_LINES = CARDS_LINES` (mesma grade do total). Frontend: card novo em `page.tsx`
(padrão "Cartões Vermelhos"), tipo `cartoes_amarelos` em `api.ts`.

### 17.4 Mercado novo: qualificação/agregado em mata-mata ida-volta (fecha o gap do §16.4)

A hipótese #5 (§16.2) já tinha confirmado dependência fraca entre as pernas
(corr(margem_leg1, margem_leg2)=-0,132, n=1.702) — fraca o suficiente pra servir o mercado
com as duas pernas **independentes** (produto/convolução das duas matrizes conjuntas do
Dixon-Coles), sem precisar de um modelo bivariado correlacionado dedicado.

`Predictor.predict_aggregate(team_a, team_b, tournament)`: roda `predict()` duas vezes (perna
1 = team_a mandante; perna 2 = team_b mandante, mando invertido), pega a matriz conjunta
`P[gols_A, gols_B]` de cada perna via `dc.predict_proba_markets(...)["joint"]`, reindexação
+ `scipy.signal.fftconvolve` das duas pra obter a distribuição conjunta do **agregado**
`P_agg[total_A, total_B]`. Daí: P(A classifica) = P(agregado_A > agregado_B) + 0,5·P(empate)
(empate no agregado ⇒ prorrogação/pênaltis, sem sinal disponível pra pesar melhor que
50/50 — documentado como simplificação), top-3 placares agregados mais prováveis, e
O/U de gols agregados (linha maior, 2,5-6,5, cobre as 2 pernas).

Anexado automaticamente em `predict()` (chave `mata_mata_agregado`) só quando
`tournament` é uma das competições continentais de clube que realmente jogam ida-volta com
mando invertido (`KNOCKOUT_TOURNAMENTS`: Champions/Europa/Conference League, Libertadores,
Sul-Americana, Copa do Brasil, AFC/CAF/CONCACAF Champions League) — **não** entra pra
seleção (Copa do Mundo/Euro/Copa América são mata-mata de jogo único). Overhead medido:
+12ms por predição (51ms→64ms), irrelevante. Novo endpoint `GET /api/aggregate` também
exposto standalone (mesmo cálculo, pra uso fora do fluxo de análise normal). Frontend:
`MataMataAgregadoCard` novo em `DerivedMarkets.tsx` + card de gols agregados reaproveitando
`MarketCard`, ambos dentro de `CollapsibleMarket` "Mata-Mata (Ida e Volta)".

### 17.5 Retestado: prop "jogador a levar cartão" em clube — REPROVADO de novo

Já reprovado pra seleção (§9, AUC~0,58). Retestado agora em clube com o dataset de 60 ligas
(`test_player_cards.py --scope clube`, adaptado pra ler do espelho local via `raw_cache`
em vez de escanear o Neon — regra de ouro do `ARCHITECTURE.md` §3.1) — 3.566.167
player-games, 57.037 jogadores. **AUC 0,634 (+0,017 sobre a taxa-base), abaixo do padrão do
site (~0,74 do goleador) e do limiar do gate (0,68)** → NÃO PROMOVER, mesmo com 4x mais
jogadores que o teste de seleção. Confirma: cartão de jogador é fraco por natureza
(idiossincrático/dependente de árbitro), não por falta de dado.

**Gotcha encontrado no processo**: o script original usava `GradientBoostingClassifier`
clássico — em 3,5M linhas isso trava por 10+ minutos sem progresso visível (mesmo problema
já visto nesta sessão nos scripts de prop de jogador de clube, §16). Trocado por
`HistGradientBoostingClassifier` (mesmos hiperparâmetros/mesmo padrão dos outros scripts de
prop) — terminou em minutos.

### 17.6 Expansão de coleta: 8 competições novas (copas dos "big five" + Ásia)

Cota do dia (Ultra, 75k) sobrando após os 60 ligas anteriores baterem "FIM (tudo coberto)"
(0 jogos faltando). Adicionadas ao `LEAGUES` de `prefetch_clubs.py`, priorizando copas
domésticas de grande fama que ainda não tinham entrado (só a Copa do Brasil tinha copa
doméstica coberta) + 2 ligas de mercado grande na Ásia com boa cobertura de box-score:

FA Cup (Inglaterra), FA Cup (Escócia), Copa del Rey, DFB Pokal, Coppa Italia, Coupe de
France, Indian Super League, Thai League 1.

Backfill via `prefetch_clubs_parallel.py --workers 16`: 19.875/21.547 fixtures baixadas
(92%) antes de bater o teto de chamadas do dia (`--max 22000`) — restam ~1.672 fixtures pra
completar amanhã (script idempotente, cota-first, resume sozinho). **Dados coletados ainda
NÃO entraram no dataset de treino nem no artefato retreinado do §17.2** (que usa o parquet
de antes desta coleta) — fast-follow: rebuildar `club_features_enriched.parquet` +
retreinar quando a coleta destas 8 ligas completar.

**Bug encontrado e corrigido em `prefetch_clubs_parallel.py`**: import de `_local_put`
(função que não existe mais — foi renomeada pra `_local_put_batch` numa sessão anterior sem
atualizar o script paralelo, que ficava sem uso há um tempo). Corrigido: import e chamada
ajustados pra `_local_put_batch([(key, fid, lid, season, raw)])`.

### 17.7 Cota do dia ao final da sessão

~65.3k/75k chamadas usadas (assinatura Ultra ativa até 2026-08-19). Consumida por: expansão
das 8 ligas novas (~22k chamadas), coleta diária automática de seleções (tarefa agendada
`\PrevisaoJogos\`, floor 2010, rodando em paralelo o tempo todo), e checagens de `/status`.
Retomar o backfill das 8 ligas novas amanhã, cota resetada.

## 18. Créditos promocionais + 2 tipos de cupom de parceiro + indicação de parceiros (2026-07-21)

Reforma da camada de monetização (parceiros/cupons/créditos). Backend testado (unit + smoke
runtime), frontend typecheck limpo. **Migrations são Postgres (produção); o SQLite de dev usa
`create_all`, não roda estas migrations.** Rodar `alembic upgrade head` no Neon ao promover.

### 18.1 Créditos promocionais (novo saldo, não-fungível)
- `Wallet.promo_balance` + `CreditTransaction.promo_delta`/`promo_after` (mesmo padrão de
  `reserved_*`). `post_transaction` ganhou `promo_delta` com guarda de negativo.
- **Boas-vindas = 0** (`auth/service.WELCOME_CREDITS` era 8). Novo usuário nasce com 0; conta com
  o crédito diário promocional + eventual código de indicação (bônus de 5, inalterado).
- **Crédito diário promocional = a cota `FreeDailyUse`** (1/dia, não acumula) — decisão do dono.
- **Prioridade de consumo** em `analysis/service.create_analysis`: grátis-diária → `promo_balance`
  → pago. `free`/`promo` são consumidos **na hora, nunca reservados** (mesmo em partida futura),
  logo **não habilitam a Aposta Escolhida**; só crédito PAGO em partida futura reserva.
- `credit_tx_id` da análise agora só é setado numa RESERVA real; `bets/service._load_reserved_analysis`
  passou a exigir `status == reserved` (fecha bug latente: aposta sobre análise sem reserva
  quebrava a liquidação ao tentar estornar reserva inexistente).

### 18.2 Dois tipos de cupom de parceiro
- **Convite** (criado na aprovação, `admin/service._create_partner_invite`): agora
  `first_purchase_only=True` + `promo_credits=5` + `commission_pct` **por-cupom** (= 30 − desconto,
  fecha a inconsistência de um `commission_pct` global com múltiplos tiers). Os 5 créditos vão pro
  `promo_balance` na 1ª compra (`payments/service._credit_if_paid`, key `coupon-promo:{order}`).
- **Promocional** (novo, `PartnerCouponRequest`): parceiro solicita (nome ≤12, % desconto), **1
  pendente por vez**; admin aprova com prazo (dias) OU teto de faturamento **pré-desconto**
  (`Coupon.revenue_limit_brl`, checado em `validate_coupon` e desativado em `deactivate_if_cap_reached`),
  ou rejeita com motivo. **E-mail ao parceiro nos dois casos** (`email.send_partner_coupon_decision_email`).
- `Coupon` novos: `promo_credits`, `commission_pct`, `revenue_limit_brl`. `compute_benefit` retorna
  `(amount, bonus, promo)`; `CouponPreview.promo_credits`.
- `commission_for_order` usa `coupon.commission_pct` quando a ordem usou cupom do próprio parceiro
  (fallback `affiliate.commission_pct`).

### 18.3 Indicação de parceiros (um nível) + override 5%
- `Affiliate.parent_affiliate_id` (self-ref). `apply_for_partnership` aceita `ref_partner` (código
  do indicador via link `/parceiro/solicitar?ref_partner=CODE`). O indicado **não vê** o vínculo.
- `AffiliateCommission` ganhou `kind (direct|override)` + `source_affiliate_id`; unique passou de
  `order_id` para composto `(order_id, affiliate_id)` (1 direta + 1 override por ordem).
- `_override_commission_for_parent`: 5% (PlatformSetting `partner_override_pct`, default 5) da
  comissão direta ao indicador, **custo extra do sistema** (não descontado do indicado), **um nível
  só**, idempotente por `(order_id, parent_id)`.
- `referred_partners_stats` (portal + admin detalhe); `compute_portal_stats` separa buyers/revenue
  (só `direct`) de due/paid (direct+override).

### 18.4 UI + observabilidade
- Dashboard do parceiro: 2 links (usuários / indicar parceiros), "Solicitar cupom promocional"
  (modal, bloqueado com pendente), aba "Parceiros indicados". Carteira mostra saldo Promocionais.
- Admin: **badge** de pendências acima da aba Parceiros (`/admin/pending-counts`), seção de
  solicitações de cupom (aprovar dias/faturamento, recusar com motivo), detalhe do parceiro com
  indicados + override devido. Checkout pré-preenche o cupom do parceiro via `?ref=` (`resolve-coupon`).
- Endpoints novos: `/affiliates/{coupon-requests,portal/referred-partners,resolve-coupon}`,
  `/admin/{coupon-requests[/{id}/approve|reject],pending-counts}`.

### 18.5 Migrations (head anterior `3549706daeb8`)
`d1f0a1b2c3d4` (wallet promo) → `d2f1b2c3d4e5` (coupon cols + `app_partner_coupon_requests`) →
`d3f2c3d4e5f6` (affiliate parent + commission kind/source + unique composto). Validadas por SQL
offline p/ Postgres + `create_all` no SQLite.

---

## 19. Bateria H1-H4 (empate/valor/de-vig/xG) + coleta 68→83 competições (2026-07-21/22)

Pedido do dono: baseline walk-forward de população completa + 4 hipóteses (H1 empate,
H2 backtest de valor, H3 de-vig 3-vias, H4 xG) + exaurir a cota do dia com coleta nova.
Relatório completo com todos os números: `backend/data/reports/RESUMO_BATERIA.md`
(por hipótese: `backend/data/reports/{baseline_walkforward,h1_empate,h2_value,h3_devig,h4_xg}/`).
Scripts: `backend/scripts/battery_{dataset,baseline_and_h1,h2_h3,h4_xg}.py`.
Dataset/comando/hiperparâmetros: `club_features_enriched.parquet` (183.530 jogos após
filtro matches_played_before≥5, 52 torneios), `DixonColesNBRegressor(n_estimators=100,
max_depth=3, learning_rate=0.05, max_goals=12, random_state=42)` — produção, sem alteração.

### 19.1 Coleta
68 competições de clube confirmaram **"tudo coberto"** (só gaps residuais de jogos
recém-terminados). Adicionadas **+15 competições novas** em duas levas (cota resetou à
meia-noite UTC no meio da sessão, aproveitada): Copa Argentina, Primera Nacional (ARG),
Taça de Portugal, Segunda Liga (POR), 3. Liga (Alemanha), Série C (Brasil), Liga
Panamenha, NB I (Hungria), Premier League (Gana), Botola Pro (Marrocos), Primera
Division (Costa Rica/Guatemala), Veikkausliiga (Finlândia), First League (Bulgária),
Liga 1 (Indonésia) — **68→83 competições no espelho local** (`club_raw_cache.sqlite`).
Seleções (`--all-nations`, floor 2010) recoletadas, sem achado novo (segue saturada,
§12.6). **As 15 ligas novas ainda NÃO entraram no `club_features_enriched.parquet`
nem no artefato de produção** — fast-follow natural: rebuildar o parquet + retreinar
quando quiser incorporá-las (mesmo padrão do §17.6).

### 19.2 Baseline walk-forward (pré-requisito)
Desvio documentado: protocolo de 5 folds temporais expanding (já estabelecido no
projeto, `research_clubs/protocol.py`) em vez de leave-one-(liga,temporada)-out literal
(≈600 retreinos, inviável numa sessão). 91.765 jogos avaliados fora-da-amostra: log-loss
médio 1.0082, ECE médio 1.26%, acurácia 1x2 ~49.9%, acurácia placar exato ~13.0%.
Robustez de 5 seeds (último fold): variação 0.00% — `GradientBoostingRegressor` de
produção usa `subsample=1.0`, é determinístico dado o dataset (achado documentado, não
é falha de reprodutibilidade).

### 19.3 H1 — Empate — NÃO PASSA o gate (estruturalmente; diagnóstico honesto)
ECE do empate isolado = 1.21% (já bem calibrado). Correlação freq_real_empate ×
acurácia_argmax por liga = **-0.681** (confirma: ligas com mais empate real sofrem mais
acurácia). Regra draw-aware (τ sweep): **nenhum τ melhora a acurácia sobre o argmax
puro** — log-loss/Brier do modelo são invariantes à regra de decisão (matemático).
Controle negativo corrigido nesta sessão (limiar original comparava contra acaso
uniforme 33%, errado para 1x2 que tem desequilíbrio de classe real ~45% de H por
vantagem de mandante — contra o baseline correto, sem vazamento). **Decisão: não é bug
de modelo, é oportunidade de PRODUTO** — exibir P(empate) + odd justa ao lado do argmax.

### 19.4 H2 — Backtest de valor — achado de infra + proxy positivo + real inconclusivo
**Achado de infra**: `collect_club_odds_forward.py` **NÃO está no cron**
(`collect_odds_task.cmd` só chama a versão de seleção) — cobertura de odds de clube só
cresce manualmente. Backtest de papel (proxy, grid edge×Kelly×overround): modelo bate
"sempre o favorito" com folga (+4.38% vs -7.65% yield médio), controle negativo ~0,
robusto a 5 seeds. CLV real (84 fixtures reais resolvidas via snapshots +
`model_snapshot` forward): edge médio -6.28%, 32.7% positivo — amostra pequena demais
pra validar rentabilidade; valida a metodologia, não o lucro.

### 19.5 H3 — De-vig 3-vias — Shin recomendado
`backend/data/reports/h3_devig/devig_methods.py` (proporcional/power/Shin) com testes
unitários, confirma favorite-longshot bias da literatura. Amostra real pequena (84
fixtures) — Shin recomendado por fundamentação teórica (equivalente a power nesta
amostra). Não é código de produção ainda, é modelo de referência pra quando o value
betting de 1x2 for implementado.

### 19.6 H4 — xG no DC-NB — REPROVADO (3ª vez)
Já reprovado em Fase 7 (2026-06-30) e §17.1 (2026-07-19). Por instrução do pedido, **não
reexecutada a bateria completa** — só Passo 0 (cobertura, agora 15.7%, cresceu marginal
e só em jogos recentes) + reteste confirmatório 1-fold: Δlog-loss=-0.00014 (limiar
-0.001, não passa por 7x), Δece=+0.00027 (piora). Controle negativo limpo. **Fechado
definitivamente** — não repetir sem xG de fonte nova (tracking) ou cobertura que deixe
de ser concentrada em 2023+.

### 19.7 Decisão
Nenhuma promoção de modelo, nenhum push de mudança de modelo pra `main` (H4 reprovado,
H1 é produto). Ver `RESUMO_BATERIA.md` para o detalhe completo e a lista de
ações de produto/infra recomendadas (fora do escopo de código desta sessão).

### 19.8 Fast-follow: retreino com 83 competições + bateria Tier 2/Tier 3 (2026-07-22)
Fechamento das pendências deixadas em aberto pelo §19.1 ("as 15 ligas novas ainda não entraram
no `club_features_enriched.parquet` nem no artefato de produção").

**Retreino de produção**: `scripts/build_clubs_production_artifacts.py` rerodado —
`model_artifacts_clubes/` agora tem **5589 times / 272918 jogos (272918 pra
gols/resultado/BTTS/over2.5; 141919 pra chutes/escanteios/cartões) / 72 torneios** (subiu de 52).
Mesma arquitetura/hiperparâmetros do §13 (sem mudança de modelo, só volume de dado). Smoke test
(`Predictor(art_dir='model_artifacts_clubes')`, Real Madrid x Barcelona, La Liga): carrega sem
erro, saída sã (H 39.2% / D 25.2% / A 35.6%, 3.0 gols esperados). **Artefato ainda não
commitado** — pendente de decisão do dono (`model_artifacts_clubes/*.joblib` não é gitignored,
mas troca o modelo em produção, então fica fora do escopo de "autorização geral" até
confirmação explícita).

**Tier 2 (features candidatas, gate §6, todas via `research_clubs/protocol.py`, 5 folds
temporais)** — **nenhuma promovida**:
- *Shot Quality Index* (chutes insidebox/outsidebox, `tier2_shot_quality/veredito.md`): cobertura
  46.8% (bem acima do xG ~15%). 5/5 folds melhoram, mas Δlog-loss médio = **-0.00010** (limiar
  -0.001) — **REPROVADO**, controle negativo limpo.
- *Goalkeeper Saves* (`tier2_goalkeeper_saves/veredito.md`): cobertura 52.9% (risco de "muro de
  dados", concentrada em anos recentes, mesmo padrão do xG). 5/5 folds melhoram, Δlog-loss médio
  = **-0.00037** (abaixo do limiar) — **REPROVADO**, controle negativo limpo.
- *Cartão de jogador + árbitro, combinação #3* (`tier2_player_cards_referee/veredito.md`): isola
  o efeito marginal de `ref_strictness` dentro do modelo de jogador (scope clube, amostra bem
  maior que seleção). AUC com-árbitro 0.6328 vs sem-árbitro 0.6301 (ganho +0.0026, 4/4 folds) —
  fica abaixo do piso de promoção (AUC≥0.68) já usado pra esse prop — **REPROVADO**, mesmo padrão
  das 2 combinações já testadas antes (isolado e agregado por equipe).
- *blend_btts na seleção* (`tier2_blend_btts_selecao/veredito.md`): `0.5*DC-NB + 0.5*HistGBM` no
  dataset de seleção (9954 jogos). 1/5 folds melhoram, Δlog-loss médio = **+0.0063** (piora), ECE
  piora (2.84%→4.86%) — **REPROVADO**, pior resultado das 3 tentativas já feitas (clube 13 ligas,
  clube 60 ligas, seleção) — confirma que blend BTTS não escala pra amostra pequena.
- *Mercado de assistência (clube)*: tarefa marcada concluída no rastreamento desta sessão, mas
  **nenhum artefato de relatório/veredito foi localizado** pra registrar aqui — só existe
  `scripts/build_assist_model.py`, já commitado em 2026-07-19 (3 dias antes desta bateria,
  código de produção pré-existente, não tocado nesta sessão). Não sei precisar o que foi
  concluído nesse item sem mais contexto — **pendência de auditoria, não um veredito**.

**Tier 3 (Passo 0 — só viabilidade/cobertura, sem treino de modelo)**:
- `goals_prevented` (goleiro): cobertura agregada **4.92%** (pior que o xG) — **NOT VIABLE agora**.
- `/predictions` da API-Football como baseline externo: log-loss 2.0953 em 40 fixtures (PIOR que
  palpite uniforme constante ln(3)≈1.0986) — vendor devolve probabilidades genéricas/degeneradas
  (só 6 combinações distintas em 40 casos) — **não serve de benchmark hoje**.
- `/teams/statistics` por faixa de minuto: 12/12 combos com dado real, custo de coleta completa
  ~2.300-7.500 chamadas (barato dentro da cota) — **viável como feature futura**, não implementado.

**Item 13 revisitado (time-decay, dataset de 83 ligas)**: rerun de `time_decay_H2`/`H3` (mesma
pergunta já fechada em `sweep-pesos-gols`, memória do agente) — log parado às 12:17 (processo
não está mais rodando; sem erro visível, só sem impressão de conclusão do H2). H3 terminou com
veredito explícito **REPROVADO** (0/5 folds melhoram, Δ+0.0003), consistente com o achado
anterior ("time-decay não ajuda"). H2 não gerou veredito final (parou em fold_0.70 de 5) — não
foi relançado nesta sessão (não bloqueante, resultado parcial já aponta na mesma direção do H3).

### 19.9 Decisão (fast-follow)
Nenhuma promoção de modelo nesta rodada (5/5 hipóteses Tier 2 reprovadas). Retreino de produção
(mais dados, mesma arquitetura) verificado e são, mas **não commitado** — decisão do dono.
Tier 3 fica só como mapa de viabilidade pra decisão futura de investimento de coleta.

---

## 20. Bateria de valor/CLV em escala + auditoria adversarial (2026-07-22)

Pedido do dono: a partir dos achados do módulo de backtest (`scripts/backtest_*.py`, 8117
fixtures de 2025 casadas com odds reais de `/data-test`, ver §19-adjacente/relatório de
4 ligas Brasileirão+Premier League+La Liga+Serie A), rodar quantos agentes fossem
necessários, cada linha de pesquisa com um crítico adversarial (discordar/tentar derrubar),
testando tudo que pudesse aprimorar os modelos. 4 linhas (W1-W4), 8 agentes no total
(proponente+crítico cada), execução paralela em background.

### 20.1 Groundwork
`scripts/adhoc_value_groundwork.py`: junta modelo (`prediction_json`) + odds reais abertura/
fechamento (book "Avg") + de-vig (`devig_methods.py`) pros 8117 fixtures →
`data/built/backtest_valuebet_dataset.parquet`. ~60x a amostra do H3 original (84 fixtures).

### 20.2 W1 — Valor/edge de-vig em escala: **SEM EDGE** (confirma H3 com N grande)
Estratégia "aposta quando `p_model - p_fair(devig) > limiar"` (1x2 e O/U 2,5), split
cronológico honesto (metade antiga escolhe limiar, metade nova valida), bootstrap. ROI
negativo out-of-sample nos dois mercados em todo limiar testado; CLV real (abertura vs
fechamento) ~zero, sem assinatura de vantagem informacional; ROI piora no decil de edge mais
alto (>10%, efeito real e distinguível de ruído nesse bucket específico, mas crítico
corrigiu a narrativa original — não é gradiente suave, buckets intermediários são ruidosos).
Estratégia alternativa "maior edge absoluto" (não só o favorito do próprio modelo) performa
igual ou pior — descarta "o modelo só concorda com o favorito do book" como explicação.

**Bug real achado e corrigido**: `devig_methods.py::shin_devig()` tinha erro de fórmula
(`(pi/S)²` em vez de `pi²/S`) que fazia o solver `brentq` nunca achar raiz — caía sempre,
silenciosamente, no fallback `power_devig()`. Confirmado: shin ≡ power em 99.98-100% dos
casos reais testados. **Shin nunca foi genuinamente testado em nenhuma análise anterior do
projeto, incluindo o H3 original (§19.5)** — a "recomendação Shin" do H3 era, na prática, uma
recomendação de power. Corrigido nesta sessão (fórmula `pi²/S`); testes unitários do arquivo
não pegavam o bug (só checavam direção do ajuste, não que shin≠power) — teste de regressão
`enviesado/shin_e_genuinamente_diferente_de_power` adicionado. Reprocessado com Shin corrigido:
conclusão de fundo não muda (ROI na mesma faixa, correlação de edge shin-corrigido×power >0.998).

Decisão: **não construir feature de "aposta de valor automática"** em cima da saída atual
do modelo/mercado.

### 20.3 W2 — Confiança do modelo em O/U não ajuda; discordância favoritismo×placar_exato é artefato do empate
Hipótese "confiança alta = eco do mercado, sem edge" **rejeitada na forma literal**
(divergência `|p_model-p_fair|` é igual em alta/média confiança, Mann-Whitney p=0.60) — mas
filtrar "modelo escolhe O/U" por divergência alta também não gera ROI robusto out-of-sample
(overfitting de limiar confirmado por placebo de 5000 amostras: resultado do treino cai no
percentil 87 de sorte pura).

Discordância entre `favoritismo` e `placar_exato` é **sempre** o placar_exato escolhendo
Empate (nunca troca H↔A), em 71.22% dos 8117 jogos — crítico confirmou ser artefato
matemático de proximidade (jogos com margem `p_model[favorito]-p_model[D]` pequena), não um
achado independente do modelo. Teste extra do crítico: apostar **sempre** em Empate (todo
jogo, não só nos de discordância) tem ROI estatisticamente igual à estratégia mais elaborada
— reforça o achado de produto já documentado em §19.3 (mostrar P(empate)+odd justa ao lado
do argmax), sem justificar uma regra de decisão nova.

**Pista nova, não validada**: em jogos de discordância, o modelo esperava EV melhor pro
favorito (-1.8%) que pro empate (-9.87%), mas o oposto aconteceu na realidade — sugere
miscalibração LOCAL (favorito superestimado / empate subestimado, ~2.3pp cada) especificamente
em jogos de margem apertada, não capturada pelo ECE agregado (1.21%, §19.3). Não testado com
holdout — fica como hipótese pra próxima rodada, não é decisão de produto ainda.

### 20.4 W3 — Robustez estatística: os 2 casos "positivos" da análise de 4 ligas são ruído; achado extra de vazamento localizado
Bootstrap 20.000 reamostragens: os 2 ROI positivos da análise de 4 ligas (Brasileirão/
favoritismo +1.97%, La Liga/placar_exato +0.52%) têm IC 95% que engloba folgadamente zero —
indistinguíveis de sorte (p=0.75 e p=0.96). Correção de comparações múltiplas (Bonferroni e
BH/FDR, 17 testes): **0 sobrevivem**. O sinal agregado mais forte é NEGATIVO (pooled N=6122,
ROI -5.10%, IC 95% [-7.73%,-2.45%] exclui zero — consistente com o vig da casa, não com edge).

**Achado**: 93 dos 306 jogos do Brasileirão (análise de 4 ligas) são anteriores ao corte de
treino do modelo congelado (2025-07-01) — potencial vazamento treino/teste. Crítico confirmou
com query própria e **escopou corretamente**: localizado só no Brasileirão (calendário civil
brasileiro cruza o corte de julho; as 3 ligas europeias começam a temporada em agosto, 0 jogos
pré-corte, sem contaminação). Mesmo vazamento existe no `backtest_dashboard.html` principal
(mesmo `backtest_predictions.parquet`), mas impacto pequeno nas métricas de acurácia lá
(~0.3-0.7pp) — nota de rodapé adicionada ao dashboard e ao relatório de 4 ligas. **Não invalida
W1/W2** (excluem Brasil estruturalmente — sem odds de abertura na fonte pra essa liga).

Poder estatístico: detectar edge de 2% de ROI com 80% de poder precisaria de ~18.700 apostas
(temos 1.102 nas 3 ligas europeias limpas) — faltam ~17.500, equivalente a ~15 temporadas
adicionais por liga. Fora de alcance por acúmulo orgânico de dado nesse horizonte.

### 20.5 W4 — Lacuna de O/U no Brasileirão: fechável via API-Football, cron já corrigido
API-Football já suporta O/U pro Brasileirão — confirmado com 848 jogos já coletados com
mercado `gols_over_under` nos snapshots existentes (`data/odds/club_snapshots/`). Cota: plano
Ultra, 40.701/75.000 restante hoje, válido até 2026-08-19. `collect_odds_task.cmd` **já chama**
`collect_club_odds_forward.py` (commit `59b8ddb`, o gap do H2/§19.4 já foi corrigido antes
desta sessão) — cron rodando de fato, ~2-3% da cota diária. Gap adicional achado pelo crítico:
`collect_club_odds_forward.py` não anexa `model_snapshot` (diferente do coletor de seleção) —
recomendado como fast-follow, não implementado aqui (fora do escopo autorizado desta bateria).

Recomendação: não buscar fonte paga alternativa — deixar o coletor forward (já corrigido)
acumular Brasileirão prospectivamente; revisitar quando houver amostra suficiente.

### 20.6 Decisão
Nenhuma promoção de modelo, nenhuma feature nova de aposta/valor construída — nenhuma das 4
linhas achou edge robusto que justificasse. 1 bug de código real corrigido
(`devig_methods.py::shin_devig`, com teste de regressão novo). 1 nota de caveat adicionada ao
dashboard e ao relatório de 4 ligas (vazamento localizado no Brasileirão). Pista de
miscalibração local (favorito/empate em jogos de margem apertada) fica para validação futura
com holdout adequado — não é ação imediata. Scripts novos (`scripts/adhoc_*`) e relatórios
(`data/reports/adhoc_valuebet_w{1,2,3,4}/`) preservados; sem commit/push desta bateria (pendente
de decisão do dono).

## 21. Nosso modelo vs `/predictions` da API-Football em escala (8117 jogos, 2026-07-23/24)

Pedido do dono: avaliar se o endpoint nativo `/predictions` da API-Football (Poisson próprio +
forma/H2H, sem usar odds) valeria algo como sinal de "ensemble/convergência" na produção — testar
com TODAS as predições possíveis contra os mesmos mercados do nosso modelo, no mesmo conjunto de
jogos, e reportar qual performa melhor.

**Metodologia**: `scripts/fetch_predictions_baseline.py` coletou `/predictions?fixture=<id>` para
os 8117 fixtures do backtest congelado 2025 (`data/built/backtest_predictions.parquet`, 2025-01-11
a 2026-05-31, 26 competições) — coleta idempotente, retomável, ~8.100 chamadas de cota (folga
diária, sem impacto nos coletores de produção). `scripts/adhoc_compare_apifootball_predictions.py`
cruzou por `fixture_id` e rodou `research_clubs/protocol.py` (log-loss/Brier/ECE/acurácia
multiclasse) dos dois lados no MESMO conjunto de jogos. Relatório completo:
`data/reports/adhoc_compare_apifootball/RELATORIO_FINAL.md`.

**Resultado — 1X2 (único mercado com probabilidade calibrada dos dois lados), N=8117**:

| lado | log_loss | brier | ece | acurácia |
|---|---|---|---|---|
| nosso modelo (DC-NB) | 1,016 | 0,6087 | 1,22% | 49,1% |
| `/predictions` API-Football | 1,593 | 0,7031 | 14,05% | 41,5% |

Nosso modelo ganha em **26 de 26 competições** (log-loss), incluindo as 4 ligas-alvo do dono
(Brasileirão/Premier/La Liga/Serie A Itália, N=1474: 1,0026 vs 1,649). Confirma o piloto anterior
(n=40, log-loss vendor 2,0953 — pior que o palpite uniforme ln(3)≈1,0986). O/U total de gols: o
vendor não expõe probabilidade calibrada, só uma sugestão binária (`under_over`) presente numa
minoria das respostas — comparado honestamente só como acerto direcional (sem log-loss/Brier/ECE,
que exigiriam probabilidade). BTTS, dupla chance e gols esperados por time: **sem equivalente
probabilístico no vendor**, fora da comparação (não fabricada métrica sem dado do outro lado).

**Decisão**: **não construir nenhum badge de "ensemble/convergência"** com o `/predictions` nativo
em produção — o vendor não bate o nosso modelo em nenhuma métrica, em nenhuma das 26 competições
testadas. Achado descartado por evidência, não por suposição.

## 22. "Verificador de Bets" — odds por casa nos cards + seção Oportunidades Encontradas (2026-07-23/24)

Pedido do dono: já que `/odds` da API-Football diferencia por casa de apostas (hoje só usávamos a
MEDIANA entre casas, descartando a identidade), expor isso no produto — badge nos cards mostrando
quantas casas têm odd cadastrada pra aquele mercado, com modal listando em ordem decrescente e
destacando as que pagam acima/dentro da faixa de odd justa do modelo; e uma seção nova
"OPORTUNIDADES ENCONTRADAS" (entre "Funções Avançadas de Análise" e "Monte sua Seleção") listando
combinações mercado×casa com EV positivo segundo o modelo, ordenadas decrescente, com explicação de
o que é EV e reforço de que não é garantia de lucro.

**Achado de arquitetura**: o backend de produção (Render) nunca chama a API-Football nem lê os
JSONL locais dos coletores forward (rodam via Task Scheduler numa máquina separada,
`data/odds/` é gitignored). Solução: sincronizar o snapshot por-casa mais recente numa tabela nova e
pequena no Neon (precompute, nunca blob — regra de ouro do projeto).

**Implementado**:
- `scripts/fetch_odds.py::parse_fixture_odds_by_bookmaker` — função nova, aditiva (não altera
  `parse_fixture_odds`/mediana existente), usa `bm.get("name")` (antes descartado) pra preservar
  odd por casa. Escopo: os 9 mercados já em `BET_MAP` (resultado, gols O/U, btts, escanteios×3,
  cartões×3) — sem expandir mercados nesta rodada.
- `collect_odds_forward.py`/`collect_club_odds_forward.py` — gravam `odds_by_bookmaker` no
  snapshot JSONL (campo novo, lado a lado da mediana) e sincronizam com 2 tabelas novas no Neon
  (`odds_bookmaker_latest`, `club_odds_bookmaker_latest`; `fixture_id` PK, JSON, `updated_at`) via
  `upsert_df`. Rodados manualmente 1x pra popular dado real (3 fixtures de seleção + 31 de clube
  sincronizados, ~35 chamadas de cota).
- `app/services/odds_bookmaker_service.py` + `GET /api/odds/bookmakers?fixture_id=&scope=` — lê a
  tabela Neon, devolve por mercado/outcome a lista casa+odd já ordenada decrescente. Não recalcula
  odd justa (já vem do `/predict`).
- Frontend: `fixtureId`/`scope` agora chegam até `AnalysisResultsView` (gap real — a página não
  propagava, embora `resolvedFixtureId` já existisse). `BookmakerOddsBadge.tsx` (badge+tooltip+modal
  via Radix, destaque verde para odd ≥ `faixa_odd_justa.min`) plugado nos cards de Resultado, Ambas
  Marcam, Gols (só total da partida — API-Football não expõe O/U por time), Escanteios e Cartões (3
  cards cada). `OpportunitiesSection.tsx` — nova seção entre `AnalysisResultsView` e "Monte sua
  Seleção" em `page.tsx`, calcula `EV = odd_oferecida × p_model − 1` no cliente cruzando a resposta
  do endpoint novo com `prediction.odds` já existente, filtra só EV>0, ordena decrescente, texto
  educativo de EV + jogo responsável, não renderiza nada quando não há oportunidade real.

**Testado**: `tsc --noEmit`/`npm run build` limpos; validado visualmente contra fixture real
(Botafogo x Vitória, clube) — badges só nos cards certos, modal ordena e destaca corretamente,
seção de oportunidades listou linhas reais com EV>0.

**Nota honesta de cronograma**: cobertura de odds por-casa hoje é pequena (só os fixtures dentro da
janela de retenção de 1-14 dias já processados manualmente durante o teste); o cron de produção
(a cada ~3h) povoa as tabelas novas prospectivamente a partir do próximo deploy — sem retrofit
retroativo possível (dado por-casa nunca foi persistido antes desta sessão).

## 23. [RETIRADO] Bateria de Experimentos: Hipóteses A, B e C (v1, 2026-07-27) — ver §24

A versão original desta seção (escrita em 2026-07-27, nunca commitada) foi **retirada em
2026-07-28** após revisão crítica. Motivo: `scripts/hypothesis_testing_suite.py` não usava o
`Predictor` de produção (usava um sigmoid ad-hoc sobre média de gols, sem Elo/GAP/calibração) e
gerava odds 100% sintéticas a partir da própria probabilidade do modelo (`odd = (1/p_model) *
multiplicador_fixo`) — circular por construção, então o "alfa" aparecia garantido
independentemente de qualquer edge real. Rodava também in-sample sobre uma base
(`club_features_enriched.parquet`, 21.130 jogos/4 torneios) inconsistente com a produção atual
(272.918 jogos/72 torneios), sem CV temporal (violando o gate §6), e a tabela por competição não
tinha piso de amostra (linhas de n=1 reportando 100% de acerto). Os números que estavam registrados
aqui (§23.1-23.3) também não batiam com os CSVs que o próprio script gerou (ex.: doc dizia Premier
League ROI +16.96%, CSV real do script dizia +2.34%) — divergência nunca explicada.

**Contradição não sinalizada na época**: esta bateria concluía "alfa garantido"/edge positivo,
contradizendo diretamente a bateria de valor/CLV já registrada em §20 (dados reais, 8117 fixtures,
bootstrap 20k + correção Bonferroni/BH-FDR), que concluiu **sem edge robusto em nenhuma linha
testada**. Ninguém comparou os dois antes de promover §23 ao doc-mestre.

`docs/RELATORIO_HIPOTESES_A_B_C.md` (v1) e `scripts/hypothesis_testing_suite.py` foram mantidos no
repo com aviso de descarte (rastreabilidade), não apagados. Reexecução honesta (modelo de produção
via `Predictor.predict_from_row`, odds reais de `data-test/*.csv`, split point-in-time via modelo
congelado) registrada em **§24**.

## 24. Hipóteses A, B e C (v2, honesta) — modelo de produção real + odds reais (2026-07-28)

Reexecução completa das Hipóteses A/B/C do §23, desta vez com o `Predictor` de produção real
(`predict_from_row`, artefato congelado `model_artifacts_clubes_2025frozen/`, cutoff
2025-07-01, sem vazamento) e odds 100% reais (`data-test/*.csv`, football-data.co.uk) — nada
fabricado. Relatório completo em `docs/RELATORIO_HIPOTESES_A_B_C_v2.md`.

### 24.1 Escopo real (limitação a comunicar, não esconder)

Esta máquina só tem 4 competições de clube no espelho local (`data/club_raw_cache.sqlite`:
Brasileirão A/B, Premier League, Champions League — 21.130 jogos), não as 83 competições/272.918
jogos do artefato de produção atual (retreinado em outra máquina, 2026-07-22, §19.8). Das 4, só
**Premier League** (380/380) e **Brasileirão Série A** (342/380) têm odds reais em `data-test/`.
**N final: 722 partidas reais, temporada 2025/26.** Backfill das competições faltantes
(`mirror_club_cache.py`) iniciado em 2026-07-28 — ver §24.5.

**Modelo usado**: `model_artifacts_clubes_2025frozen/` já commitado (cutoff 2025-07-01,
**250.682 jogos / 5.365 times** — treinado na base completa em outra máquina). Um retreino local
chegou a sobrescrevê-lo por uma versão de apenas 19.574 jogos/396 times (a base local parcial);
isso foi detectado e **revertido**, e todos os números abaixo foram regerados com o artefato bom.
**Lição**: `backtest_train_frozen_model.py` lê o `club_features_enriched.parquet` local — rodá-lo
numa máquina com base parcial degrada silenciosamente o artefato congelado. Confira
`meta.json["n_train"]` antes e depois.

### 24.2 Hipótese A — Alfa de cotação (real, robusto)

Comparar a melhor odd real (`Max`) vs a pior odd individual real disponível, no pick do modelo:
**Alfa = +7.15%** IC95%[+6.05%,+8.31%] no 1x2 (N=722) e **+2.12%** IC95%[+1.78%,+2.46%] no O/U
2.5 (N=380, PL). Por liga: Brasileirão +3.11% [+2.54%,+3.74%], Premier League +10.78%
[+8.82%,+12.87%]. Pooled (1102 apostas): **+5.41%** [+4.67%,+6.21%]. Todos excluem zero — é
dispersão estrutural de mercado, estatisticamente sólida. **Não é vantagem do modelo**, é
vantagem de comparar casas (mensagem defensável: "escolher a melhor cotação reduz a perda
esperada", não "dá lucro" — o ROI segue negativo na melhor casa em 3 dos 4 recortes).

### 24.3 Hipótese B — Modelo vs 3 perfis de apostador (sem edge robusto)

Perfis pedidos originalmente (favoritista, emocional-por-gols = sempre Over 2.5 já que BTTS não
existe em `data-test`, faixa de odd 1.70-2.20) comparados ao pick do modelo, mesma fonte de
preço (`book="Avg"`) pra isolar seleção de comparação de casas. Bootstrap + Bonferroni/BH-FDR.

**O benchmark não é zero (ver §25.1)**: com vig de 6.05%, o ROI esperado de qualquer apostador
sem vantagem é **−5.71%**. Resultados (pooled): modelo_1x2 −8.51% [−15.77%,−1.17%] = **−0.76σ do
benchmark, não significativo**; favoritista −6.35% (inclui 0); faixa_odd −11.57%; modelo_ou
−11.40%; emocional_sempre_over −4.24% (inclui 0). Por liga: Premier League −15.04%
[−24.57%,−5.45%] = −1.99σ (limítrofe, não sobrevive correção); Brasileirão −1.24% (inclui 0).

**Nada aqui é conclusivo**: detectar edge de 2% exigiria ~19.400 apostas e temos 722. Registrar
sem maquiar: nesta amostra o pick do modelo teve ROI **pior** que o do favoritista (−8.51% vs
−6.35%), mas com SE ~3.7pp os dois são indistinguíveis. **Corrobora §20 ("sem edge robusto"),
não contradiz** — ao contrário do §23 (v1, retirado). Não usar para claim de "modelo bate
apostador comum".

### 24.4 Hipótese C — Desagregação por liga/ano (piso N≥100, sem linha de N=1)

Por liga: Brasileirão N=342, winrate 50.9%, ROI −1.24% IC95%[−12.12%,+9.56%]; Premier League
N=380, winrate 46.8%, ROI −15.04% IC95%[−24.57%,−5.45%] (exclui zero, mas fica a −1.99σ do
benchmark de −5.37% dessa liga — limítrofe, ver §25). Por ano: como só há uma temporada real
disponível (2025/26), a "desagregação por ano" é essa mesma temporada cortada pelo calendário
civil (2025: N=528, ROI −1.79%, inclui 0; 2026: N=194 = meia temporada, ROI −26.78%) — **não é
teste de consistência multi-temporada** como o §23 (v1) fabricou ("10 de 11 anos lucrativos,
2010-2026").

### 24.5 Pendências

- `mirror_club_cache.py` (backfill das ~79 competições faltantes) bloqueado nesta máquina por
  falta de credenciais: precisava de `APIFOOTBALL_KEY` (copiada de `.env` da raiz pra
  `backend/.env` nesta sessão — cota OK, 67.530/75.000 restantes, assinatura válida até
  2026-08-19) **e** de `DATABASE_URL` real do Neon (aqui `backend/.env` só tem
  `sqlite:///./dev_verify.db`, um stand-in local de dev sem a tabela `club_match_detail_cache`)
  — aguardando o dono adicionar a connection string real.
- Assim que o backfill terminar: rerodar `build_clubs_dataset.py --stage all` →
  `backtest_train_frozen_model.py --cutoff 2025-07-01` → `backtest_odds_ingest.py` →
  `backtest_match_games.py` → `backtest_generate_predictions.py` → os 3 scripts
  `adhoc_hipotese_{a,b,c}_*.py` — mesma cadeia desta rodada, só com a base completa (72
  torneios), que deve ampliar bastante o N de todas as três hipóteses (mais ligas cobertas por
  `data-test/`, incluindo ligas continentais se houver fonte equivalente).

## 25. Diagnóstico modelo × mercado — o benchmark correto, o vig e o poder estatístico (2026-07-28)

Gerado por `backend/scripts/adhoc_diagnostico_modelo_vs_mercado.py` sobre as mesmas 722 partidas
do §24, comparando a probabilidade do modelo com a **probabilidade do próprio mercado de-vigada**
(Shin, `devig_methods.py`). Saída em `data/reports/diagnostico_modelo_vs_mercado.csv`.
**Esta seção reenquadra §19, §20 e §24 — leia antes de propor qualquer hipótese de valor/EV.**

### 25.1 O benchmark não é zero — é o vig

Vig (overround) médio das odds: **6.05%**. Logo o ROI esperado de *qualquer* apostador sem
vantagem nenhuma é **−5.71%**. Comparar ROI contra zero (erro cometido na 1ª leitura do §24)
faz um modelo perfeitamente são parecer quebrado.

| Recorte | ROI observado | ROI esperado s/ edge | Distância |
|---|---:|---:|---:|
| Pooled (722) | −8.51% | −5.71% | **−0.76σ** |
| Brasileirão A (342) | −1.24% | −6.08% | +0.86σ |
| Premier League (380) | −15.04% | −5.37% | −1.99σ (limítrofe) |

O agregado está a **0.76 desvio-padrão** da teoria — indistinguível de "sem edge". O caso mais
negativo (Premier League) é limítrofe e não sobreviveria à correção de múltiplas comparações;
lê-lo como "o modelo é anti-preditivo na PL" seria sobreajustar ruído.

### 25.2 O modelo não está quebrado: captura ~78% da informação do mercado

| | log-loss | Brier | ECE | Acurácia |
|---|---:|---:|---:|---:|
| Nosso modelo | 1.0200 | 0.6123 | 0.0207 | 48.8% |
| Mercado (de-vig Shin) | 0.9975 | 0.5988 | 0.0167 | 50.6% |

Referência: chute uniforme = ln(3) = 1.0986. O mercado ganha 0.1011 sobre o uniforme; nós
ganhamos 0.0786 → **capturamos ~78% da informação que o mercado inteiro precifica**. ECE de
0.0207 confirma modelo **bem calibrado** (sem bug de calibração). Coerente com §21 (ganhamos do
`/predictions` da API-Football em 26/26 competições): somos bons *entre modelos*; o mercado é o
agregador mais eficiente que existe e continua à frente. **Para lucrar não basta ser bom — é
preciso ser melhor que o mercado por mais que o vig.**

Observação metodológica relevante: quando o artefato congelado foi (por engano) degradado para
uma base parcial, o log-loss **piorou** (1.0219) mas o ROI **melhorou** (−5.85%) — evidência
direta de que, com N desta ordem, **ROI é dominado por ruído e não serve para ranquear modelos**.
Use log-loss/ECE para qualidade de modelo e CLV para habilidade de aposta.

### 25.3 Poder estatístico: as baterias anteriores eram subdimensionadas

- Detectar edge de **2%** com 80% de poder: **N ≈ 19.400 apostas**. Temos 722 (§24) / 8.117 (§20).
- Detectar edge de **5%**: N ≈ 3.110.

**Nenhuma conclusão de §24 (B e C) tinha poder para ser conclusiva em qualquer direção.** O
gargalo do projeto é **dado**, não modelagem — refinar método com N desta ordem é desperdício.

### 25.4 Achado novo: eficiência de mercado difere por liga (hipótese aberta)

| Liga | % da informação do mercado capturada | Acurácia modelo vs mercado |
|---|---:|---|
| Brasileirão Série A | **83%** | 50.9% vs 51.8% |
| Premier League | **71%** | 46.8% vs 49.5% |

Hipótese (não confirmada — N=342/380, pode ser ruído): a Premier League é o mercado mais
eficientemente precificado do futebol; ligas com menos atenção quantitativa internacional
(Brasileirão, séries inferiores, ligas menores) são onde uma vantagem informacional local teria
mais chance de existir. **Se há edge em algum lugar, não é onde estávamos olhando.** Testável
assim que o backfill de competições (§24.5) e as temporadas históricas ampliarem a base.

### 25.5 Consequências práticas

1. **Métrica primária passa a ser CLV** (closing line value), não ROI: converge com N muito
   menor. Bloqueado hoje porque o histórico de odds não é persistido (só o snapshot mais recente
   vai pro Neon e os `.jsonl` do Render são efêmeros) — é o fix nº1 da migração pro Drive (§26).
2. **Mensagem comercial defensável** é a do §24.2 (alfa de comparar casas, robusto) e a que já
   está no ar em `/desempenho` ("o modelo perde menos"), **não** promessa de lucro.
3. **Três baterias independentes (§19, §20, §25) convergem**: bater o mercado provavelmente não é
   o negócio. O negócio é o usuário perder menos, decidir melhor e pagar menos vig.

## 26. Google Drive como repositório oficial de dados (2026-07-28, provedor trocado 2026-07-30)

Decisão do dono: **um armazenamento externo passa a ser a fonte da verdade de todos os dados**;
no Neon fica só o que precisa de query em runtime. Motivador concreto: nesta sessão o backfill de
83 competições ficou inacessível porque o dado existia **só em outra máquina**, o
`club_features_enriched.parquet` local divergia da produção (21k/4 torneios vs 273k/72), e o
histórico de odds do Render é efêmero (impede medir CLV, §25.5).

**Nota de provedor (2026-07-30)**: a escolha original foi Zoho WorkDrive — desenhada e
implementada, mas **nenhuma credencial chegou a ser criada e nenhum dado foi enviado**. O dono
trocou a decisão para **Google Drive** antes da ativação; a troca foi só de adapter
(`app/core/datastore.py`), sem qualquer migração de dado necessária. Onde este texto ainda disser
"WorkDrive" fora desta seção, é resquício textual — o provedor vigente é Google Drive.

### 26.1 Regra de ouro

**Nenhum dado pode ter sua ÚNICA cópia numa máquina local.** O diretório local é cache derivado
e descartável: apagar `backend/data/` e rodar `datastore_sync pull` deve restaurar tudo.
Google Drive é armazenamento de **arquivos** — não dá `SELECT` nele; dado que precisa de query em
runtime continua no Neon.

### 26.2 Arquitetura (3 camadas)

- **Google Drive** — raw caches, datasets de treino, `data-test/`, histórico de snapshots de odds,
  artefatos (todas as versões), relatórios, `historico_completo.json`.
- **Neon** — usuário/monetização, agregados `*_agg`, `odds_bookmaker_latest`/`*_registry`.
  Blobs (`match_detail_cache`, `club_match_detail_cache`) devem **migrar** pro Drive.
- **Cache local** — efêmero, gitignored, regenerável.

**Artefatos de produção: modo híbrido** (decisão explícita do dono). `model_artifacts{,_clubes}/`
(120 MB) **continuam no git** — deploy sem dependência externa e boot rápido — **e** são
espelhados no Drive como fonte da verdade/versionamento. Evita que uma indisponibilidade do
Drive derrube um deploy de produção.

### 26.3 Implementação

- `backend/app/core/datastore.py` — `DataStore` (Protocol) + `LocalStore` + `GoogleDriveStore` +
  `get_datastore()`, trocável por `DATA_STORE=local|gdrive`. Mesmo padrão dos adapters de
  pagamento/nota fiscal (nunca hardcode o provedor num domínio). `fetch()` é a função que
  scripts/serviços devem usar no lugar de caminho hardcoded. Auth via Service Account (JWT,
  `google-auth`), sem interação humana — a pasta do Drive precisa ser compartilhada (papel
  Editor) com o `client_email` da service account. Upload em blocos via protocolo resumível do
  Drive (não lê o arquivo inteiro em memória — importa pro `club_raw_cache.sqlite`, ~7 GB hoje).
- `data/MANIFEST.yaml` — registro declarado de cada dataset (caminho, camada, dono, cadência,
  se é crítico em runtime). **Todo dado novo deve ser registrado aqui.**
- `backend/scripts/datastore_sync.py` — `status` / `push` / `pull` / `verify`, incremental por
  sha256 (`backend/data/.datastore_state.json`). `verify` consulta o **remoto de verdade**, não o
  estado local — é o que faz cumprir a regra de ouro.

**Estado atual (2026-07-30)**: validado ponta a ponta com `DATA_STORE=local` (push incremental,
pull preservando subpastas, verify). Dois bugs reais pegos no teste e corrigidos: o `pull`
achatava `reports/performance/x.json` em `reports/x.json`, e o `verify` confiava no estado local
(daria "tudo certo" falso com remoto vazio). `status` hoje acusa **~8 GB / 1255 arquivos** com
cópia única em máquina local — cresceu bastante desde 2026-07-28 (952 MB) por causa da coleta do
§28 (expansão de competições, lesões, odds históricas, contexto de elenco). `GoogleDriveStore`
em si ainda **não foi executado contra a API real** — só contra `LocalStore` — porque a credencial
ainda não existia quando foi escrito.

### 26.4 Pendente — credenciais do Google Drive

Faltam (criar em `console.cloud.google.com`, colocar em `backend/.env`):

1. Criar/escolher um projeto no Google Cloud e ativar a **Google Drive API**.
2. `IAM & Admin → Service Accounts` → criar uma service account → gerar uma **chave JSON**.
3. No Google Drive normal (não o do projeto — o pessoal/organizacional de quem administra),
   criar (ou escolher) uma pasta e **compartilhá-la** com o e-mail da service account (campo
   `client_email` do JSON, formato `algo@projeto.iam.gserviceaccount.com`), papel **Editor** —
   sem isso a service account não enxerga nada (ela não tem Drive próprio com cota).
4. Pegar o ID da pasta na URL: `https://drive.google.com/drive/folders/<ID>`.

Variáveis: `GOOGLE_SERVICE_ACCOUNT_JSON` (caminho pro arquivo) **ou**
`GOOGLE_SERVICE_ACCOUNT_JSON_B64` (o JSON inteiro em base64 numa linha só — útil pra plataformas
que só aceitam env var, tipo Render), e `GOOGLE_DRIVE_FOLDER_ID` (o ID do passo 4).
Com as chaves no lugar, o único passo é `DATA_STORE=gdrive python -m scripts.datastore_sync push`.

## 27. Pesquisa ampla de novas variáveis/dados/abordagens (2026-07-24)

Dono pediu levantamento amplo de candidatos a nova variável/dado/abordagem capazes de aumentar a
capacidade preditiva. Auditoria interna prévia (3 agentes Explore): modelos/features de produção,
histórico completo de ~60 hipóteses já testadas/reprovadas, fontes de dado/endpoints já avaliados —
usada como bloco de contexto para não repetir pesquisa já feita (regra de ouro do CLAUDE.md).

**Execução**: 7 agentes de domínio em paralelo (papers acadêmicos, empresas de análise, blogs
técnicos, repositórios open source, competições Kaggle, engenharia de ML aplicada, fontes de dados
comerciais/gratuitas), consolidados em `backend/docs/PESQUISA_VARIAVEIS_EXTERNAS.md`. Comitê técnico
de 3 revisores independentes (rigor estatístico/viés, viabilidade de dados/engenharia, estratégia/
roadmap) revisou o material — round 1 completo e independente; round 2 (cross-review formal ponto a
ponto) foi interrompido pelo limite semanal de subagentes da plataforma, e a síntese de convergência
foi feita diretamente pelo orquestrador (sem divergência de fato encontrada entre os 3 — nota de
honestidade metodológica registrada no relatório final).

**Resultado**: `backend/docs/RELATORIO_NOVAS_VARIAVEIS.md` — 6 seções (auditoria, ~15 novas
variáveis curadas, ranking de prioridade de 24 candidatos, 5 hipóteses inéditas com plano de
validação, tabela de 14 fontes de dados avaliadas, roadmap em 4 fases). Top 5 recomendado pra
começar (custo de dado zero, reusa infraestrutura já existente): calibração Dirichlet no 1X2,
calibração Beta em chutes, job de coleta `/injuries` de clube em massa, auditoria leakage-aware da
cascata chutes→escanteios→cartões, monitoramento PSI de drift. Achado mais forte com evidência
externa (mas caro de implementar): Compound Poisson para escanteios com backtest real contra odds
HKJC (Sharpe 3,07 vs 1,52 do Poisson simples). Confirma-se o "muro de dados" (xT/OBV/VAEP/Packing
Rate/xGOT bloqueados por falta de coordenadas x/y na API-Football) e vários ratings "alternativos"
ao Elo (SciSkill, Opta Power Rankings, valor de mercado de elenco) descartados por confounding com
força de time já capturada pelo Elo — mesmo padrão que já reprovou xG 3x.

**Decisão registrada**: nenhuma variável foi implementada ou testada sob o gate §6 nesta pesquisa —
é backlog priorizado, aguardando decisão do dono sobre o que entra em teste real primeiro.

**Reenquadramento posterior (§25)**: o diagnóstico de 2026-07-28 concluiu que o gargalo do projeto é
**dado, não modelagem** (poder estatístico: detectar edge de 2% exige N≈19.400). Isso não invalida o
ranking desta pesquisa, mas muda a leitura: os candidatos que **trazem dado novo** (job `/injuries`,
cobertura de odds forward para CLV) sobem de prioridade sobre os que só refinam método
(calibração Dirichlet/Beta). O PLANO 7 (2026-07-30) age nessa ordem.

## 28. Retomada da coleta: pipeline quebrado, odds destravadas e dívida documental (2026-07-30)

Auditoria do repositório e da infraestrutura de coleta antes de retomar o uso da cota diária.
Achou três problemas silenciosos e um desbloqueio grande. **Assinatura API-Football (Ultra) vence
2026-08-19** — 20 dias no momento desta seção; o plano priorizou o que é irreversível.

### 28.1 O pipeline diário estava meio-morto havia 16 dias

A tarefa `\PrevisaoJogos\PrefetchWorldCup` tem `ExecutionTimeLimit = PT3H`. Ela inicia 06:30 e vinha
sendo **morta às 09:30** (`LastTaskResult 267014` = SCHED_S_TASK_TERMINATED) ainda dentro de
`prefetch_wc_data.py --all-nations`. Os passos seguintes do `prefetch_wc.cmd` nunca chegavam a rodar:
`build_scorer_model`, `build_shots_prop_model` e `precompute_aggregates`. Evidência: no log
`data/state/prefetch_wc.log` o último marcador `----- precompute agregados` é de **14/07 12:37**, e
os mtimes de `model_artifacts/scorer_model.joblib` e `shots_prop_model.joblib` estavam congelados na
mesma data. Ou seja, **os agregados servidos ao site (árbitro/minutagem/quadrantes) ficaram 16 dias
parados** e ~5k de cota/dia eram gastos sem concluir nada.

Duas causas no `prefetch_wc_data.py`, ambas corrigidas:

1. **Um round-trip ao Neon por fixture candidata** (`cache_get`). Com 249 seleções × 17 temporadas
   isso virava dezenas de milhares de round-trips — o custo era latência de banco, não de API. Agora
   as chaves do espelho local são carregadas de uma vez (`raw_cache.local_keys()`, nova).
2. **Re-listagem cega do histórico inteiro todo dia** (~4.200 chamadas), com o histórico já saturado.
   Agora há estado em `data/state/wc_seasons_done.json`; a temporada corrente e a anterior nunca são
   marcadas como exauridas.

Correções estruturais: `scripts/rebuild_models.cmd` (novo) separa rebuild de coleta — **rebuild não
pode depender de coleta terminar** — como tarefa `\PrevisaoJogos\RebuildModels`;
`scripts/prefetch_wc_full.cmd` (novo) faz a varredura histórica semanalmente enquanto o run diário
usa `--floor 2024`; e o `ExecutionTimeLimit` da tarefa sobe para PT8H.

### 28.2 Odd histórica não existe — e dois filtros estrangulavam a coleta forward

Verificado por sonda direta: `/odds?fixture=<jogo de 2025>` devolve 0 resultados e
`/odds?league=39&season=2025` devolve 0 resultados. **A API-Football não serve odd retroativa.** Só
dá para acumular para a frente, então cada dia não coletado é perda permanente — o que torna os dois
bugs abaixo mais caros do que pareciam:

- `collect_club_odds_forward.py` filtrava `LEAGUES` casando o **nome** da liga contra as chaves de
  `tournament_weights` do `meta.json`. Os rótulos vêm de fontes diferentes (`"Serie A (Italia)"` vs
  `"Serie A Italia"`, `"Championship (Inglaterra)"` vs `"Championship"`, `"Super Lig"` vs
  `"Süper Lig"` com mojibake). Medido: **28 das 83 ligas** entravam. Ficavam de fora Serie A italiana,
  Championship, Ligue 2, Saudi, J1, K League, Colômbia, Chile, Peru, Uruguai, FA Cup. Filtro removido:
  odd de liga ainda não treinada custa 1 requisição de uma cota ~90% ociosa, e perder a janela é
  irreversível.
- `collect_odds_backfill.py` importava `target_league_ids()`, que lista os subdiretórios de
  `data/raw/fixtures/` — **41 diretórios, todos de seleção**. As 83 competições de clube eram
  ignoradas: `odds_history.sqlite` tinha **12 fixtures** depois de dias rodando. Agora tem
  `--scope {selecao,clube,ambos}` (default `ambos`, 124 ligas) e um pré-filtro de fixtures já
  coletadas no dia — sem ele, as 8 execuções diárias da tarefa `CollectOdds` re-baixavam a janela
  inteira toda vez.

### 28.3 O desbloqueio: 107.095 partidas com odds reais, custo zero de cota

`data/MANIFEST.yaml` registrava que o domínio `football-data.co.uk` estava inacessível e que
`scripts/fetch_historical_odds.py` "nunca rodou contra a fonte real". **O bloqueio era da máquina
onde o §24 rodou, não do domínio**: da máquina de coleta o download funciona. Resultado: 305 arquivos
(33 MB, 16 temporadas × 22 divisões europeias) em `data-test/historical/`.

| | antes | depois |
|---|---:|---:|
| partidas com odds 1X2 | 722 | **107.095** |
| partidas com Max/Avg e O/U 2.5 | 380 | **37.243** |

O §25.3 estabelece que detectar um edge de 2% com 80% de poder exige **N≈19.400**. O gargalo
estatístico que tornava inconclusivas as conclusões de §24.3 e §24.4 **deixa de existir para 1X2 e
O/U**. Reexecutar as Hipóteses B e C sobre esta base é a próxima tarefa de pesquisa óbvia — e agora
com poder para dar resposta em qualquer direção, inclusive negativa.

### 28.4 Coletas novas

- **`/injuries` em massa** (`scripts/collect_injuries.py`, novo). O endpoint devolve a liga inteira
  numa resposta **sem paginação** (Premier League 2025 = 3.417 registros em 1 chamada) e cada registro
  vem amarrado a um `fixture_id` — **é retroativo, serve para treinar**, não é só "quem está fora
  hoje". Varredura completa: **868 chamadas → 175.595 registros, 27.551 fixtures, 746 times**.
  Cobertura **desigual, e isso importa**: grandes europeias a partir de 2020/21, Brasileirão só a
  partir de 2024, Libertadores quase nada. Qualquer feature derivada precisa carregar a flag
  `inj_has_data` junto — "0 desfalques" por falta de cobertura não é "elenco cheio".
- **Expansão de 83 → 150 competições de clube.** `GET /leagues` enumerado e filtrado por cobertura
  real (`coverage.fixtures.statistics_fixtures` **e** `lineups`, o mínimo que as features exigem):
  108 competições não coletadas, das quais **67 sobrevivem à curadoria** (excluídas as de seleção —
  pertencem ao pipeline `prefetch_wc_data.py` — além de futebol feminino e categorias de base, cujas
  dinâmicas contaminariam o modelo masculino de clube). Entram como constante **separada**
  `LEAGUES_EXPANSION_20260730`, atrás de `--include-expansion`/`--only-expansion`: **coletar não é
  treinar**; a inclusão no artefato de produção passa pelo gate §6 numa decisão à parte. Rodada em
  `--local-only` — `data/MANIFEST.yaml` lista `club_match_detail_cache` em `neon_to_migrate`, então
  os blobs novos vão só para o espelho SQLite, não engordam o Neon.

### 28.5 Achado que economiza cota: `coach` e `formation` já estavam no blob

O `RELATORIO_NOVAS_VARIAVEIS.md` supunha que troca de técnico exigiria `/coachs` e continuidade de
elenco exigiria `/transfers` (~11k chamadas). **Não exige**: `lineups[].coach.id`,
`lineups[].formation` e `lineups[].startXI[].player.id` já estão dentro de cada blob em
`club_raw_cache.sqlite` desde sempre. `scripts/build_squad_context_features.py` (novo) deriva de
graça, sobre as 273 mil partidas já coletadas: mandato do técnico (jogos e dias), técnico
recém-chegado, troca no último jogo, estabilidade de formação, continuidade de escalação (Jaccard
entre escalações consecutivas) e tamanho do núcleo fixo.

**Todas point-in-time estritas** — só jogos anteriores; a escalação da própria partida nunca entra,
porque o blob só existe depois do jogo. A única exceção é declarada e isolada em colunas próprias
(`*_inj_*`, lista de desfalques da própria partida, que é informação pública pré-jogo e é assim que
seria usada em produção).

### 28.6 Outros bugs achados no caminho

- `prefetch_clubs_parallel.py::budget_ok_locked` comparava o header
  `x-ratelimit-requests-remaining` (**por minuto**, teto 450) contra `--margin 500`: a condição era
  verdadeira já na primeira chamada e o script parava alegando `LIMITE_DIARIO` sem baixar nada. É o
  mesmo bug documentado em `scripts/quota_tracker.py:8-20`, que tinha escapado neste arquivo.
- `prefetch_clubs._local_put_batch` tinha `except Exception: pass`. Um `database is locked` (leitura
  longa concorrente) descartava o lote inteiro de fixtures recém-baixadas **sem uma linha de log** —
  dado pago em cota e perdido em silêncio. Agora tem retry com espera crescente e loga a falha.
- **Gasto duplicado de cota**: `app/main.py` subia uma thread de 3h no import que chamava os mesmos
  coletores forward que a tarefa Windows `CollectOdds` já roda a cada 3h — e no Render seria um loop
  por worker, escrevendo nas mesmas tabelas do Neon ao mesmo tempo. Agora atrás de
  `ENABLE_INPROC_SCHEDULER` (default **off**). A rota `GET /api/cron/refresh-upcoming` (protegida por
  `CRON_TOKEN`) segue disponível para acionamento externo.

### 28.7 Dívida documental de 24-26/07 (código que entrou sem registro)

- **SGP (Same Game Parlay)** — `app/domains/bets/markets.py`, commit `10434d3`. Particiona as pernas
  da aposta: as de placar (1X2/BTTS/Over-Under) são resolvidas por **soma exata sobre a matriz
  conjunta Dixon-Coles** `snapshot["gols"]["matrix"]` (`markets.py:174-203`), o que trata redundância
  entre pernas e detecta combinação impossível (HTTP 400); as de contagem (escanteios/cartões/chutes)
  passam por uma **cópula gaussiana** (`markets.py:103-131`). **Limitação conhecida: a matriz Σ da
  cópula é hardcoded e chutada** (`markets.py:94-100` — 0,22 / 0,55 / 0,30 / 0,18 / 0,05), não
  estimada dos dados; é candidata natural a uma bateria de validação. Segunda limitação: análises
  salvas **antes** de `10434d3` não têm o campo `matrix` e caem no fallback de independência. Não há
  UI própria — o SGP aparece só como a odd combinada dentro de "Monte sua Seleção".
- **RBAC** — commits `1d73660`/`380bf22`. Papéis hoje: `user`, `partner`, `owner`, `manager`;
  `admin`/`superadmin` foram removidos do enum **sem migração de dados**. O enum é VARCHAR
  (`native_enum=False`, `app/domains/enums.py:1`), então o schema não quebra, **mas qualquer linha
  em Neon com `role='admin'` vira `LookupError` ao carregar**. *Verificação pendente do dono:*
  `SELECT role, COUNT(*) FROM users GROUP BY role`.
- **Carteira** — `app/domains/wallet/service.py:28-37,77-83` força `available_balance = 100.00` para
  `owner`/`manager`/`partner` a cada leitura **e** a cada transação. Efeito prático: parceiro nunca
  gasta crédito de verdade, e o débito da análise fica registrado em `CreditTransaction` mas o saldo
  volta a 100 na mesma operação. *Confirmar com o dono se é intencional.*
