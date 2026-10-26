# Horas em que o sensor não vê partículas saem na análise, não no banco

O `no-01` teve episódios com PM1, PM2,5 e PM10 em 0,0 por horas, e a causa (sensor ou ar muito limpo) não se decide só com os dados do nó. Uma hora com pelo menos 25% das leituras abaixo de 0,5 µg/m³, ou média abaixo de 1,0 µg/m³, é suspeita e fica sem média em `analytics.hourly_means`, que o dashboard, a API, o treino, o job de previsão e as métricas do período compartilham. As leituras não são marcadas nem apagadas: `measurements` é imutável, o banco congelado mantém o hash, e a regra pode ser revista sem mexer nos dados.

## Considered Options

- **Marcar a qualidade na ingestão:** só vale para leituras novas, porque a tabela é imutável, e uma leitura zerada sozinha não é implausível.
- **Cortar o período a partir do primeiro episódio:** jogaria fora dias bons, já que os episódios começaram em 12/10 e voltaram em 25/10.
- **Manter tudo e só avisar:** deixa as horas em zero entrarem nas médias, nos modelos e no texto do TCC.

## Consequences

O treino perde linhas: um atraso ausente tira a linha, então 26 horas suspeitas reduzem o conjunto de 334 para 256 linhas. O job horário não prevê enquanto a hora anterior for suspeita. `period_metrics` e `compare_cetesb` têm `--include-suspect` para a análise de sensibilidade e para conferir a regra contra a estação de referência sem ajustar os limites. Se a CETESB mostrar ar tão limpo quanto o nó nessas horas, a regra deve ser descartada.
