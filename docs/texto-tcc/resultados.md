# Resultados

Estrutura do capítulo de resultados do TCC. Só estão preenchidos os números já congelados e documentados: os do banco `pm25-congelado-2026-10-09_2026-11-08.db` (SHA-256 `2d6dfd45891e8d91f6eb34afda3748a39c38a84b4c04af94dbf206c93f293e87`, 51.820 leituras, extraído em 09/11/2026 às 04:51 UTC), que cobre de 09/10 a 08/11/2026 (31 dias, horário de Brasília). Cada tabela indica o arquivo de `resultados/` de onde saiu. O que depende do banco de 35 dias, da rodada final do protocolo ou do período de sobreposição dos nós está marcado com [PENDENTE] e não deve ser preenchido antes de o resultado existir. O passo a passo da rodada final está em [`docs/rodada-final.md`](../rodada-final.md), e as ressalvas de cada resultado, em [`limitacoes.md`](limitacoes.md).

Os resultados de previsão desta versão são os da **avaliação preliminar** de 09/11/2026 (31 dias, uma dobra de validação, hiperparâmetros fixos). O protocolo de avaliação (`docs/protocolo-de-avaliacao.md`) define que a rodada final usa um banco de pelo menos 35 dias; quando ela existir, as tabelas da seção 3 passam a trazer os números dela, e os preliminares ficam como registro do que já tinha sido visto.

## 1. Coleta e qualidade dos dados

### 1.1 Período e conjunto de dados

| Item | Valor | Fonte |
|---|---|---|
| Período analisado | 09/10 a 08/11/2026 (31 dias, horário de Brasília) | `periodo.json` |
| Banco congelado | `pm25-congelado-2026-10-09_2026-11-08.db` | `periodo.json` |
| SHA-256 | `2d6dfd45891e8d91f6eb34afda3748a39c38a84b4c04af94dbf206c93f293e87` | `periodo.json` |
| Leituras no banco | 51.820 | `periodo.json` |
| Nó da análise principal | `no-01` (Osasco, bairro Veloso) | `docs/limitacoes-do-tcc.md` |

Banco de 35 dias da rodada final: [PENDENTE: período, nome do arquivo, SHA-256 e número de leituras do banco congelado de pelo menos 35 dias].

### 1.2 Saúde da coleta

Tabela 21 do TCC. `no-01`, 09/10 a 08/11/2026 (`resultados/periodo.json`, bloco `operacional`).

| Indicador | `no-01` |
|---|---|
| Minutos esperados | 44.640 |
| Minutos com leitura | 43.390 |
| Completude | 97,2% |
| Maior lacuna | 542 min |
| Mensagens perdidas | 0 |
| Reinícios | 32 |
| Duplicatas descartadas | 67 |
| RSSI médio | −44,2 dBm |
| Minutos sem leitura, por origem | reinício 999; bordas 251; comunicação 0; aquisição 0; total 1.250 |

O `no-02`, na mesma janela, teve completude de 18,6%, 37 reinícios, 76 horas válidas e 59 horas suspeitas (`docs/limitacoes-do-tcc.md`, item 1); ele entrou em 21/10/2026 e media em outro local, por isso fica fora da análise principal.

Gráfico 1 (completude diária): `resultados/figuras/completude_diaria.png`, gerado pelo `result_figures` a partir de `resultados/completude_diaria.csv`.

Mesmos indicadores no banco de 35 dias: [PENDENTE: tabela refeita com o `period_metrics` sobre o banco da rodada final].

### 1.3 Horas válidas, suspeitas e sem média

`no-01` (`resultados/periodo.json`, bloco `pm25`, e `docs/limitacoes-do-tcc.md`, item 2).

| Horas | Quantidade |
|---|---|
| Esperadas | 744 |
| Válidas | 651 |
| Suspeitas | 70 (9,4%) |
| Sem média por falta ou escassez de leituras | 23 |
| Dias com média de 24 h válida | 26 |

As 70 horas suspeitas formam 17 episódios, os maiores de 14, 13 e 9 horas (`docs/limitacoes-do-tcc.md`, item 2).

### 1.4 Estatísticas de PM2,5

Tabela 22 do TCC. Médias horárias válidas do `no-01`, sem as horas suspeitas (`resultados/periodo.json`, bloco `pm25`), em µg/m³.

| Estatística | Valor |
|---|---|
| Horas válidas | 651 |
| Média | 21,5 |
| Mediana | 19,7 |
| Desvio-padrão (amostral) | 15,2 |
| Percentil 5 | 3,3 |
| Percentil 95 | 44,9 |
| Máximo horário | 116,1 |

