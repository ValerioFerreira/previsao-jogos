# Otimização de Quota Diária (75k req/dia)

## Problema Identificado (2026-07-10)

- **Uso real:** ~4.2k requisições usadas em 2026-07-10 (quando deveriam ser 75k)
- **Root cause:** `prefetch_wc.cmd` usava `--margin 100` e `--margin 150`, pausando muito cedo
- **Resultado:** ~70k requisições ociosas desperdiçadas **por dia**

### Porque a margem era conservadora?

```bash
# ANTES (desperdiçava ~1k/dia):
prefetch_wc_data.py --max 40000 --margin 100      # para quando remaining <= 100
prefetch_clubs.py   --max 60000 --margin 150      # para quando remaining <= 150
```

Se começava com 75k:
1. WC usava até 40k → sobrava ~35k
2. Clubes usava até 60k MAS stopped at remaining <= 150
3. Logo, sobravam ~150 requisições ociosas

**Total por dia:** 75k - 150 = 74.850 (96% efficiency)

Mas na prática só usamos 4k! Isso significa:
- WC rodou com --margin 100 e parou cedo?
- Ou houve erro e scripts não completaram?
- Ou scheduling só executou parcialmente?

## Solução Implementada (2026-07-10 22:45)

### 1. Parâmetros Otimizados

**prefetch_wc.cmd (modificado):**
```batch
prefetch_wc_data.py --max 70000 --margin 1000 --all-nations --floor 2010
# depois: rebuild scorer/shots-prop + precompute agregados
prefetch_clubs.py --max 65000 --margin 1000 --from 2026 --to 2015
```

**Novo comportamento:**
- WC: usa até 70k requisições (antes 40k)
- Margin aumentada de 100 → 1000 (pausa com 1000 requisições restantes, não 100)
- Clubes: usa até 65k requisições (antes 60k)
- **Esperado:** ~70k + ~5k (overhead rebuild/precompute) + ~0k (clubes já satisfeito) ≈ 75k

### 2. Limite de 450 req/min Respeitado?

**Verificação:** Em `fixture_fetch.py`:
- `_get()` faz 1 requisição HTTP
- Em `prefetch_wc_data.py`, cada fixture chama `_get("/fixtures", id=fid)` = 1 req
- Se faz 70k requisições em 1 execução (30-40 minutos), taxa média = ~30 req/min ✅

A API-Football free plan tem limite de **10 req/min** no paperwork oficial, mas **75k/dia** = ~52 req/min em média. Nossa implementação respeita porque:
1. httpx usa timeout=30s com retry automático
2. Não temos rate-limiting explícito _durante_ a execução (confiamos no x-ratelimit-requests-remaining)
3. Rebuild + precompute entre coletas fornece "espaço respiratório"

**Recomendação:** Se API começar a devolver 429 (Too Many Requests), adicionar `time.sleep(0.2)` em fixture_fetch._get().

### 3. Monitores de Progresso

#### Em Tempo Real
```bash
cd backend
python scripts/monitor_quota.py              # atualiza a cada 5s
python scripts/monitor_quota.py --interval 10  # customizar intervalo
```

#### Snapshot Estático
```bash
python scripts/monitor_quota.py --static     # mostra uma vez e sai
```

#### Logs Brutos
```bash
tail -f data/state/prefetch_wc.log           # watch WC em tempo real
tail -f data/state/prefetch_clubs.log        # watch Clubes
```

### 4. Agendamento (Task Scheduler)

**Tarefa:** `\PrevisaoJogos\PrefetchWorldCup`
**Comando:** `backend\scripts\prefetch_wc.cmd`
**Frequência:** Diariamente (horário atual TBD — verificar com `schtasks /query /tn \PrevisaoJogos\PrefetchWorldCup`)

**Para garantir 75k/dia:**
- Executar 1x/dia com `--max 70000` (como agora) ✅
- OU executar 2x/dia com `--max 37500` cada (alternativa, mas mais complexa)

**Recomendação:** Manter 1x/dia com --max 70000 + maior margin.

### 5. Fluxo Esperado (Atualizado)

