# HANDOFF — continuação em outra máquina

> **Escrito em**: 2026-07-28/29, ao fim de uma sessão que rodou numa máquina **sem** as
> credenciais de produção e **sem** a base completa de clubes.
> **Para**: o próximo agente/dev que continuar este trabalho em outra máquina.
> **Leia junto**: `DOCUMENTACAO_CENTRAL.md` §23 a §26 (nesta ordem) e `CLAUDE.md`.

---

## 0. TL;DR — o que aconteceu e o que falta

Uma bateria de hipóteses A/B/C (§23) tinha sido executada com **odds fabricadas** e um **modelo
de brinquedo**, produzindo números inflados que contradiziam a bateria séria já registrada (§20).
Isso foi **retirado** (§23 virou nota de retirada) e **refeito de forma honesta** (§24), com o
modelo de produção real e odds reais. O diagnóstico que explica os resultados está no §25. Uma
decisão de arquitetura de dados (WorkDrive como fonte da verdade) foi tomada e a camada foi
construída e testada (§26), mas **falta credencial para ativar**.

**Três bloqueios, todos por credencial/rede — nenhum por código:**

| # | Bloqueio | O que falta | Impacto |
|---|---|---|---|
| 1 | Mirror de competições | `DATABASE_URL` real do Neon | N do backtest preso em 722 |
| 2 | WorkDrive | 4 vars `ZOHO_*` | Dados ainda com cópia única local |
| 3 | Odds históricas | rede que alcance football-data.co.uk | N preso em 1 temporada |

---

## 1. Ative o WorkDrive primeiro (§26)

É o passo que impede a próxima máquina de repetir o problema desta.

```bash
# 1) credenciais em backend/.env (criar em https://api-console.zoho.com)
#    ZOHO_CLIENT_ID=...
#    ZOHO_CLIENT_SECRET=...
#    ZOHO_REFRESH_TOKEN=...
#    ZOHO_WORKDRIVE_FOLDER_ID=...
#    ATENÇÃO ao data center: conta UE/Índia/AU usa domínio diferente —
#    ZOHO_ACCOUNTS_BASE / ZOHO_WORKDRIVE_BASE (mesma pegadinha do ZeptoMail)

cd backend
DATA_STORE=workdrive python -m scripts.datastore_sync status   # o que existe local vs remoto
DATA_STORE=workdrive python -m scripts.datastore_sync push     # sobe tudo (952 MB na 1ª vez)
DATA_STORE=workdrive python -m scripts.datastore_sync verify   # exit 1 se algo só existir local
```

**A máquina que tem os dados bons deve dar `push` ANTES de qualquer máquina dar `pull`.**
Hoje (2026-07-28) o `verify` acusa **952 MB / 119 arquivos** com cópia única local.

**Regra de ouro**: nenhum dado pode ter cópia única em máquina local. Dado novo → registrar em
`data/MANIFEST.yaml` → acessar via `app/core/datastore.py::fetch()` → `push`.

⚠️ **Cuidado documentado**: o `WorkDriveStore` foi escrito contra a API REST do WorkDrive mas
**nunca foi executado contra a API real** (não havia credencial). O `LocalStore` foi testado
ponta a ponta. Espere ajustar detalhes de endpoint/paginação na primeira execução real —
especialmente `_resolve()` (WorkDrive endereça por **id**, não por caminho) e o formato de
resposta de `/files/{id}/files`. Valide com `--dry-run` e um dataset pequeno (`--id reports`)
antes de subir os 583 MB do `club_raw_cache`.

---

## 2. Destrave a base de clubes (§24.1, §24.5)

Esta máquina só tinha **4 competições** (21.130 jogos: Brasileirão A/B, Premier League,
Champions League). A produção usa **83 competições / 272.918 jogos / 72 torneios** — coletadas
em outra máquina e **inacessíveis daqui**. É exatamente o problema que o WorkDrive resolve.

```bash
cd backend
# precisa de DATABASE_URL real do Neon (aqui só havia sqlite:///./dev_verify.db)
# e de APIFOOTBALL_KEY (checar cota antes: GET /status -> subscription.end)
python scripts/mirror_club_cache.py            # backfill do bruto via API, zero egress do Neon
python scripts/build_clubs_dataset.py --stage all
# validar: df['tournament'].nunique() ~= 72 e len(df) ~= 272918 (bate com
# model_artifacts_clubes/meta.json). Se der 4 torneios/21k, a base ainda está incompleta.
```

---

## 3. Refaça o backtest com a base completa (§24.5)

Cadeia exata, nesta ordem (todos os scripts já existem e funcionam):