Médias de 24 h acima de cada referência, nos 26 dias válidos (`resultados/periodo.json`, bloco `referencias`). Nem a OMS nem o CONAMA definem limite horário de PM2,5; a contagem de horas é só uma referência.

| Referência (média de 24 h, µg/m³) | Dias acima (de 26) | Horas acima (de 651) |
|---|---|---|
| OMS 2021 nível-guia e CONAMA 506/2024 PF (15) | 20 | 373 |
| OMS 2021 meta intermediária 4 e CONAMA PI-4 (25) | 10 | 262 |
| CONAMA 506/2024 PI-3 (37) | 1 | 105 |
| OMS 2021 meta intermediária 3 (37,5) | 1 | 96 |
| OMS 2021 meta intermediária 2 e CONAMA PI-2, em vigor (50) | 0 | 17 |
| CONAMA 506/2024 PI-1 (60) | 0 | 5 |
| OMS 2021 meta intermediária 1 (75) | 0 | 4 |

Gráfico 2 (perfil por hora do dia e por dia da semana): `resultados/figuras/perfil_pm25.png`, gerado pelo `result_figures` a partir de `resultados/perfil_hora.csv` e `resultados/perfil_dia_semana.csv`.

### 1.5 Estatísticas de PM2,5 com as horas suspeitas incluídas (sensibilidade)

`period_metrics --include-suspect` sobre o mesmo banco congelado, rodado em 13/11/2026 (`resultados/com_horas_suspeitas/periodo.json`). As 70 horas suspeitas entram com a média que tiveram; a saúde da coleta não muda. Valores em µg/m³.

| Estatística | Sem as horas suspeitas | Com as horas suspeitas |
|---|---|---|
| Horas com média | 651 | 721 |
| Média | 21,5 | 19,4 |
| Mediana | 19,7 | 16,5 |
| Desvio-padrão (amostral) | 15,2 | 15,7 |
| Percentil 5 | 3,3 | 0,3 |
| Percentil 95 | 44,9 | 44,4 |
| Máximo horário | 116,1 | 116,1 |
| Dias com média de 24 h válida | 26 | 30 |

Com as horas suspeitas, os dias com média de 24 h acima de cada referência não mudam (20, 10, 1, 1, 0, 0 e 0, na ordem da tabela da seção 1.4), agora sobre 30 dias válidos; as horas acima de cada valor também são as mesmas, sobre 721.

## 2. Comparação com a CETESB

Estação Osasco da CETESB (código 120), médias horárias de MP2,5 do QUALAR, 744 horas no arquivo, 10 vazias; rótulo de hora tratado como o fim da hora. Viés é a média de nó menos CETESB, e a reta é a do nó em função da CETESB. Valores em µg/m³.

### 2.1 Sem as horas suspeitas (análise principal)

`resultados/comparacao_cetesb.json`, nó `no-01`.

| Grupo | Horas pareadas | Média do nó | Média da CETESB | Viés | MAE | RMSE | r | R² | Inclinação | Intercepto |
|---|---|---|---|---|---|---|---|---|---|---|
| Total | 641 | 21,2 | 12,9 | +8,3 | 12,0 | 16,0 | 0,43 | 0,18 | 0,82 | 10,6 |
| Umidade até 75% | 625 | 20,8 | 12,8 | +8,0 | 11,7 | 15,3 | 0,44 | 0,19 | 0,81 | 10,5 |
| Umidade acima de 75% | 16 | 37,7 | 16,3 | +21,4 | 26,2 | 34,3 | n/c | n/c | n/c | n/c |

n/c: não calculado, por haver menos de 24 horas pareadas no grupo.

### 2.2 Com as horas suspeitas (sensibilidade)

`resultados/com_horas_suspeitas/comparacao_cetesb.json`, nó `no-01`.

| Grupo | Horas pareadas | Média do nó | Média da CETESB | Viés | MAE | RMSE | r | R² | Inclinação | Intercepto |
|---|---|---|---|---|---|---|---|---|---|---|
| Total | 711 | 19,2 | 12,4 | +6,8 | 11,6 | 15,5 | 0,45 | 0,20 | 0,90 | 8,1 |
| Umidade até 75% | 694 | 18,8 | 12,3 | +6,5 | 11,2 | 14,8 | 0,46 | 0,21 | 0,88 | 8,0 |
| Umidade acima de 75% | 17 | 35,6 | 15,7 | +19,9 | 24,9 | 33,3 | n/c | n/c | n/c | n/c |
| Só as horas suspeitas | 70 | 0,69 | 7,7 | −7,0 | 7,2 | 9,3 | 0,27 | 0,07 | 0,06 | 0,3 |
| Demais horas | 641 | 21,2 | 12,9 | +8,3 | 12,0 | 16,0 | 0,43 | 0,18 | 0,82 | 10,6 |

