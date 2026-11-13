# Roteiro da rodada final de avaliação

Passo a passo para executar a rodada final definida em [`protocolo-de-avaliacao.md`](protocolo-de-avaliacao.md), quando o banco de pelo menos 35 dias puder ser congelado. Este roteiro não muda o protocolo: ele só fixa a ordem, os caminhos e onde registrar cada resultado. **Nada aqui foi executado.** Os campos de registro, no fim, estão marcados com [PENDENTE].

Regras que valem do começo ao fim:

- A rodada final do `train_forecast` roda **uma vez**. Não se roda de novo depois de ver os números, não se altera a grade, as métricas nem a regra de relato, e nenhum modelo é escolhido pelo teste final. Se a execução falhar por motivo técnico antes de gravar o relatório, pode ser repetida com o mesmo comando; registre a falha na seção 7.
- Todos os scripts de análise só leem o banco. O único passo que escreve algo fora de `resultados/` é o 5 (`fit_forecast`), que grava modelos novos na pasta do job horário.
- As saídas vão para `resultados/rodada-final/`, e não para a raiz de `resultados/`, para não sobrescrever os arquivos da avaliação preliminar de 09/11/2026 (`periodo.json`, `comparacao_cetesb.json`, `no-01/previsao.json`, `dois_nos/previsao.json`), citados em `limitacoes-do-tcc.md`. As opções dos comandos são as do protocolo; só a pasta de saída difere.

## 0. Antes de começar