```bash
cd backend
python scripts/backtest_train_frozen_model.py --cutoff 2025-07-01   # NUNCA sobrescreve produção
python scripts/backtest_odds_ingest.py --year 2025
python scripts/backtest_match_games.py
python scripts/backtest_generate_predictions.py
python scripts/adhoc_diagnostico_modelo_vs_mercado.py    # RODE ESTE PRIMEIRO (dá o benchmark)
python scripts/adhoc_hipotese_a_alfa_cotacao.py
python scripts/adhoc_hipotese_b_perfis_apostador.py
python scripts/adhoc_hipotese_c_desagregacao.py
```

Depois **atualize os números do §24 e do `docs/RELATORIO_HIPOTESES_A_B_C_v2.md`** — os valores
lá são de N=722 (2 ligas, 1 temporada) e devem ser substituídos, não somados.

---

## 4. Regras que NÃO podem ser quebradas (aprendidas na marra)

1. **Nunca fabricar odds a partir da probabilidade do próprio modelo.** É circular por
   construção — o "alfa" aparece garantido mesmo sem edge nenhum. Foi o erro que invalidou o
   §23 inteiro. Use odds de mercado independentes (`data-test/`, coleta forward).
2. **Nunca use `model_artifacts{,_clubes}/` (produção) para medir desempenho histórico.** Eles
   foram ajustados na base inteira, sem holdout (`meta.json["n_train"]` = 100% dos dados) —
   é vazamento garantido. Use um artefato **congelado** (`backtest_train_frozen_model.py`).
3. **Nunca use `Predictor.predict()` para backtest.** Ele usa o snapshot de **agora**. Use
   `predict_from_row(row)`, que consome features point-in-time da linha histórica.
4. **Nunca compare ROI contra zero.** O benchmark é o ROI-sem-edge dado o vig (§25.1). Com vig
   de 6.05%, o benchmark é **−5.71%**, não 0. Comparar contra zero fez um modelo são parecer
   quebrado.
5. **Sempre reporte N e IC95% (bootstrap).** Nenhum número pontual sem intervalo. E cheque o
   poder: detectar edge de 2% exige ~20.100 apostas (§25.3).
6. **Piso de amostra em tabelas por liga/ano** (usamos N≥100). Nunca uma linha "1 jogo, 100% de
   acerto" ao lado da Premier League — foi outro vício do §23.
7. **Antes de propor hipótese de odds/valor/EV:** ler §19, §20, §24, §25. Muita coisa já foi
   reprovada com amostra grande; não repita.

---

## 5. Onde o projeto está, cientificamente (§25)

Não há nada quebrado no modelo. Os números:

- **Vig 6.05%** → benchmark sem edge = −5.71%. ROI observado agregado = −5.85% (**−0.04σ**).
- **log-loss**: modelo 1.0219 vs mercado de-vigado 0.9975 → capturamos **~76%** da informação
  do mercado. **ECE 0.0199 = bem calibrado.**
- **Poder**: 722 apostas contra ~20.100 necessárias. Nada em §24 era conclusivo, em nenhuma
  direção.
- **Hipótese aberta e mais promissora**: eficiência de mercado difere por liga — capturamos 85%
  no Brasileirão (onde até ganhamos em acurácia: 52.0% vs 51.8%) e 65% na Premier League. Se há
  edge, é em mercados menos eficientes, não nas big five.
- **Métrica que deveria virar primária: CLV** (closing line value) — converge com N muito menor
  que ROI. Hoje **impossível de medir** porque o histórico de odds não é persistido (só o
  snapshot mais recente vai pro Neon; os `.jsonl` do Render são efêmeros). **Corrigir isso é o
  item de maior retorno depois do WorkDrive.**

**Conclusão estratégica**: três baterias independentes (§19, §20, §25) convergem — bater o
mercado provavelmente não é o negócio. O que é defensável e já está no ar: *o usuário perde
menos, decide melhor e paga menos vig* (`/desempenho` + alfa de cotação do §24.2).

---

## 6. Pendências abertas (com dono e critério de pronto)

| Item | Bloqueado por | Pronto quando |
|---|---|---|
| Ativar WorkDrive | 4 vars `ZOHO_*` | `datastore_sync verify` sai com exit 0 |
| Mirror de clubes | `DATABASE_URL` do Neon | dataset com ~72 torneios/273k jogos |
| Odds históricas | rede (ver abaixo) | `data-test/historical/` populado |
| Persistir histórico de odds | decisão de schema | CLV mensurável (§25.5) |
| Migrar blobs do Neon | WorkDrive ativo | `match_detail_cache` fora do Neon |
| Rever §24 com base completa | itens 1-3 acima | números de N>10k no §24 e no v2 |
| **Expansão de mercados** | ver `docs/PLANO_EXPANSAO_MERCADOS.md` | gate §6-C definido + candidatos julgados |