Nas horas suspeitas, a mediana da estação foi de 7,0 µg/m³, contra 12,0 nas horas válidas; em 33% delas a estação marcou 10 µg/m³ ou mais, com máximos de até 27 (`docs/limitacoes-do-tcc.md`, item 2).

### 2.3 Sensibilidade à convenção de hora do QUALAR

Com o rótulo de hora tratado como início da hora (`--hour-label start`), o r cai de 0,43 para 0,39 e o RMSE sobe de 16,0 para 16,4 (`docs/limitacoes-do-tcc.md`, item 8).

Gráfico de dispersão nó × CETESB: `resultados/figuras/dispersao_cetesb.png`, gerado pelo `result_figures` a partir de `resultados/comparacao_cetesb_pares.csv` (análise principal, sem as horas suspeitas).

Pendências desta seção:

- [PENDENTE: as duas tabelas refeitas sobre o banco de 35 dias, com o CSV do QUALAR do mesmo período.]
- [PENDENTE: coordenadas oficiais da estação Osasco e a distância até o `no-01`, hoje estimada em cerca de 4,4 km.]
- [PENDENTE: confirmação pela CETESB da convenção de hora do QUALAR.]

## 3. Previsão

Previsão da média horária de PM2,5 da hora seguinte, comparada com a persistência. O skill score é um menos a razão entre o RMSE do previsor e o da persistência, nas mesmas horas. O protocolo não elege um modelo: todos os previsores são relatados nas duas trilhas.

### 3.1 Trilha fixa

#### Avaliação preliminar (31 dias, uma dobra)

Só o `no-01`: 494 horas completas, 1 dobra de validação com 91 horas e teste final com 149 horas, de 31/10 a 07/11/2026; hiperparâmetros de `forecasting.DEFAULTS`; MLP com 5 sementes (42 a 46). Fonte: `resultados/no-01/previsao.json` (Python 3.10.11, numpy 2.2.6, pandas 2.3.3, scikit-learn 1.7.2). RMSE e MAE em µg/m³; a MLP aparece pela média ± desvio-padrão das sementes, e o MAE dela é o da semente de referência (42).

| Previsor | RMSE validação | Skill validação | MAE teste | RMSE teste | Skill teste |
|---|---|---|---|---|---|
| Persistência | 10,47 | 0 | 5,06 | 7,08 | 0 |
| Ridge | 10,08 | +0,037 | 4,84 | 6,50 | +0,082 |
| MLP (5 sementes) | 10,09 ± 0,15 | +0,036 ± 0,015 | 4,99 | 6,90 ± 0,15 | +0,025 ± 0,021 |
| Gradient boosting | 10,92 | −0,043 | 5,87 | 7,47 | −0,055 |

Sensibilidade com os dois nós juntos: 521 horas completas, validação com 91 horas e teste com 176 horas (27 delas do `no-02`). Fonte: `resultados/dois_nos/previsao.json`.

| Previsor | RMSE teste | Skill teste |
|---|---|---|
| Persistência | 8,50 | 0 |
| Ridge | 8,05 | +0,053 |
| MLP (5 sementes) | 8,39 ± 0,11 | +0,013 ± 0,013 |
| Gradient boosting | 8,62 | −0,014 |

Leitura, pela regra do protocolo: nenhum modelo supera a persistência de forma clara. Com uma dobra, a condição de manter o sinal em todas as dobras não pode ser avaliada.

#### Rodada final (banco de 35 dias)

[PENDENTE: tabela da trilha fixa da rodada final, só com o `no-01`: horas completas, número de dobras, RMSE, MAE e skill score de cada previsor na validação (todas as dobras juntas e por dobra) e no teste final, com a MLP pela média e pelo desvio das 5 sementes.]

[PENDENTE: a mesma tabela para a rodada de sensibilidade com os dois nós.]

### 3.2 Trilha ajustada (sensibilidade)

A busca de hiperparâmetros (`--tune`, grade em `docs/grade-hiperparametros.json`) ainda não foi rodada com dados reais.

