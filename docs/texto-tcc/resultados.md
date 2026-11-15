# Resultados

Estrutura do capítulo de resultados do TCC. Só estão preenchidos os números já congelados e documentados. Os da **rodada final** vêm do banco `pm25-congelado-2026-10-09_2026-11-14.db` (SHA-256 `5d0895330af48518807fcb635ac623579b85250787852730ae94048ffc5a2bd5`, 67.336 leituras, extraído em 15/11/2026 às 03:00 UTC), que cobre de 09/10 a 14/11/2026 (37 dias, horário de Brasília), com as saídas em `resultados/rodada-final-2026-11-14/`. Os da **avaliação preliminar** vêm do banco `pm25-congelado-2026-10-09_2026-11-08.db` (SHA-256 `2d6dfd45891e8d91f6eb34afda3748a39c38a84b4c04af94dbf206c93f293e87`, 51.820 leituras, extraído em 09/11/2026 às 04:51 UTC), de 09/10 a 08/11/2026 (31 dias), com as saídas na raiz de `resultados/`. Cada tabela indica o arquivo de onde saiu. O que ainda depende da CETESB, da validação prospectiva ou do período de sobreposição dos nós está marcado com [PENDENTE] e não deve ser preenchido antes de o resultado existir. O registro da rodada final está em [`docs/rodada-final.md`](../rodada-final.md), seção 7, e as ressalvas de cada resultado, em [`limitacoes.md`](limitacoes.md).

A rodada final do protocolo de avaliação (`docs/protocolo-de-avaliacao.md`) foi executada em 15/11/2026, uma vez por configuração, com duas dobras de validação, as trilhas fixa e ajustada e 5 sementes para a MLP. Os resultados da **avaliação preliminar** de 09/11/2026 (31 dias, uma dobra, hiperparâmetros fixos) ficam ao lado, como registro do que já tinha sido visto. A execução de 13/11/2026, descartada por ter só uma dobra de validação, não entra nas tabelas (`docs/rodada-final.md`, seção 7).

## 1. Coleta e qualidade dos dados

### 1.1 Período e conjunto de dados

| Item | Rodada final | Avaliação preliminar |
|---|---|---|
| Período analisado | 09/10 a 14/11/2026 (37 dias, horário de Brasília) | 09/10 a 08/11/2026 (31 dias) |
| Banco congelado | `pm25-congelado-2026-10-09_2026-11-14.db` | `pm25-congelado-2026-10-09_2026-11-08.db` |
| SHA-256 | `5d0895330af48518807fcb635ac623579b85250787852730ae94048ffc5a2bd5` | `2d6dfd45891e8d91f6eb34afda3748a39c38a84b4c04af94dbf206c93f293e87` |
| Leituras no banco | 67.336 | 51.820 |
| Extraído em | 15/11/2026, 03:00 UTC | 09/11/2026, 04:51 UTC |
| Nó da análise principal | `no-01` (Osasco, bairro Veloso) | `no-01` |

