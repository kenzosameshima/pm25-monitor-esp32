# O job de previsão grava direto no SQLite

O job horário abre o banco e grava só na tabela `forecasts`, em vez de enviar as previsões por uma rota `POST` da API. A API deixa de ser o único escritor, mas o job faz uma transação curta por hora numa tabela que a API não usa: o WAL serializa as gravações e a conexão espera até 10 s por uma trava. A rota `POST` manteria um escritor só, ao custo de mais código, de outro token e de mais superfície exposta.

## Consequences

Há dois escritores no banco (a API e o job), então o job não pode tocar em `measurements`, que é imutável. Uma previsão é idempotente por nó, hora-alvo, modelo e versão, e rodar o job de novo na mesma hora não duplica nada.