[PENDENTE: combinação escolhida para cada modelo na validação, RMSE e skill score de cada tentativa, e os resultados da trilha ajustada na validação e no teste final, ao lado dos da trilha fixa.]

### 3.3 Validação prospectiva

Previsões gravadas pelo job horário antes de a hora-alvo terminar, no `no-01`.

| Versão | Treino | Horas avaliáveis | RMSE do modelo | RMSE da persistência | Skill score | Intervalo (bootstrap em blocos diários) |
|---|---|---|---|---|---|---|
| `ridge v0` (provisório) | 17/10/2026, cerca de 8 dias | 304 (17/10 a 07/11/2026) | 8,83 | 8,42 | −0,049 | −0,094 a −0,015 |
| `ridge v1` | 09/11/2026, 494 horas do `no-01`, alpha 10 | [PENDENTE] | [PENDENTE] | [PENDENTE] | [PENDENTE] | [PENDENTE] |
| Versões novas dos três modelos, treinadas depois da rodada final | [PENDENTE] | [PENDENTE] | [PENDENTE] | [PENDENTE] | [PENDENTE] | [PENDENTE] |

Fonte da linha do `ridge v0`: `docs/limitacoes-do-tcc.md`, item 3. O `v0` é provisório e não representa os modelos da avaliação offline. As 18 horas de previsão do `no-02` não entram: o modelo foi treinado no `no-01`, e o `no-02` media em outro local.

### 3.4 Previsões retroativas (relatadas à parte)

Previsões recalculadas depois do fato, só com as leituras anteriores à hora-alvo. Não são validação prospectiva e não entram no conjunto da seção 3.3.

| Versão | Horas | RMSE do modelo | RMSE da persistência | Skill score | Intervalo |
|---|---|---|---|---|---|
| `ridge v0-retro` | 171 | 6,82 | 7,07 | +0,034 | −0,060 a +0,069 (inclui zero) |
| `ridge v1-retro` e versões novas | [PENDENTE] | [PENDENTE] | [PENDENTE] | [PENDENTE] | [PENDENTE] |

Fonte: horas, skill score e intervalo em `docs/limitacoes-do-tcc.md`, item 3. Os dois RMSE foram calculados em 13/11/2026 sobre a tabela `forecasts` do banco congelado, com `analytics.forecast_scores`, nas 171 horas do `no-01` que têm observação, persistência e previsão retroativa (de 13/10 a 07/11/2026); a mesma conta reproduz as 171 horas e o skill score de +0,034 já documentados, e as 304 horas e −0,049 do `ridge v0`. As primeiras 5 horas-alvo recalculadas foram as de 17/10 às 18:00 UTC e de 18/10 das 18:00 às 21:00 UTC, depois de uma queda do túnel (`docs/planejamento-e-estado.md`, seção 7).

Gráfico de previsto × observado do teste final: `resultados/figuras/previsto_observado.png` (avaliação preliminar), gerado pelo `result_figures` a partir de `resultados/no-01/previsao_teste.csv`, com o observado, a persistência e o Ridge. [PENDENTE: a mesma figura com o teste final da rodada final.]

## 4. Concordância entre os nós

O `no-02` mede ao lado do `no-01`, no mesmo apoio, desde 11/11/2026, às 14:18 em Brasília (17:18 UTC). A sobreposição está em curso e o período ainda não foi congelado; a única execução do `compare_nodes` foi um teste de funcionamento numa cópia do banco vivo, em 13/11/2026, cujo resultado não vale como análise e não é citado aqui.

| Item | Valor |
|---|---|
| Período de sobreposição analisado | [PENDENTE: início e fim, e o banco congelado com SHA-256] |
| Horas cheias no período e estado das horas de cada nó | [PENDENTE] |
| Horas pareadas | [PENDENTE] |
| Média de cada nó | [PENDENTE] |
| Viés (`no-01` − `no-02`), MAE e RMSE | [PENDENTE] |
| r de Pearson e R² | [PENDENTE] |
| Reta de regressão (`no-01` em função do `no-02`) | [PENDENTE] |
| Bland-Altman: viés e limites de concordância de 95% | [PENDENTE] |
| Por faixa de umidade (até 75% e acima de 75%) | [PENDENTE] |
| Com as horas suspeitas incluídas (`--include-suspect`) | [PENDENTE] |

[PENDENTE: gráfico de dispersão e gráfico de Bland-Altman, a partir de `concordancia_nos_pares.csv`.]

[PENDENTE: comparação das horas suspeitas de um nó com as leituras do outro nas mesmas horas, para a discussão da causa das horas suspeitas.]