Fontes: bloco `congelamento` de `resultados/rodada-final-2026-11-14/periodo.json` e de `resultados/periodo.json`. O banco da rodada final tem cópia conferida pelo hash em `E:\pm25-backups\congelados\` (`docs/rodada-final.md`, seção 7).

### 1.2 Saúde da coleta

Tabela 21 do TCC. `no-01`, bloco `operacional` de `resultados/rodada-final-2026-11-14/periodo.json` (rodada final) e de `resultados/periodo.json` (preliminar).

| Indicador | Rodada final (09/10 a 14/11) | Preliminar (09/10 a 08/11) |
|---|---|---|
| Minutos esperados | 53.280 | 44.640 |
| Minutos com leitura | 51.853 | 43.390 |
| Completude | 97,3% | 97,2% |
| Maior lacuna | 542 min | 542 min |
| Mensagens perdidas | 0 | 0 |
| Reinícios | 39 | 32 |
| Duplicatas descartadas | 70 | 67 |
| RSSI médio | −44,6 dBm | −44,2 dBm |
| Minutos sem leitura, por origem | reinício 1.176; bordas 251; comunicação 0; aquisição 0; total 1.427 | reinício 999; bordas 251; comunicação 0; aquisição 0; total 1.250 |

O `no-02`, na janela preliminar, teve completude de 18,6%, 37 reinícios, 76 horas válidas e 59 horas suspeitas (`docs/limitacoes-do-tcc.md`, item 1); ele entrou em 21/10/2026 e media em outro local até 11/11/2026, por isso fica fora da análise principal. Na rodada final, o `period_metrics` rodou só com o `no-01` (`--devices no-01`), como manda o protocolo; os indicadores do `no-02` no período de 37 dias não foram calculados.

Gráfico 1 (completude diária): `resultados/rodada-final-2026-11-14/figuras/completude_diaria.png` (rodada final) e `resultados/figuras/completude_diaria.png` (preliminar), gerados pelo `result_figures` a partir do `completude_diaria.csv` de cada pasta.

### 1.3 Horas válidas, suspeitas e sem média

`no-01`, bloco `pm25` de cada `periodo.json`. As horas sem média são as esperadas menos as válidas e as suspeitas.

| Horas | Rodada final | Preliminar |
|---|---|---|
| Esperadas | 888 | 744 |
| Válidas | 778 | 651 |
| Suspeitas | 82 (9,2%) | 70 (9,4%) |
| Sem média por falta ou escassez de leituras | 28 | 23 |
| Dias com média de 24 h válida | 31 | 26 |

Na avaliação preliminar, as 70 horas suspeitas formavam 17 episódios, os maiores de 14, 13 e 9 horas (`docs/limitacoes-do-tcc.md`, item 2). A contagem de episódios não foi refeita para as 82 horas suspeitas da rodada final.

### 1.4 Estatísticas de PM2,5

Tabela 22 do TCC. Médias horárias válidas do `no-01`, sem as horas suspeitas (bloco `pm25` de cada `periodo.json`), em µg/m³.

| Estatística | Rodada final | Preliminar |
|---|---|---|
| Horas válidas | 778 | 651 |
| Média | 20,7 | 21,5 |
| Mediana | 18,7 | 19,7 |
| Desvio-padrão (amostral) | 14,6 | 15,2 |
| Percentil 5 | 3,1 | 3,3 |
| Percentil 95 | 44,1 | 44,9 |
| Máximo horário | 116,1 | 116,1 |

Médias de 24 h acima de cada referência, nos dias válidos (bloco `referencias`). Nem a OMS nem o CONAMA definem limite horário de PM2,5; a contagem de horas é só uma referência.

| Referência (média de 24 h, µg/m³) | Dias acima, rodada final (de 31) | Horas acima, rodada final (de 778) | Dias acima, preliminar (de 26) | Horas acima, preliminar (de 651) |
|---|---|---|---|---|
| OMS 2021 nível-guia e CONAMA 506/2024 PF (15) | 23 | 439 | 20 | 373 |
| OMS 2021 meta intermediária 4 e CONAMA PI-4 (25) | 10 | 290 | 10 | 262 |
| CONAMA 506/2024 PI-3 (37) | 1 | 109 | 1 | 105 |
| OMS 2021 meta intermediária 3 (37,5) | 1 | 100 | 1 | 96 |
| OMS 2021 meta intermediária 2 e CONAMA PI-2, em vigor (50) | 0 | 17 | 0 | 17 |
| CONAMA 506/2024 PI-1 (60) | 0 | 5 | 0 | 5 |
| OMS 2021 meta intermediária 1 (75) | 0 | 4 | 0 | 4 |

Gráfico 2 (perfil por hora do dia e por dia da semana): `resultados/rodada-final-2026-11-14/figuras/perfil_pm25.png` (rodada final) e `resultados/figuras/perfil_pm25.png` (preliminar), gerados pelo `result_figures` a partir do `perfil_hora.csv` e do `perfil_dia_semana.csv` de cada pasta.

### 1.5 Estatísticas de PM2,5 com as horas suspeitas incluídas (sensibilidade)

`period_metrics --include-suspect` sobre o mesmo banco congelado de cada rodada: em 15/11/2026 para a rodada final (`resultados/rodada-final-2026-11-14/com_horas_suspeitas/periodo.json`) e em 13/11/2026 para a preliminar (`resultados/com_horas_suspeitas/periodo.json`). As horas suspeitas entram com a média que tiveram; a saúde da coleta não muda. Valores em µg/m³.

| Estatística | Rodada final, sem as suspeitas | Rodada final, com as suspeitas | Preliminar, sem as suspeitas | Preliminar, com as suspeitas |
|---|---|---|---|---|
| Horas com média | 778 | 860 | 651 | 721 |
| Média | 20,7 | 18,8 | 21,5 | 19,4 |
| Mediana | 18,7 | 15,8 | 19,7 | 16,5 |
| Desvio-padrão (amostral) | 14,6 | 15,1 | 15,2 | 15,7 |
| Percentil 5 | 3,1 | 0,4 | 3,3 | 0,3 |
| Percentil 95 | 44,1 | 43,3 | 44,9 | 44,4 |
| Máximo horário | 116,1 | 116,1 | 116,1 | 116,1 |
| Dias com média de 24 h válida | 31 | 36 | 26 | 30 |

Com as horas suspeitas, os dias com média de 24 h acima de cada referência não mudam, nas duas rodadas: na final, 23, 10, 1, 1, 0, 0 e 0 (na ordem da tabela da seção 1.4), agora sobre 36 dias válidos; na preliminar, 20, 10, 1, 1, 0, 0 e 0, sobre 30. As horas acima de cada valor também são as mesmas, sobre 860 (final) e 721 (preliminar).

## 2. Comparação com a CETESB

Rodada final: [PENDENTE: aguardando o CSV do QUALAR de 09/10 a 14/11/2026]. O `compare_cetesb` não foi rodado sobre o banco da rodada final. As tabelas abaixo são as da **avaliação preliminar** (09/10 a 08/11/2026) e ficam como registro.

Estação Osasco da CETESB (código 120), médias horárias de MP2,5 do QUALAR, 744 horas no arquivo da avaliação preliminar, 10 vazias; rótulo de hora tratado como o fim da hora. Viés é a média de nó menos CETESB, e a reta é a do nó em função da CETESB. Valores em µg/m³.

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

- [PENDENTE: aguardando o CSV do QUALAR de 09/10 a 14/11/2026; com ele, as duas tabelas refeitas sobre o banco da rodada final, sem e com as horas suspeitas.]
- [PENDENTE: coordenadas oficiais da estação Osasco e a distância até o `no-01`, hoje estimada em cerca de 4,4 km.]
- [PENDENTE: confirmação pela CETESB da convenção de hora do QUALAR.]

## 3. Previsão

Previsão da média horária de PM2,5 da hora seguinte, comparada com a persistência. O skill score é um menos a razão entre o RMSE do previsor e o da persistência, nas mesmas horas. O protocolo não elege um modelo: todos os previsores são relatados nas duas trilhas.

### 3.1 Trilha fixa

#### Rodada final (banco de 37 dias)

Só o `no-01`: 574 horas completas e 2 dobras de validação, com 240 horas no total. Dobra 1: hora t de 24/10 07:00 a 31/10 07:00 UTC, 91 horas, com 240 horas de treino; dobra 2: de 31/10 07:00 a 07/11 07:00 UTC, 149 horas, com 331 horas de treino. Teste final: janela de 08/11 02:00 a 15/11 02:00 UTC (hora t), 80 horas, com 494 horas de treino; as horas-alvo do teste vão de 10/11 10:00 a 15/11 02:00 UTC. Hiperparâmetros fixos de `forecasting.DEFAULTS` (Ridge com alpha 10; gradient boosting com taxa 0,1, 100 iterações, 31 folhas e 20 amostras mínimas por folha; MLP com camadas de 32 e 16 unidades, taxa 1e-3, 200 épocas, lote 32 e paciência 15), escolhidos antes de ver os dados (a origem de cada valor está em `limitacoes.md`, seção 3.1); MLP com 5 sementes (42 a 46). Fonte: `resultados/rodada-final-2026-11-14/no-01/previsao.json`, bloco `results` (Python 3.10.11, numpy 2.2.6, pandas 2.3.3, scikit-learn 1.7.2; `database.sha256` igual ao da seção 1.1). RMSE e MAE em µg/m³; a validação junta as duas dobras; a MLP aparece pela média ± desvio-padrão amostral das sementes, e o MAE dela é o da semente de referência (42).

| Previsor | MAE validação | RMSE validação | Skill validação | MAE teste | RMSE teste | Skill teste |
|---|---|---|---|---|---|---|
| Persistência | 5,43 | 8,53 | 0 | 4,39 | 5,64 | 0 |
| Ridge | 5,45 | 8,07 | +0,054 | 3,86 | 5,20 | +0,078 |
| MLP (5 sementes) | 5,41 | 8,13 ± 0,06 | +0,047 ± 0,007 | 3,93 | 5,22 ± 0,08 | +0,075 ± 0,014 |
| Gradient boosting | 6,49 | 9,06 | −0,062 | 4,60 | 6,15 | −0,090 |

Por dobra e no teste. O `previsao.json` só traz a validação com as dobras juntas; os valores por dobra foram recalculados em 15/11/2026, em modo leitura sobre o banco congelado, com as funções do próprio `train_forecast` e os mesmos hiperparâmetros e sementes. Juntando as dobras, o recálculo reproduz exatamente o RMSE de validação e de teste do relatório (`docs/rodada-final.md`, seção 7).

| Previsor | RMSE dobra 1 (91 h) | Skill dobra 1 | RMSE dobra 2 (149 h) | Skill dobra 2 | RMSE teste (80 h) | Skill teste |
|---|---|---|---|---|---|---|
| Persistência | 10,47 | 0 | 7,10 | 0 | 5,64 | 0 |
| Ridge | 10,08 | +0,037 | 6,54 | +0,078 | 5,20 | +0,078 |
| MLP (5 sementes) | 10,09 ± 0,15 | +0,036 ± 0,015 | 6,66 ± 0,04 | +0,061 ± 0,005 | 5,22 ± 0,08 | +0,075 ± 0,014 |
| Gradient boosting | 10,92 | −0,043 | 7,70 | −0,085 | 6,15 | −0,090 |

Leitura, pela regra do protocolo (uma diferença só é ganho se for maior que o desvio entre sementes e mantiver o sinal em todas as dobras):

- **Ridge × persistência: ganho.** O skill score é positivo nas duas dobras (+0,037 e +0,078) e no teste (+0,078): o RMSE fica de 3,7% a 7,8% abaixo do da persistência. O Ridge é determinístico; não há desvio entre sementes a comparar.
- **MLP × persistência: ganho.** O skill score médio é positivo nas duas dobras (+0,036 ± 0,015 e +0,061 ± 0,005) e no teste (+0,075 ± 0,014), e é positivo nas 5 sementes em cada dobra e no teste. A diferença de RMSE para a persistência (0,38 e 0,43 µg/m³ nas dobras, 0,40 na validação junta e 0,42 no teste) é maior que o desvio entre sementes (0,15, 0,04, 0,06 e 0,08).
- **Gradient boosting × persistência: sem ganho.** O skill score é negativo nas duas dobras (−0,043 e −0,085) e no teste (−0,090): o boosting fica pior que a persistência em todas as etapas.
- **Ridge × MLP: equivalentes no teste; vantagem marginal do Ridge na validação.** Na validação junta, o RMSE médio da MLP fica 0,07 µg/m³ acima do Ridge, pouco mais que o desvio entre sementes (0,06), e o Ridge tem o menor RMSE médio nas duas dobras; na dobra 1, porém, a diferença (0,01) é muito menor que o desvio da dobra (0,15), e 2 das 5 sementes ficam abaixo do Ridge. No teste, a diferença (0,02) é menor que o desvio (0,08). Como o teste não confirma a validação, os dois resultados são relatados.
- **Validação × teste.** Concordam no sinal de todos os previsores contra a persistência. Os skill scores do teste são maiores em módulo que os da validação junta (Ridge +0,078 contra +0,054; MLP +0,075 contra +0,047; gradient boosting −0,090 contra −0,062).

O que já tinha sido visto: a dobra 1 tem as mesmas 91 horas e os mesmos números da única dobra de validação da avaliação preliminar (abaixo) e da execução descartada de 13/11/2026; a dobra 2 cobre quase a mesma semana do teste preliminar (hora t de 31/10 20:00 a 07/11 20:00 UTC), com outro treino. Das 80 horas do teste final, 50 (horas-alvo de 10/11 10:00 a 13/11 18:00 UTC) estavam no teste da execução descartada de 13/11/2026, cujos números foram vistos (`docs/protocolo-de-avaliacao.md`, "O que já foi visto"; ver `limitacoes.md`, seção 3.1).

#### Rodada final: sensibilidade com os dois nós

635 horas completas (574 do `no-01` e 61 do `no-02`), 2 dobras, validação com 255 horas e teste com 114, nas mesmas janelas. O `no-02` mediu na zona sul da capital até 11/11/2026 e ao lado do `no-01` depois disso: ele não tem horas na dobra 1, tem 15 na dobra 2 e 27 no treino do teste, todas da zona sul, e 34 no teste (horas-alvo de 12/11 07:00 a 15/11 02:00 UTC), todas do período lado a lado. Fonte: `resultados/rodada-final-2026-11-14/dois_nos/previsao.json`, bloco `results`; por dobra, o mesmo recálculo.

| Previsor | MAE validação | RMSE validação | Skill validação | MAE teste | RMSE teste | Skill teste |
|---|---|---|---|---|---|---|
| Persistência | 5,58 | 8,63 | 0 | 4,77 | 6,31 | 0 |
| Ridge | 5,59 | 8,16 | +0,055 | 4,34 | 5,91 | +0,064 |
| MLP (5 sementes) | 5,59 | 8,33 ± 0,09 | +0,036 ± 0,010 | 4,37 | 5,94 ± 0,05 | +0,058 ± 0,007 |
| Gradient boosting | 6,56 | 9,14 | −0,059 | 4,85 | 6,48 | −0,027 |

| Previsor | RMSE dobra 1 (91 h) | Skill dobra 1 | RMSE dobra 2 (164 h) | Skill dobra 2 | RMSE teste (114 h) | Skill teste |
|---|---|---|---|---|---|---|
| Persistência | 10,47 | 0 | 7,43 | 0 | 6,31 | 0 |
| Ridge | 10,08 | +0,037 | 6,87 | +0,075 | 5,91 | +0,064 |
| MLP (5 sementes) | 10,09 ± 0,15 | +0,036 ± 0,015 | 7,17 ± 0,09 | +0,035 ± 0,011 | 5,94 ± 0,05 | +0,058 ± 0,007 |
| Gradient boosting | 10,92 | −0,043 | 7,98 | −0,075 | 6,48 | −0,027 |

Leitura: o quadro é o do `no-01` sozinho. Ridge e MLP têm skill score positivo nas duas dobras e no teste (a MLP, nas 5 sementes), com diferença para a persistência maior que o desvio entre sementes: ganho, pela regra. O gradient boosting fica pior que a persistência em todas as etapas. Ridge e MLP ficam equivalentes no teste (diferença de 0,03 µg/m³, contra desvio de 0,05); na validação junta a diferença (0,16) passa o desvio (0,09), mas não na dobra 1 (0,01 contra 0,15). Os erros são maiores que os do `no-01` sozinho, e o ganho no teste, um pouco menor (Ridge +0,064 contra +0,078).

#### Avaliação preliminar (31 dias, uma dobra; registro)

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

Leitura, na época, pela regra do protocolo: nenhum modelo supera a persistência de forma clara. Com uma dobra, a condição de manter o sinal em todas as dobras não podia ser avaliada.

### 3.2 Trilha ajustada (sensibilidade)

A busca de hiperparâmetros rodou com dados reais pela primeira vez na rodada final, com `--tune ..\docs\grade-hiperparametros.json` (grade registrada antes da execução; último commit `b6173c5`, de 09/11/2026). Para cada modelo vale a combinação de menor RMSE na validação progressiva (as duas dobras juntas), com empate para a primeira da grade; o teste final não participa da escolha. Na MLP, a escolha usa só a semente de referência (42); as 5 sementes são treinadas depois, com a combinação escolhida. A trilha ajustada mostra a sensibilidade aos hiperparâmetros e não substitui a fixa; o `fit_forecast` instala só a fixa. Fonte: bloco `tuned` de cada `previsao.json`.

Tentativas no `no-01` (validação com 240 horas; RMSE em µg/m³):

| Modelo | Combinação | RMSE validação | Skill validação | Escolhida |
|---|---|---|---|---|
| Ridge | alpha 10 (a da trilha fixa) | 8,067 | +0,054 | |
| Ridge | alpha 1 | 8,064 | +0,055 | sim |
| Ridge | alpha 100 | 8,076 | +0,054 | |
| Gradient boosting | taxa 0,1, 31 folhas (a da trilha fixa) | 9,058 | −0,062 | |
| Gradient boosting | taxa 0,1, 15 folhas | 9,058 | −0,062 | |
| Gradient boosting | taxa 0,05, 31 folhas | 8,850 | −0,037 | sim |
| Gradient boosting | taxa 0,05, 15 folhas | 8,850 | −0,037 | |
| MLP (semente 42) | 32-16, taxa 0,001 (a da trilha fixa) | 8,078 | +0,053 | |
| MLP (semente 42) | 32-16, taxa 0,01 | 8,041 | +0,058 | sim |
| MLP (semente 42) | 16, taxa 0,001 | 8,325 | +0,024 | |
| MLP (semente 42) | 16, taxa 0,01 | 8,298 | +0,027 | |

No gradient boosting, 31 e 15 folhas dão o mesmo RMSE, com as duas taxas; o empate fica com 31, a primeira da grade. Com os dois nós, as combinações escolhidas são as mesmas.

Resultados da trilha ajustada no `no-01`, nas mesmas horas da trilha fixa:

| Previsor | MAE validação | RMSE validação | Skill validação | MAE teste | RMSE teste | Skill teste |
|---|---|---|---|---|---|---|
| Persistência | 5,43 | 8,53 | 0 | 4,39 | 5,64 | 0 |
| Ridge (alpha 1) | 5,48 | 8,06 | +0,055 | 3,87 | 5,21 | +0,075 |
| MLP (32-16, taxa 0,01; 5 sementes) | 5,40 | 8,19 ± 0,08 | +0,041 ± 0,010 | 3,93 | 5,23 ± 0,09 | +0,072 ± 0,017 |
| Gradient boosting (taxa 0,05, 31 folhas) | 6,25 | 8,85 | −0,037 | 4,59 | 6,04 | −0,071 |

| Previsor | RMSE dobra 1 (91 h) | Skill dobra 1 | RMSE dobra 2 (149 h) | Skill dobra 2 | RMSE teste (80 h) | Skill teste |
|---|---|---|---|---|---|---|
| Persistência | 10,47 | 0 | 7,10 | 0 | 5,64 | 0 |
| Ridge | 10,05 | +0,040 | 6,56 | +0,076 | 5,21 | +0,075 |
| MLP (5 sementes) | 10,15 ± 0,15 | +0,030 ± 0,014 | 6,70 ± 0,06 | +0,055 ± 0,009 | 5,23 ± 0,09 | +0,072 ± 0,017 |
| Gradient boosting | 10,85 | −0,037 | 7,36 | −0,038 | 6,04 | −0,071 |

Comparação com a trilha fixa:

- **Ridge:** alpha 1 e alpha 10 ficam praticamente iguais (RMSE de validação de 8,064 contra 8,067; de teste, 5,21 contra 5,20). O ganho sobre a persistência se mantém nas duas dobras e no teste (+0,040, +0,076 e +0,075).
- **Gradient boosting:** a taxa 0,05 reduz o erro na validação (8,85 contra 9,06) e no teste (6,04 contra 6,15), mas o boosting continua pior que a persistência nas duas dobras e no teste (−0,037, −0,038 e −0,071).
- **MLP:** a combinação escolhida (taxa 0,01) foi melhor na semente 42 (8,041 contra 8,078), mas, pela média das 5 sementes, fica com RMSE de validação de 8,19 ± 0,08, contra 8,13 ± 0,06 da fixa, e de teste de 5,23 ± 0,09, contra 5,22 ± 0,08: as duas trilhas são equivalentes. O ganho sobre a persistência se mantém (skill de +0,030 ± 0,014 e +0,055 ± 0,009 nas dobras e de +0,072 ± 0,017 no teste, positivo nas 5 sementes; diferenças de RMSE de 0,31, 0,39 e 0,40 µg/m³, maiores que os desvios de 0,15, 0,06 e 0,09).
- **Ridge × MLP:** o mesmo padrão da trilha fixa. No teste, equivalentes (diferença de 0,02, contra desvio de 0,09); na validação junta, a diferença (0,12) passa o desvio (0,08), mas não na dobra 1 (0,10 contra 0,15).

Trilha ajustada com os dois nós (`dois_nos/previsao.json`, bloco `tuned`; validação com 255 horas e teste com 114):

| Previsor | MAE validação | RMSE validação | Skill validação | MAE teste | RMSE teste | Skill teste |
|---|---|---|---|---|---|---|
| Persistência | 5,58 | 8,63 | 0 | 4,77 | 6,31 | 0 |
| Ridge (alpha 1) | 5,62 | 8,16 | +0,055 | 4,33 | 5,90 | +0,065 |
| MLP (32-16, taxa 0,01; 5 sementes) | 5,57 | 8,36 ± 0,10 | +0,032 ± 0,011 | 4,40 | 5,94 ± 0,08 | +0,059 ± 0,012 |
| Gradient boosting (taxa 0,05, 31 folhas) | 6,32 | 8,94 | −0,035 | 4,92 | 6,55 | −0,038 |

Por dobra, com os dois nós: Ridge +0,040, +0,072 e +0,065 (dobra 1, dobra 2 e teste); MLP +0,030 ± 0,014, +0,035 ± 0,009 e +0,059 ± 0,012, positivo nas 5 sementes; gradient boosting −0,037, −0,032 e −0,038. A leitura é a mesma do `no-01`: ganho do Ridge e da MLP sobre a persistência, boosting pior que ela.

### 3.3 Validação prospectiva

Previsões gravadas pelo job horário antes de a hora-alvo terminar, no `no-01`.

| Versão | Treino | Horas avaliáveis | RMSE do modelo | RMSE da persistência | Skill score | Intervalo (bootstrap em blocos diários) |
|---|---|---|---|---|---|---|
| `ridge v0` (provisório) | 17/10/2026, cerca de 8 dias | 304 (17/10 a 07/11/2026) | 8,83 | 8,42 | −0,049 | −0,094 a −0,015 |
| `ridge v1` | 09/11/2026, 494 horas do `no-01`, alpha 10 | [PENDENTE] | [PENDENTE] | [PENDENTE] | [PENDENTE] | [PENDENTE] |
| `ridge v2`, `gboost v2` e `mlp v2` | 15/11/2026, 574 horas do `no-01` (hora t de 10/10 07:00 a 15/11 01:00 UTC), hiperparâmetros da trilha fixa; em produção desde 03:20 UTC | [PENDENTE] | [PENDENTE] | [PENDENTE] | [PENDENTE] | [PENDENTE] |

Fonte da linha do `ridge v0`: `docs/limitacoes-do-tcc.md`, item 3. O `v0` é provisório e não representa os modelos da avaliação offline. As 18 horas de previsão do `no-02` não entram: o modelo foi treinado no `no-01`, e o `no-02` media em outro local.

As versões `v2` foram treinadas pelo `fit_forecast` sobre o banco congelado da rodada final e gravadas em `server/data/models` em 15/11/2026 (`ridge-v2` às 03:20:47, `gboost-v2` às 03:20:48 e `mlp-v2` às 03:20:50 UTC); as previsões delas valem como validação prospectiva a partir desses instantes. A primeira execução do job horário depois da instalação, às 04:05:02 UTC, gravou sem erro as previsões em tempo real das três versões `v2`, ao lado do `ridge v0` e do `ridge v1`, para a hora-alvo de 04:00 UTC, nos dois nós (`server/data/forecast.log`; `docs/rodada-final.md`, seção 7). [PENDENTE: horas avaliáveis, RMSE, skill score e intervalo de cada versão `v2`, depois de acumular as previsões; a avaliação das previsões do `ridge v1` desde 09/11/2026, que estão na tabela `forecasts` do banco congelado, ainda não foi calculada.]

### 3.4 Previsões retroativas (relatadas à parte)

Previsões recalculadas depois do fato, só com as leituras anteriores à hora-alvo. Não são validação prospectiva e não entram no conjunto da seção 3.3.

| Versão | Horas | RMSE do modelo | RMSE da persistência | Skill score | Intervalo |
|---|---|---|---|---|---|
| `ridge v0-retro` | 171 | 6,82 | 7,07 | +0,034 | −0,060 a +0,069 (inclui zero) |
| `ridge v1-retro` e versões `v2-retro` | [PENDENTE] | [PENDENTE] | [PENDENTE] | [PENDENTE] | [PENDENTE] |

Fonte: horas, skill score e intervalo em `docs/limitacoes-do-tcc.md`, item 3. Os dois RMSE foram calculados em 13/11/2026 sobre a tabela `forecasts` do banco congelado, com `analytics.forecast_scores`, nas 171 horas do `no-01` que têm observação, persistência e previsão retroativa (de 13/10 a 07/11/2026); a mesma conta reproduz as 171 horas e o skill score de +0,034 já documentados, e as 304 horas e −0,049 do `ridge v0`. As primeiras 5 horas-alvo recalculadas foram as de 17/10 às 18:00 UTC e de 18/10 das 18:00 às 21:00 UTC, depois de uma queda do túnel (`docs/planejamento-e-estado.md`, seção 7).

A execução das 04:05:02 UTC de 15/11/2026 gravou também 111 previsões `v2-retro`, para as horas-alvo de 14/11 04:00 a 15/11 03:00 UTC. As de horas-alvo até 15/11 02:00 UTC usam linhas que estavam no treino dos `v2` (hora t até 01:00) e não servem como avaliação; nenhuma `v2-retro` foi avaliada.

Gráfico de previsto × observado do teste final: `resultados/rodada-final-2026-11-14/figuras/previsto_observado.png` (rodada final, a partir de `resultados/rodada-final-2026-11-14/no-01/previsao_teste.csv`) e `resultados/figuras/previsto_observado.png` (avaliação preliminar, a partir de `resultados/no-01/previsao_teste.csv`), gerados pelo `result_figures`, com o observado, a persistência e o Ridge da trilha fixa.

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
