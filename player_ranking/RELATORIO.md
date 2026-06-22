# Relatório — Player-Level Power Ranking (pilôto executado)

> Sessão autônoma de 2026-06-21. Pipeline paralelo construído, base coletada e o
> **gate executado**. Resultado honesto: **o player-ranking (na versão agregado-de-
> temporada) NÃO melhora a previsão de resultado sobre o Elo.** Detalhes abaixo.
> Produção intacta; tudo isolado em `player_ranking/` (dados gitignored).

## 1. Objetivo e hipótese
Testar se substituir/complementar o Elo de seleção por um **ranking de força baseado
na forma de clube dos jogadores** melhora a previsão de resultado (H/D/A). Premissa:
para seleções o Elo é defasado; a força viria da qualidade/ritmo atual dos atletas.

## 2. Arquitetura construída (isolada, não-produção)
`player_ranking/src/`: `apiclient` (cache/rate-limit/retomada) · `build_raw_index`
(elenco-base local dos fixtures crus) · `build_base_squads` (regulares dos 5 jogos
anteriores — leakage-safe) · `collect_players(_fast)` (forma de clube via `/players`,
concorrente, 8 workers ≤400/min) · `build_features` (agregados de seleção + cobertura)
· `experiment` (o gate). Decisão de design **leakage-safe**: janelas pós-temporada
(jun-jul) usando o agregado da **temporada de clube recém-encerrada** → inteiramente
no passado do jogo, sem leakage e a ~1 request/jogador (em vez de ~30k chamadas por
jogo de clube).

## 3. Execuções e custo
| Etapa | Resultado | Requests |
|---|---|---|
| Passo 0 — sonda de cobertura | viável no espectro (2 rodadas; bug de adversário pego) | 259 |
| Índice de fixtures crus | 9.511 indexados, 8.325 com escalação | 0 (local) |
| Jogos-alvo + elenco-base | **414 jogos** (jun-jul 2024/25 + jun 2026), elenco ~29/lado | 0 (local) |
| Coleta de forma de clube | 13.217 pares; **10.440 jogadores com forma**, rating em 7.558 | ~13,5k |
| **Total** | cota restante ~61,4k de 75k | **~13,8k** |

## 4. Achados de DADOS (importantes por si só)
- **Cobertura BIMODAL.** Forte para Euro/Copa América/Copa 2026 e seleções com diáspora
  europeia; **fraca na cauda minnow×minnow** (F0: Maldivas×Afeganistão = 7/54 jogadores
  com forma de clube; jogadores em ligas amadoras/fora do eixo europeu sem `/players`).
  Cobertura média por jogo 0,70; **255/414 jogos com cobertura ≥0,7**.
- **Implicação:** a feature só existe de fato para jogos entre times razoavelmente fortes
  — exatamente onde o Elo já é bom. Não cobre os casos onde o modelo atual é mais fraco.
- **Disciplina pegou 2 bugs "bons demais":** contaminação do elenco-base pelo adversário
  (`/fixtures/players` traz os 2 times) e processos de coleta duplicados.

## 5. Metodologia do gate
4 conjuntos de features × subconjuntos de cobertura × 2 modelos × validação dupla:
- **Features:** ELO (`elo_diff`) | CURRENT (Elo+forma+h2h+contexto) | PLAYER (9 diffs de
  player-ranking: rating, rating ajustado por liga, minutos, share de liga top, peso de
  liga, profundidade, gols/chutes/passes-chave por 90) | CURRENT+PLAYER.
- **Subconjuntos:** completo (414) · ≥0,5 (303) · ≥0,7 (255) · equilibrados |elo_diff|≤100 (82).
- **Modelos:** HistGradientBoosting (lida c/ NaN) e Regressão Logística.
- **Validação:** 5-fold estratificado repetido 3× (robusto) + split temporal 80/20.
- **Métricas:** log-loss (proper score), ECE multiclasse, acurácia.

## 6. Resultados do gate — CV log-loss (Regressão Logística, métrica robusta)
| Subconjunto | ELO | CURRENT | PLAYER | ELO+PLAYER |
|---|---|---|---|---|
| Completo (414) | **0.875** | 0.882 | 0.929 | 0.898 |
| Cobertura ≥0,5 (303) | **0.913** | 0.923 | 0.917 | 0.918 |
| Alta cobertura ≥0,7 (255) | **0.916** | 0.927 | 0.930 | 0.932 |
| Equilibrados (82) | **1.105** | 1.209 | 1.262 | 1.380 |

**Em todos os subconjuntos o Elo sozinho é igual ou melhor; player-ranking não melhora**
(e piora os equilibrados). HGB conta a mesma história (sempre pior que LogReg aqui, por
overfit no N pequeno). O split temporal mostra "vitórias" do PLAYER (ex.: ≥0,7 TEMP
log-loss 0.80 vs Elo 0.95), **mas** é um holdout pequeno (~51 jogos) e time-confundido
(a cauda = Copa 2026); o **CV de 15 folds contradiz** → tratado como artefato, não promovido.

## 7. Por que não funciona — redundância com o Elo
Correlação de Pearson das features de player com `elo_diff` (alta cobertura):
rating_adj **+0,72**, key_passes90 +0,69, peso_liga +0,64, shots90 +0,64, minutos +0,63,
rating +0,63, topleague_share +0,61, profundidade +0,55, goals90 +0,38.
→ As features **re-medem a força do time** que o Elo já captura (times fortes têm
jogadores em ligas top com rating alto = Elo alto), só que mais ruidosas e com buracos de
cobertura. Adicionam sinal **redundante**, não novo.

A importância por permutação (HGB) chega a pôr `key_passes90`/`depth` acima de `elo_diff`,
mas como o HGB generaliza pior que o Elo-só, isso é overfit (alta importância, pior CV).

## 8. Conclusão honesta
**O gate FALHA: na versão agregado-de-temporada, o player-ranking é redundante com o Elo
e não melhora a previsão de resultado.** Consistente com a meta-conclusão da sessão (Elo
domina; os modelos estão no teto; sinal que é redundante com o Elo não ajuda).

**O que isto NÃO prova (em aberto, honestamente):** usei o agregado de TEMPORADA (proxy de
*qualidade*, que por natureza correlaciona com Elo). A parte potencialmente ortogonal —
**forma recente / fadiga / lesão / minutos das últimas semanas** — exige dados POR JOGO
(o caminho caro, ~30k+ requests com leakage a tratar) e **não foi testada**. A versão
barata não tem sinal; a versão recência fica como hipótese não-respondida.

## 9. Recomendação
- **Não promover** player-ranking-de-temporada. Não é alavanca.
- Se quiser perseguir a hipótese de verdade, o único caminho com chance é a **forma
  recente por jogo** (ortogonal ao Elo), aceitando o custo de coleta e o trabalho de
  point-in-time por jogo — e com um gate igualmente duro. Recomendo só fazer isso se o
  **backtest de odds ao vivo** (já rodando) indicar que vale o investimento.
- Box-score de seleção e calibração já foram esgotados; o ganho real, se houver, segue
  sendo medido pelo backtest ao vivo.

## 10. Reprodução / estado
```
python player_ranking/src/build_features.py   # 414 jogos, cobertura
python player_ranking/src/experiment.py        # o gate (este relatório)
```
Dados em `player_ranking/data/` (gitignored): cache de 13.217 perfis, parquets de forma,
features e dataset. Cota restante ~61,4k. Ver `MIGRACAO.md` para levar tudo p/ outra máquina.