1. O período começa em 09/10/2026 e precisa de pelo menos 35 dias completos: o último dia (`$FIM`) é 12/11/2026 ou depois, e já tem de ter terminado no horário de Brasília. Escolha `$FIM` antes de olhar qualquer resultado e não o mude depois.
2. O checkout usado tem este roteiro e o `check_protocol_clean.py` (a branch foi integrada à `main`).
3. O ambiente tem as dependências de previsão: `pip install -r requirements-ml.txt`.
4. O CSV de MP2,5 (média horária) da estação Osasco foi exportado do QUALAR para o mesmo período, de 09/10/2026 a `$FIM`, e salvo em `resultados\rodada-final\`.

Os comandos são para o PowerShell, a partir da pasta `server` do checkout:

```powershell
cd C:\temp\ws-vscode\github\pm25-monitor-esp32\server
$PY = ".\.venv\Scripts\python.exe"
$env:PYTHONUTF8 = "1"
$INICIO = "2026-10-09"
$FIM = "<último dia, AAAA-MM-DD>"
$OUT = "..\resultados\rodada-final"
$BANCO = "$OUT\pm25-congelado-${INICIO}_${FIM}.db"
$CETESB = "$OUT\<arquivo exportado do QUALAR>.csv"
New-Item -ItemType Directory -Force "$OUT\no-01", "$OUT\dois_nos", "$OUT\com_horas_suspeitas" | Out-Null
```

## 1. Conferir o protocolo e a grade

```powershell
& $PY -m scripts.check_protocol_clean
```

O script termina com código 0 e mostra o commit atual e o último commit de `docs/protocolo-de-avaliacao.md` e de `docs/grade-hiperparametros.json`. Com código 1, algum dos dois arquivos não está commitado ou tem alterações: **pare**. Uma mudança no protocolo só vale se for commitada, com o motivo, antes de rodar. Copie a saída para a seção 7.

## 2. Congelar o banco

```powershell
& $PY -m scripts.period_metrics --start $INICIO --end $FIM --devices no-01 --out-dir $OUT --freeze
Get-FileHash $BANCO -Algorithm SHA256
```

O `--freeze` copia o banco vivo pela API de backup do SQLite, sem gravar nele, e calcula as métricas do período sobre a cópia. Saídas em `resultados\rodada-final\`: o banco congelado, `periodo.json` (com `congelamento.sha256`), `completude_diaria.csv`, `perfil_hora.csv` e `perfil_dia_semana.csv`.

1. Confira que o hash do `Get-FileHash` é igual ao `congelamento.sha256` do `periodo.json` e registre o caminho e o SHA-256 na seção 7.
2. Copie o banco congelado para um segundo disco e confira o hash da cópia.
3. Daqui em diante, todos os comandos usam `--db $BANCO`. O banco congelado não é mais alterado nem regenerado.

## 3. Rodada final do `train_forecast`

Análise principal, só com o `no-01`. É o comando do protocolo, com os caminhos reais:

```powershell
& $PY -m scripts.train_forecast --db $BANCO --devices no-01 --tune ..\docs\grade-hiperparametros.json --seeds 5 --out "$OUT\no-01\previsao.json" --predictions-csv "$OUT\no-01\previsao_teste.csv"
```

Rodada de sensibilidade, com os dois nós juntos:

```powershell
& $PY -m scripts.train_forecast --db $BANCO --devices no-01,no-02 --tune ..\docs\grade-hiperparametros.json --seeds 5 --out "$OUT\dois_nos\previsao.json" --predictions-csv "$OUT\dois_nos\previsao_teste.csv"
```

Cada execução grava o relatório (trilha fixa em `results`, trilha ajustada em `tuned`, com `environment` e `database`), o CSV das previsões do teste e o `previsao_teste_ajustado.csv`. Confira, em cada `previsao.json`:

- `database.sha256` é o hash registrado no passo 2;
- `folds` é 2 ou mais;
- `devices` é o esperado.

Na sensibilidade, lembre que o `no-02` mediu na zona sul da capital até 11/11/2026 e ao lado do `no-01` depois disso.

## 4. Métricas do período e comparação com a CETESB, com e sem horas suspeitas

O `periodo.json` sem as horas suspeitas já saiu no passo 2. Com elas:

```powershell
& $PY -m scripts.period_metrics --start $INICIO --end $FIM --devices no-01 --db $BANCO --out-dir "$OUT\com_horas_suspeitas" --include-suspect
```

Comparação com a CETESB, sem e com as horas suspeitas:

```powershell
& $PY -m scripts.compare_cetesb --cetesb $CETESB --db $BANCO --devices no-01 --start $INICIO --end $FIM --out-dir $OUT
& $PY -m scripts.compare_cetesb --cetesb $CETESB --db $BANCO --devices no-01 --start $INICIO --end $FIM --out-dir "$OUT\com_horas_suspeitas" --include-suspect
```

Não use `--freeze` aqui: as métricas têm de sair do banco congelado no passo 2. Confira que o campo `banco` dos dois `periodo.json` é o nome do banco congelado.

## 5. Treinar as versões novas com o `fit_forecast`

Só depois dos passos 3 e 4. O protocolo manda treinar versões novas dos três modelos, que o job horário grava ao lado das anteriores, sem eleger um modelo. Já existem `ridge-v0` e `ridge-v1` em `data\models`; as versões novas usam `v2` nos três modelos, para ficarem identificadas como as da rodada final.

```powershell
& $PY -m scripts.fit_forecast --model ridge --version v2 --devices no-01 --db $BANCO
& $PY -m scripts.fit_forecast --model gboost --version v2 --devices no-01 --db $BANCO
& $PY -m scripts.fit_forecast --model mlp --version v2 --devices no-01 --db $BANCO
```

- **Este passo põe os modelos em produção:** os arquivos vão para `data\models`, e o job horário (`pm25-forecast`, HH:05) passa a usá-los na execução seguinte, sem reiniciar nada.
- O `fit_forecast` treina com os hiperparâmetros fixos de `forecasting.DEFAULTS`, os da trilha fixa. A combinação da trilha ajustada não entra em produção.
- Registre a linha que cada comando imprime (horas de treino, primeira e última hora, versão do scikit-learn) e o instante da instalação: as previsões de cada versão valem como validação prospectiva só a partir dele.
- Depois da primeira execução do job, confira o `data\forecast.log` e a aba "Previsto × observado" do dashboard.

## 6. Onde registrar cada resultado

| Resultado | Arquivo de origem | Onde registrar |
|---|---|---|
| Commit do protocolo e da grade, banco congelado e SHA-256 | saída dos passos 1 e 2 | Seção 7 deste roteiro; `docs/texto-tcc/resultados.md`, seção 1.1 |
| Saúde da coleta e estatísticas de PM2,5 | `rodada-final\periodo.json` e `rodada-final\com_horas_suspeitas\periodo.json` | `resultados.md`, seções 1.2 a 1.4 |
| Comparação com a CETESB, sem e com horas suspeitas | `rodada-final\comparacao_cetesb.json` e `rodada-final\com_horas_suspeitas\comparacao_cetesb.json` | `resultados.md`, seções 2.1 e 2.2 |
| Trilha fixa (validação por dobra e teste final) | `rodada-final\no-01\previsao.json`, bloco `results` | `resultados.md`, seção 3.1, "Rodada final" |
| Trilha ajustada (tentativas, combinação escolhida, resultados) | `rodada-final\no-01\previsao.json`, bloco `tuned` | `resultados.md`, seção 3.2 |
| Sensibilidade com os dois nós | `rodada-final\dois_nos\previsao.json` | `resultados.md`, seção 3.1 |
| Versões novas em produção e validação prospectiva | saída do passo 5; depois, tabela `forecasts` | `resultados.md`, seções 3.3 e 3.4; `protocolo-de-avaliacao.md` não é alterado |
| Limitações que os números novos mudam (dobras, horas de teste) | os relatórios acima | `docs/texto-tcc/limitacoes.md`, seções 3.1 e 5; `docs/limitacoes-do-tcc.md` |
| Estado do projeto | — | `docs/planejamento-e-estado.md`, seções 5, 7 e 8 |

As figuras da rodada final saem com `python -m scripts.result_figures --results ..\resultados\rodada-final`, num ambiente com `requirements-figures.txt` (fora do ambiente do servidor).

No relato, siga o protocolo: todos os previsores nas duas trilhas, inclusive os que não superam a persistência; a MLP pela média e pelo desvio das 5 sementes; uma diferença só é ganho se for maior que o desvio entre sementes e mantiver o sinal em todas as dobras; se o teste final contrariar a validação, os dois resultados são relatados. A pasta `resultados/` não é versionada: os números entram nos documentos, e o banco congelado fica guardado em dois discos.

A concordância entre os nós é outra análise, com outro banco congelado (o do período de sobreposição); o passo a passo dela está em `planejamento-e-estado.md`, seção 10.

## 7. Registro da execução

| Item | Valor |
|---|---|
| Data da rodada | [PENDENTE] |
| Commit atual (`check_protocol_clean`) | [PENDENTE] |
| Último commit do protocolo | [PENDENTE] |
| Último commit da grade | [PENDENTE] |
| Período (`$INICIO` a `$FIM`, dias) | [PENDENTE] |
| Banco congelado (caminho) | [PENDENTE] |
| SHA-256 do banco congelado | [PENDENTE] |
| Cópia no segundo disco (caminho, hash conferido) | [PENDENTE] |
| Arquivo da CETESB (nome, horas no arquivo, horas vazias) | [PENDENTE] |
| Versões (Python, numpy, pandas, scikit-learn) | [PENDENTE] |
| Dobras de validação e horas de teste (`no-01`) | [PENDENTE] |
| Falhas técnicas e repetições | [PENDENTE] |
| Versões novas instaladas (modelo, versão, instante) | [PENDENTE] |
