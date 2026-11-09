# Protocolo de avaliação dos modelos de previsão

Registrado em 09/11/2026, antes da rodada final com os dados reais. Define o que será rodado, como os resultados serão relatados e o que não será feito, para que a análise não dependa do que aparecer nos números. Mudanças neste protocolo só valem se forem commitadas antes de rodar de novo, com o motivo.

## O que já foi visto

Em 09/11/2026 rodou-se uma avaliação preliminar sobre o banco congelado de 09/10 a 08/11 (31 dias, uma dobra de validação), com hiperparâmetros fixos e sem ajuste. Ela informou este protocolo, e os resultados constam em `docs/limitacoes-do-tcc.md`. A busca de hiperparâmetros (`--tune`) **ainda não foi rodada com dados reais**.

## Pergunta e posição

A pergunta é se a média horária de PM2,5 da hora seguinte pode ser prevista, com sensores de baixo custo, melhor que a persistência (repetir o último valor). O trabalho **compara os previsores e não elege um "modelo do TCC"**. Uma conclusão como "nenhum modelo superou a persistência de forma clara" é um resultado válido.

## Dados

- Banco congelado com pelo menos 35 dias (duas dobras de validação com os padrões do script: 14 dias de treino, dobras de 7 dias, teste de 7 dias), de preferência mais, gerado por `period_metrics --freeze`, com o hash registrado.
- Análise principal: só o `no-01` (`--devices no-01`). Rodada de sensibilidade: os dois nós juntos. A concordância entre os nós é outra análise, restrita ao período em que ficarem lado a lado.
- Horas suspeitas ficam de fora, como em todas as análises do projeto; o relato com elas incluídas é feito na comparação com a CETESB.

## Trilhas

1. **Fixa (oficial).** Hiperparâmetros definidos antes de ver os dados (`forecasting.DEFAULTS`), sem alteração.
2. **Ajustada (sensibilidade).** Grade em `docs/grade-hiperparametros.json`, escolhida só na validação (menor RMSE, empate para o primeiro valor da grade). O teste final não participa da escolha. A trilha ajustada informa se o ajuste ajudaria; não substitui a trilha fixa.

Comando da rodada final (valores do período escolhido no lugar de `<início>_<fim>`):

```
python -m scripts.train_forecast --db ../resultados/pm25-congelado-<início>_<fim>.db --devices no-01 \
    --tune ../docs/grade-hiperparametros.json --seeds 5 \
    --out ../resultados/previsao.json --predictions-csv ../resultados/previsao_teste.csv
```

## Métricas e relato

- Métrica principal: RMSE e skill score sobre a persistência, nas mesmas horas, na validação (todas as dobras juntas) e no teste final. MAE como complemento.
- Todos os previsores são relatados nas duas trilhas, inclusive os que não superam a persistência, com o número de horas de cada etapa e as dobras.
- A MLP é relatada pela média e pelo desvio das 5 sementes, nunca pela melhor.
- Uma diferença só é descrita como ganho se for maior que o desvio entre sementes (MLP) e mantiver o sinal em todas as dobras; nos demais casos, é descrita como equivalente.
- O teste final é avaliado uma vez por trilha. Se ele contrariar a validação, os dois resultados são relatados.
- Os limites constam no texto: uma ou duas dobras, poucas semanas e um nó confiável.

## Produção

- O `ridge v0` provisório continua gerando previsões prospectivas e não influenciou nenhuma escolha de hiperparâmetro.
- Em 09/11/2026 entrou em produção o `ridge v1`, treinado só com o `no-01` (494 horas, de 10/10 a 07/11, Ridge com alpha 10 fixo), para acumular validação prospectiva antes da rodada final. Como o `v0`, ele não influencia nenhuma escolha de hiperparâmetro nem a avaliação offline, que usa o banco congelado; o `v0` provisório (treinado em 17/10) teve skill de −0,049 na validação prospectiva, e as previsões do `v1` valem como validação prospectiva só a partir de sua instalação.
- Depois da rodada final, treinam-se versões novas dos três modelos (`fit_forecast`), que o job horário grava ao lado do `v0`, para acumular validação prospectiva de todos. Não há uma regra de escolha de um único modelo. Se for preciso indicar um recomendado, a regra é: Ridge, a menos que outro tenha RMSE de validação pelo menos 5% menor e melhor em todas as dobras (a MLP, pela média das sementes).

## O que não será feito

- Alterar a grade, as métricas ou a regra de relato depois de ver os resultados da rodada final.
- Escolher um modelo pelo desempenho no teste final.
- Relatar só os modelos que ficaram bem.