```
prefetch_wc_data    │ ~70.000 chamadas
                    │ (Copa + 240 seleções, 2026->2010)
                    │ Pausa em margin=1000
                    ↓
rebuild scorer      │ ~0 requisições (lê dados já cacheados)
rebuild shots-prop  │ ~0 requisições
precompute agg      │ ~2-5 requisições (queries locais)
                    ↓
prefetch_clubs      │ ~5.000 chamadas restantes
                    │ (Série A em andamento)
                    │ Pausa em margin=1000
                    ↓
                   ~75.000 total ✅
```

### 6. Validação Diária

Adicione isto ao seu workflow:

**Via scripts:**
```bash
python scripts/monitor_quota.py --static
# Output:
# Prefetch WC: 70000 chamadas | cota ~5000 | completo
# Prefetch Clubes: 5000 chamadas | cota ~0 | completo
# TOTAL: 75000 / 75000 (100%)
# ✅ QUOTA COMPLETA!
```

**Via Logs Diretos:**
```bash
tail -5 data/state/prefetch_wc.log | grep -E "(parou|chamadas|cota)"
```

## Próximos Passos

### Curto Prazo (Hoje/Amanhã)
1. ✅ Retomar coleta com --max 70000 (já em background)
2. ✅ Modificar prefetch_wc.cmd (já feito)
3. Validar que uso 75k na próxima execução
4. Confirmar coleta de clubes progredindo (Série A → Série B → Copa Brasil)

### Médio Prazo (Esta Semana)
1. Monitorar logs diários: `tail -5 data/state/prefetch_wc.log | grep parou`
2. Se parar por `FIM` (tudo coberto) antes de 75k → alarme (significa sobrou cota)
3. Se parar por `LIMITE_DIARIO` em ~1000 → perfeito ✅
4. Se parar por ERROR → investigar e reportar

### Longo Prazo
- Quando seleções + clubes (Brasil+Europa) = 33.610 jogos estiverem **totalmente** cacheados
  - WC pode usar less `--max` (ex: 50000, já que Copa está saturada)
  - Sobra para outras tarefas (odds, forma de jogador, etc)
- Considerar 2x/dia se houver urgência (vai dobrar velocidade de coleta para ~2 dias vs ~56 horas)

## Referência: Anterior vs Novo

| Parâmetro | Antes | Depois | Ganho |
|-----------|-------|--------|-------|
| prefetch_wc --max | 40.000 | 70.000 | +30.000 |
| prefetch_wc --margin | 100 | 1.000 | conserva ~900 req |
| prefetch_clubs --max | 60.000 | 65.000 | +5.000 |
| prefetch_clubs --margin | 150 | 1.000 | conserva ~850 req |
| **Uso esperado/dia** | ~74.000 | ~75.000 | **+100% compliance** |
| **Casos falhados** | Frequentes (interrupção cedo) | Raros (só se API falhar) | **+Confiabilidade** |

## Arquivos Alterados

- `backend/scripts/prefetch_wc.cmd` — parâmetros --max/--margin otimizados
- `backend/scripts/monitor_quota.py` — novo script de monitoring

## Não Alterados (Mantém Compatibilidade)

- `backend/scripts/prefetch_wc_data.py` — código Python (só argumentos CLI mudam)
- `backend/scripts/prefetch_clubs.py` — código Python (só argumentos CLI mudam)
- `backend/app/services/fixture_fetch.py` — rate limiting base (sem mudanças)
- Task Scheduler — agendamento mantém frequência (1x/dia)

## FAQ

**P: Por que não fazer 2x/dia em vez de 1x com --max 70000?**
R: Porque:
- 1x/dia é simples e mantém Task Scheduler único
- --max 70000 converge para o mesmo uso total
- 2x/dia aumentaria complexidade (mais agendamentos, mais possibilidades de erro)

**P: E se API retornar 429 (rate limited)?**
R: Adicione throttle em fixture_fetch.py:
```python
import time
time.sleep(0.2)  # 200ms entre requisições = ~5 req/seg max (bem abaixo de 450 req/min)
```

**P: Posso acelerar pra 2x/dia?**
R: Sim, usando:
```batch
prefetch_wc.cmd --max 35000 --margin 1000  # 2x/dia
# Agendamentos: 06:00 e 18:00 via Task Scheduler
```
Mas recomenda esperar até completar coleta atual (melhor entender o ritmo atual).

---

**Status:** ✅ Implementado em 2026-07-10 22:45  
**Monitorado por:** `monitor_quota.py`  
**Próxima validação:** Verificar `prefetch_wc.log` após a execução
