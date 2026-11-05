# A saúde da coleta usa uma janela fixa, a mesma no painel, na API e no período

O painel (e a API de leitura, que alimenta o app) e o `period_metrics` calculavam completude e maior lacuna de jeitos diferentes. O painel contava os minutos esperados desde a primeira leitura do nó, se ela fosse depois do início da janela; o `period_metrics` contava a janela inteira e separava o trecho antes da primeira leitura como "bordas". Para o `no-01` em 09/10 a 03/11 (26 dias), isso dava 98,19% num e 97,53% no outro, e no `no-02` 15,1% contra 8,2%.

A conta passou a ser uma só, `analytics.minute_health`, usada por `analytics.collection_health` (painel, API, app) e por `period_metrics.operational_metrics`. A janela é fixa: todos os minutos dela são esperados, também os de antes da primeira leitura e os de depois da última, e a maior lacuna inclui esses dois trechos. Os minutos de cada borda continuam à parte em `lacunas_min.bordas`.

## Considered Options

- **Contar desde a primeira leitura nos dois:** deixaria o nó recém-instalado com completude alta e esconderia que a janela do estudo não foi coberta. Daria 98,19% no texto do TCC, número mais fácil de a banca questionar.
- **Manter as duas definições e documentar a diferença:** o app e o capítulo de resultados continuariam divergindo para o mesmo intervalo.

## Consequences

Para um nó que já operava no início da janela, nada muda: o `no-01` tem os mesmos 97,5% (período do TCC), 542 min de maior lacuna, 26 reinícios e 53 duplicatas nos dois lugares. Para um nó que entra no meio da janela, o painel e o app passam a mostrar completude menor até a janela passar do início dele. O minuto que a janela corta ao meio, e o que ainda está fechando, não contam como esperados. Duplicatas são as dos lotes recebidos de `start` até `now`, inclusive.
