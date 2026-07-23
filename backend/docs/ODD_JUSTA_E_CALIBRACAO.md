# Odd justa, calibração vs mercado e vitrine de desempenho — achados e decisões

**Data:** 2026-07-23 · Sessão de vitrine de métricas + odd justa + incorporação à produção.
Documento-mestre; complementa `DOCUMENTACAO_CENTRAL.md`, `PESQUISA_CLUBES.md §7` e
`data/reports/performance/RESUMO_DESEMPENHO.md`.

## 1. O que foi feito
1. **Vitrine de desempenho** (`/desempenho` + `GET /api/performance` + dashboard gerencial):
   números reais de backtest out-of-sample, honestos, com jogo responsável em destaque.
2. **Odd justa REAL / break-even**: medimos, com odds reais, o quão bem o modelo identifica a odd
   justa (viés/precisão) em 1x2, Over/Under 2,5 e handicap asiático.
3. **Incorporação à produção**: correção de viés por mercado (`bias_correction.joblib`) + faixa de
   odd justa ±5% (95/100/105%) uniforme nos cards. Frontend inalterado; só recalibra números.
4. **Infra de coleta**: job `collect_odds_backfill.py` (janela de retenção, todos os mercados,
   `odds_history.sqlite`, agendado a cada 3h) + skill `validar-mercado-com-odds` pra recalibrar
   qualquer mercado novo quando chegar odd real.

## 2. Achado central (honesto)
O modelo **identifica a odd justa quase sem viés**. Medido contra a odd de-vigada real do mercado:

| Mercado | N | Viés (pp) | Precisão MAE (pp) | Break-even (mediana) | Gap melhor casa (mediana) |
|---|---|---|---|---|---|
| 1X2 (geral ligas-alvo) | 1448 | +1,45 | 5,94 | +4,10% | +2,80% |
| Over/Under 2,5 (geral) | 1102 | +0,52 | 5,60 | +5,43% | +3,03% |
| Handicap asiático .5 (geral) | 251 | +4,89 | 5,07 | +6,75% | +3,63% |

- **Viés ~0** no total (todas as saídas); o viés positivo aparece só no **lado recomendado** (o
  modelo é levemente superconfiante no lado que escolhe — efeito de seleção, não erro sistemático).
- **Reconciliação com a bateria W1-W4:** viés ~0 ⇒ a odd justa do modelo ≈ a do mercado ⇒ **não há
  edge batendo o mercado**. O ativo defensável é o **line-shopping**: a melhor casa já paga ~3%
  acima da média (mediana, lado recomendado), e o break-even exige ~4-5%. Ou seja, boa parte do
  valor está ao alcance de quem compara casas — e é isso que a plataforma aponta.
- **Calibração global** (walk-forward, 91.765 jogos, 52 competições): ECE 1,26%, log-loss 1,008,
  acurácia 1x2 49,9%, placar exato 13,0% (acima da literatura ~10-13%). Modelo vs mercado de
  fechamento: log-loss 1,0026 vs 0,9805 — coladinho no benchmark mais difícil.

## 3. Correção de viés na produção
`scripts/build_bias_correction.py` aprende, por mercado, Platt logit-linear
`p_corr = sigmoid(a·logit(p)+b)` contra a odd de-vigada real, com **guarda anti-degeneração**
(slope fora de [0.5,1.5] ou logit quase constante → identidade). Resultado:
- 1x2: a=0,998, b=−0,010 (near-identidade) · ou25: a=0,975 (near-identidade) · handicap: **identidade**
  (fit degenerado — probs de linha .5 se aglomeram em 0,5; o modelo já é calibrado).
- **Conclusão honesta: a correção é ~identidade** — o modelo já está calibrado, então os números
  quase não mudam. Aplicada mesmo assim (near-identity) pra padronizar o pipeline e a faixa ±5%.
- `app/services/odds.py::apply_bias` + `fair_band` aplicam a correção e a faixa 95/100/105% ao redor
  da odd justa; `predictor.py` carrega `bias_correction.joblib` via `os.path.exists` (ausência =
  identidade). Escopo: clube (odds de teste de clube); seleção usa identidade.

## 4. Mercados sem odds ainda (BTTS, escanteios, cartões)
- Odds existem na API-Football (`BET_MAP`: btts=8, escanteios=45/57/58, cartões=80/82/83) mas com
  **retenção de só 7 dias** → só coleta forward acumulando. Amostra atual: ~182 jogos de clube com
  btts/escanteios/cartões nos snapshots. Pequena; cresce com o job.
- Fontes externas (ver `data/reports/odds_sources.md`): Footiqo tem BTTS grátis; escanteios/cartões
  não têm fonte 100% grátis com histórico — The Odds API (~US$59) é o melhor custo-benefício pago.
- **Plano:** o job `collect_odds_backfill.py` acumula o dataset rotulado; quando cada mercado tiver
  amostra suficiente (>~300), rodar a skill `validar-mercado-com-odds` (1 por mercado) pra medir
  viés/precisão e gerar a correção. **Cronograma honesto:** infra pronta agora; a recalibração de
  escanteios/cartões fecha à medida que o dado da janela de 7 dias acumula (semanas). BTTS pode
  fechar antes (Footiqo + API-Football).

## 5. Pesquisa de escanteios 1T/2T (paralela) — REPROVADA
5 candidatos (StatsBomb como rótulo real, 1516 jogos limpos): nenhum bate o baseline. Divisão 1T/2T
é ~constante (0,53 no 2º tempo). Se lançar o mercado, split fixo 0,53. Detalhe em `PESQUISA_CLUBES.md §7`
e `data/reports/corners_halftime/RESUMO.md`.

## 6. Arquivos
- Produção: `app/services/odds.py`, `predictor.py`, `app/services/predictor_service.py`,
  `model_artifacts_clubes/bias_correction.joblib`, `app/services/performance_service.py`,
  `frontend/src/app/desempenho/page.tsx`.
- Scripts: `build_bias_correction.py`, `adhoc_metrics_{fair_odds,hitrates,model_vs_naive}.py`,
  `collect_odds_backfill.py` (agendado em `collect_odds_task.cmd`).
- Skill: `.claude/skills/validar-mercado-com-odds/SKILL.md`.
- Dados (gitignored, regeneráveis): `data/reports/performance/*.json`, `odds_history.sqlite`.

## 7. Guardrails (mantidos)
Sem promessa de lucro; jogo responsável em destaque; margem = de-vig real (não % fixo); gap por
mediana no lado recomendado; correção de viés não inventa edge (é ~identidade porque o modelo já é
calibrado). Nenhuma taxa metodologicamente enganosa (ex.: O/U 93-100% da linha=estimativa) é exibida.