**Expansão de mercados (plano aprovado 2026-07-29, nada executado)**: há ~15 mercados novos
abertos com o dado que **já está no cache**, sem gastar cota de API — 7 estatísticas da API que
nunca viraram coluna, mais tudo que `events` (99,9% de cobertura, minuto exato) permite derivar.
O plano completo, com catálogo, armadilhas de dado e critérios, está em
**`docs/PLANO_EXPANSAO_MERCADOS.md`**. Achado central: **os mercados de contagem em produção
nunca passaram por gate nenhum** — a Fase 0 é definir o gate §6-C, a Fase 1 é aplicá-lo
retroativamente aos 7 mercados já no ar. As Fases 2 e 4 (clube) dependem do mirror completo.

**Odds históricas**: `backend/scripts/fetch_historical_odds.py` está pronto (352 arquivos: 22
ligas × 16 temporadas, `--list` mostra o plano). Em 2026-07-28 o domínio
`football-data.co.uk` estava **inacessível desta máquina**: DNS resolvia (217.160.0.246) mas o
TCP era descartado em http **e** https, enquanto google/pypi/api-sports respondiam normalmente
— bloqueio específico do domínio nessa rede. **Tente de outra rede antes de assumir que o
script está errado** (ele nunca rodou contra a fonte real). Alternativa: baixar pelo navegador
para `data-test/historical/<temporada>/<div>.csv`.

---

## 7. Detalhes de ambiente que custaram tempo

- **`openpyxl`** foi instalado no venv nesta sessão (necessário para ler
  `data-test/new_leagues_data.xlsx`, onde está o Brasileirão). Não estava no `requirements`.
  Se `backtest_odds_ingest.py` falhar com `ImportError: openpyxl`, é isso.
- **`pyyaml`** é necessário para `datastore_sync.py` (lê o MANIFEST).
- **`APIFOOTBALL_KEY`** existia no `.env` da **raiz** mas não em `backend/.env` (que é o único
  que `fixture_fetch.py::_key()` lê). Foi copiada nesta sessão. Ambos os `.env` são gitignored.
- **Cota da API-Football** em 2026-07-28: 67.530/75.000 restantes, assinatura válida até
  **2026-08-19**. Cheque `GET /status` antes de planejar coleta de vários dias.
- **Bug de dados real**: no `new_leagues_data.xlsx` (Brasileirão) as odds só existem na coluna
  de **fechamento**. Filtrar apenas abertura zera o Brasileirão inteiro — os 3 scripts de
  hipótese usam fechamento com fallback para abertura por causa disso.

---

## 8. Estado do repositório

Commitado na `main` ao fim desta sessão: documentação (§23-§26), camada de dados
(`datastore.py`, `MANIFEST.yaml`, `datastore_sync.py`), scripts de hipótese e diagnóstico,
`fetch_historical_odds.py`, relatório v2, e o v1 marcado como descartado.

**Não commitado (mudanças de outra sessão, intocadas):** alterações em
`backend/app/domains/admin/*`, `frontend/src/**`, `AGENTS.md`, `docs/AUDIT_REPORT.md`,
`graphify-out/`. Se você não as reconhece, confirme com o dono antes de mexer.

### ⚠️ Armadilha real, custou meia sessão — não repita

`backend/model_artifacts_clubes_2025frozen/` **já estava commitado, treinado na base completa
(250.682 jogos / 5.365 times)**. Rodar `backtest_train_frozen_model.py --cutoff 2025-07-01`
nesta máquina o **sobrescreveu silenciosamente** por uma versão de apenas 19.574 jogos / 396
times — porque o script lê o `club_features_enriched.parquet` **local**, que aqui só tinha 4
ligas. Todo o backtest rodou com um modelo aleijado antes de o erro ser detectado; foi revertido
(`git checkout`) e tudo foi regerado com o artefato bom.

**Antes e depois de rodar qualquer `*_train_*`:**
```bash
python -c "import json,io; m=json.load(io.open('backend/model_artifacts_clubes_2025frozen/meta.json',encoding='utf-8',errors='replace')); print(m['n_train']['goals'], len(m['snapshot']))"
# esperado: 250682 5365  (ou mais, se a base tiver crescido). Se cair para ~19k/396, PARE.
```
Só retreine o congelado depois de confirmar que a base local está completa (~273k jogos/72
torneios). Um artefato congelado bom vale mais que um retreino ruim.
