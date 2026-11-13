# Limitações e ameaças à validade

Rascunho da seção para o texto final do TCC, redigido a partir de [`docs/limitacoes-do-tcc.md`](../limitacoes-do-tcc.md), que continua sendo o registro de trabalho. Os números desta seção vêm do banco congelado em 09/11/2026 (`pm25-congelado-2026-10-09_2026-11-08.db`, SHA-256 `2d6dfd45891e8d91f6eb34afda3748a39c38a84b4c04af94dbf206c93f293e87`), que cobre de 09/10 a 08/11/2026 (31 dias, horário de Brasília), e foram produzidos pelos scripts `period_metrics`, `compare_cetesb` e `train_forecast`; a fonte de cada número está indicada entre parênteses. A análise principal usa apenas o nó `no-01`. As decisões de projeto citadas estão registradas em [`docs/adr`](../adr/). Os pontos ainda sem resultado estão reunidos na última subseção e marcados com [PENDENTE].

As ameaças estão organizadas em quatro grupos: validade externa (o que pode ser generalizado), validade de construto e de medição (se o que foi medido corresponde ao que se quer afirmar), validade interna e de conclusão estatística (se as comparações sustentam as conclusões) e limitações do sistema que não afetam os resultados.

## 1. Validade externa

### 1.1 Período de coleta curto e um único ponto de medição

A coleta analisada cobre 31 dias, abaixo das cerca de cinco semanas recomendadas no próprio projeto para a avaliação dos modelos (README, seção "Avaliação de modelos de previsão"). Apenas um nó tem dados confiáveis no período: o `no-01`, instalado em Osasco (bairro Veloso), no apoio externo de uma janela, coberto por uma estrutura da casa, a 1,1 m do chão. O `no-02` entrou em operação em 21/10/2026 e, durante todo o período congelado, mediu na zona sul da capital, a mais de 15 km do `no-01`; os dois nós, portanto, não mediram o mesmo ar.

No período, o `no-01` teve completude de 97,2% (43.390 de 44.640 minutos esperados), 651 horas válidas de 744 esperadas e 26 dias com média de 24 h válida (`period_metrics`, `resultados/periodo.json`). Na mesma janela de 31 dias, o `no-02` teve completude de 18,6%, 37 reinícios, 76 horas válidas e 59 horas suspeitas (`period_metrics`). A definição de completude é a de janela fixa, igual no painel, na API e no `period_metrics`: o trecho anterior à primeira leitura de um nó conta como esperado (ADR 0005). Em 22/10/2026, entre cerca de 09:27 e 15:50 UTC, o `no-02` reiniciou cerca de 27 vezes seguidas, uma a cada 15 minutos aproximadamente, com o campo `rssi` ausente; o comportamento é compatível com a regra do firmware de reiniciar após 15 minutos sem Wi-Fi, mas a causa não foi confirmada. Em 05 e 06/11/2026 o `no-02` enviou cerca de 1.400 leituras por dia, com uma interrupção em 07/11/2026.

Em consequência, os resultados são preliminares e não se generalizam para outros locais, para outras estações do ano nem para episódios de poluição que o mês analisado não cobriu. Com os nós em locais diferentes, o período congelado também não permite medir a concordância entre dois sensores iguais expostos ao mesmo ar.

Como mitigação, o período e esta limitação constam no texto, e a análise principal usa apenas o `no-01` (`period_metrics --devices no-01`, `compare_cetesb --devices no-01`, `train_forecast --devices no-01`); a rodada do `train_forecast` com os dois nós é apresentada como análise de sensibilidade. A concordância entre sensores é tratada em análise separada, restrita ao período em que os nós ficaram lado a lado: o `no-02` foi instalado ao lado do `no-01` em 11/11/2026, às 14:18 em Brasília, depois do período congelado (ver 5).

## 2. Validade de construto e de medição

### 2.1 Horas suspeitas do `no-01`

Em episódios, o sensor do `no-01` registrou 0,0 µg/m³ em PM1, PM2,5 e PM10 enquanto continuava respondendo. O projeto define como suspeita a hora com pelo menos 25% das leituras abaixo de 0,5 µg/m³ de PM2,5, ou com média abaixo de 1,0 µg/m³; essa hora fica sem média na análise, e o banco imutável não é alterado (ADR 0004).

No período, 70 das 744 horas esperadas são suspeitas (9,4%; eram 26 em 26/10 e 44 em 04/11), além de 23 horas sem média por falta ou escassez de leituras, o que deixa 651 horas válidas (`period_metrics`). A causa não está decidida: pode ser defeito do sensor ou ar muito limpo. Na comparação com a estação Osasco da CETESB, incluir as horas suspeitas melhora o ajuste: 711 horas pareadas, viés de +6,8 µg/m³ e r de 0,45, contra 641 horas, +8,3 µg/m³ e r de 0,43 sem elas (`compare_cetesb`, com e sem `--include-suspect`). Conferidas hora a hora contra a estação, as 70 horas suspeitas formam 17 episódios (os maiores, de 14, 13 e 9 horas), com média do nó de 0,69 µg/m³ (mediana de 0,25). Nessas horas a estação marca valores mais baixos (mediana de 7,0 µg/m³, contra 12,0 nas horas válidas; 44% das horas com 5 µg/m³ ou menos, contra 16%), mas em 33% das horas suspeitas ela marca 10 µg/m³ ou mais, com máximos de até 27 (`compare_cetesb --include-suspect`, CSV das horas pareadas). Um nó que lê zero nos três canais por horas enquanto a estação marca de 5 a 27 µg/m³ não é compatível apenas com ar limpo; a explicação mais provável é uma falha intermitente do sensor, talvez coincidente com momentos de ar mais limpo, mas isso não está provado.

A escolha afeta os resultados nos dois sentidos: retirar essas horas pode enviesar para cima as médias e as comparações, se o ar estava de fato limpo; mantê-las pode subestimar o PM2,5, se o sensor falhou.

Como mitigação, a regra é única e aplicada no mesmo ponto do código (`analytics.hourly_means`), de modo que painel, API, treino e métricas usam as mesmas horas (ADR 0004), e os resultados são relatados com e sem as horas suspeitas (`compare_cetesb --include-suspect` e a opção equivalente do `period_metrics`; saídas em `resultados/` e em `resultados/com_horas_suspeitas/`).

### 2.2 Umidade relativa e viés do PMS5003

Acima de cerca de 75% de umidade relativa, o PMS5003 tende a superestimar o PM2,5. Das 641 horas pareadas com a CETESB, apenas 16 tiveram umidade média acima de 75%, com viés de +21,4 µg/m³ nessas horas contra +8,0 µg/m³ nas demais (`compare_cetesb`); 16 horas não bastam para estimar correlação nem regressão. É possível que o BME280 meça a umidade do ar sob a cobertura, mais baixa que a do ambiente, ou a do interior da caixa; isso não foi verificado.

O viés em relação à estação de referência pode, portanto, depender da umidade, mas a amostra não permite concluir. Nenhuma correção por umidade foi aplicada nem avaliada.

Como mitigação, o aplicativo avisa quantas horas da janela consultada passaram do limite, e a comparação com a CETESB é relatada com a separação por faixa de umidade.

### 2.3 Comparação com a estação da CETESB: distância, microambiente e convenção de hora

A referência é a estação Osasco da CETESB (código 120; Av. dos Autonomistas, esquina com a Rua São Maurício, Vila Quitaúna, segundo documento da CETESB), com as médias horárias de MP2,5 do QUALAR. O endereço da estação não está bem documentado, e um segundo candidato (Rua Tomé de Souza, 438, Jardim D'Abril) foi descartado. O `no-01` fica a cerca de 4,4 km da estação; a estimativa foi feita pelo eixo da Rua São Maurício e da rua do nó no OpenStreetMap, sem o número dos imóveis, com incerteza de poucas centenas de metros (com o segundo candidato, seriam cerca de 2,5 km). O nó está no apoio externo de uma janela, coberto, a 1,1 m do chão e junto à fachada, enquanto a estação segue o padrão regulatório de instalação. O PMS5003 não foi calibrado.

Foram pareadas 641 horas (a CETESB tem 10 horas vazias nas 744 do arquivo). A média do nó foi de 21,2 µg/m³ contra 12,9 µg/m³ da CETESB, com viés de +8,3 µg/m³, MAE de 12,0, RMSE de 16,0, correlação de Pearson de 0,43 (R² de 0,18) e reta do nó em função da CETESB com inclinação 0,82 e intercepto 10,6 (`compare_cetesb`, `resultados/comparacao_cetesb.json`). Os valores da CETESB são inteiros.

O nó lê mais alto que a referência e acompanha pouco a variação horária dela. O coeficiente de correlação baixo mistura o erro do sensor, a distância entre os pontos, o microambiente (fachada, cobertura, altura) e a resolução inteira da estação, e a comparação não separa essas causas. Ela mede a concordância entre dois pontos e não valida o PMS5003 como instrumento de referência.

O rótulo de hora do QUALAR foi tratado como o fim da hora (01:00 = 00:00 a 01:00), segundo a documentação do pacote qualR; com o rótulo tratado como início, o r cai para 0,39 e o RMSE sobe para 16,4 (`compare_cetesb --hour-label start`). A convenção ainda precisa ser confirmada com a CETESB. Como mitigação, os resultados são relatados com e sem as horas suspeitas e separados por umidade, e a distância e a descrição do ponto de instalação constam no texto.

## 3. Validade interna e de conclusão estatística

### 3.1 Hiperparâmetros fixos e validação progressiva com poucas dobras

Na avaliação preliminar, os hiperparâmetros dos modelos são fixos e foram definidos antes de ver os dados (`forecasting.DEFAULTS`: Ridge com alpha 10; gradient boosting com taxa 0,1, 100 iterações, 31 folhas e 20 amostras mínimas por folha; MLP com camadas de 32 e 16 unidades, taxa 1e-3, 200 épocas e paciência 15). Não houve busca de hiperparâmetros: a validação progressiva compara os modelos e não os ajusta. Com os padrões do script (14 dias mínimos de treino, dobras de 7 dias e teste de 7 dias), uma dobra de validação exige pelo menos 28 dias; com 31 dias há exatamente uma.

Só com o `no-01`, a avaliação teve 494 horas completas, 91 horas na validação e 149 no teste final, de 31/10 a 07/11/2026 (`train_forecast`, `resultados/no-01/previsao.json`). O RMSE no teste (µg/m³) e o skill score sobre a persistência foram: persistência 7,08; Ridge 6,50 (+0,082); MLP 6,90 ± 0,15 (+0,025 ± 0,021, média de 5 sementes); gradient boosting 7,47 (−0,055). Com os dois nós juntos o quadro é o mesmo, com erros maiores (persistência 8,50; Ridge 8,05, +0,053; MLP 8,39 ± 0,11; gradient boosting 8,62), porque o teste inclui 27 horas do `no-02` (`resultados/dois_nos/previsao.json`).

Nenhum modelo supera a persistência de forma clara: o Ridge fica um pouco acima, a MLP é estatisticamente igual a ela e o gradient boosting fica pior. Com uma dobra de validação e 149 horas de teste, a diferença do Ridge não é sólida. Sem ajuste, um modelo mais flexível (MLP, gradient boosting) pode perder apenas por estar mal calibrado, o que enfraquece a comparação entre modelos.

Como mitigação, o relatório é reproduzível (versões das bibliotecas e hash do banco congelado), a MLP é treinada com várias sementes (`--seeds`) e o skill score é calculado contra a persistência sobre as mesmas horas. Os hiperparâmetros não foram alterados depois de ver o teste final. O protocolo de avaliação, registrado em 09/11/2026 (`docs/protocolo-de-avaliacao.md`), prevê para a rodada final uma trilha ajustada, de sensibilidade, com a grade registrada antes da execução (`docs/grade-hiperparametros.json`) e escolhida só na validação, com o teste final fora da escolha; essa rodada ainda não foi executada (ver 5).

### 3.2 Previsões retroativas separadas das prospectivas

Em 17 e 18/10/2026, uma queda do túnel deixou 5 horas-alvo sem previsão. Elas foram recalculadas depois, apenas com as leituras anteriores a cada hora-alvo, e gravadas na versão `v0-retro`, à parte das previsões em tempo real (`v0`, 28 na data do registro). Desde 20/10/2026 os scripts agendados recalculam sozinhos as quedas de até 24 horas, também na versão `-retro`.

O `ridge v0`, treinado em 17/10/2026 com cerca de 8 dias de dados e nunca retreinado, teve no `no-01` desempenho pior que a persistência na validação prospectiva: nas 304 horas avaliáveis (17/10 a 07/11/2026), RMSE de 8,83 µg/m³ contra 8,42 da persistência, com skill score de −0,049 (intervalo de −0,094 a −0,015 por bootstrap em blocos diários, aproximado porque dias seguidos são correlacionados). A versão `v0-retro` teve skill score de +0,034 em 171 horas (intervalo de −0,060 a +0,069, que inclui zero), mas cobre só horas de lacuna e não é comparável. As previsões do `no-02` (18 horas) não servem para a avaliação: o modelo foi treinado no `no-01`, e o `no-02` estava em outro local. Esses números constam em `docs/limitacoes-do-tcc.md` e foram calculados sobre a tabela `forecasts` do banco congelado.

O `v0` é um modelo provisório e não representa os modelos da avaliação offline (o Ridge ficou acima da persistência no teste, com treino maior); um resultado não se transfere para o outro. As previsões retroativas não são validação prospectiva e não podem entrar no mesmo conjunto das previsões em tempo real. A validação prospectiva das versões finais só começa quando elas entrarem em produção.

Como mitigação, as versões ficam separadas e identificadas no painel e no aplicativo, as métricas são relatadas em separado, e esta ressalva consta no texto. A gravação das previsões pelo job horário diretamente no banco, em uma tabela que a API não usa, está registrada na ADR 0001.

### 3.3 Reinícios do `no-01`

O `no-01` reiniciou 32 vezes em 31 dias, cerca de uma vez por dia (`period_metrics`). Dos 32 reinícios, 23 deixaram no máximo 2 minutos sem leitura, 3 deixaram 3 minutos e 6 deixaram lacunas de 6 a 543 minutos (6, 26, 34, 52, 320 e 543); o padrão aponta para reinício por software (watchdog ou rotina) e não para falta de energia. Nenhuma leitura se perdeu (0 mensagens perdidas): o buffer em flash e o reenvio funcionaram. O tempo de operação antes de cada reinício vai de poucos minutos (nos dias de instalação, 09/10 e 20 a 21/10/2026) a cerca de 98 horas; 19 dos 32 passaram de 15 horas. O `api.log` não registra o motivo dos reinícios (nenhuma ocorrência de watchdog, reset ou brownout).

Cada reinício custa poucos minutos de dados, e o efeito na completude é pequeno: 97,2% no período, com 999 dos 1.250 minutos de lacuna devidos a reinícios e 251 à borda inicial, antes da primeira leitura (`period_metrics`). A causa, porém, é desconhecida e pode se repetir.

A causa não foi investigada. No período analisado, o firmware não informava o motivo do reinício; identificá-la exige registrar a causa do reset no firmware e acompanhar o nó por mais tempo (ver 5).

## 4. Limitações do sistema sem efeito nos resultados

### 4.1 Servidor único e segurança da implantação

O sistema tem um só servidor e um só banco, que são um ponto único de falha (ADR 0003). As tarefas agendadas do Windows rodam como SYSTEM sem restringir as permissões da pasta do servidor: quem pode escrever nela, ou em `data\models` (lido com `joblib.load`), executa código como SYSTEM. O token de leitura vai embutido no APK e pode ser extraído, mas só dá acesso de leitura e pode ser trocado no `.env`. A página pública, sem token, mostra apenas o estado do ar de cada nó (ADR 0006).

Essas limitações não afetam os resultados científicos; são limites de robustez e de segurança do sistema. Se o servidor parar, os nós guardam cinco dias de leituras e o aplicativo avisa com 15 minutos ou mais de atraso.

Como mitigação, há backup diário com verificação de integridade, em um disco separado do disco do banco; a API fica presa ao loopback, atrás de um túnel gerenciado (ADR 0003); os tokens são separados por papel; as rotas de leitura abrem o banco em modo somente leitura; e o banco congelado tem cópia em dois discos. O endurecimento das tarefas agendadas (conta de baixo privilégio e ACLs) é trabalho futuro.

## 5. Lacunas que ainda dependem de resultado

- **Concordância entre os dois nós.** Os nós estão lado a lado desde 11/11/2026, às 14:18 em Brasília; falta um período de sobreposição estável, de uma a duas semanas, e a análise com o `compare_nodes`. [PENDENTE: horas pareadas, viés, MAE, RMSE, r, R², reta de regressão e limites de concordância de Bland-Altman do período de sobreposição congelado, com e sem as horas suspeitas.]
- **Rodada final da avaliação dos modelos.** Depende do banco congelado de pelo menos 35 dias, que ainda não existe. [PENDENTE: RMSE, MAE e skill score de cada previsor nas trilhas fixa e ajustada, na validação (por dobra) e no teste final, com a média e o desvio das 5 sementes da MLP.]
- **Validação prospectiva das versões finais.** Depende de treinar e instalar as versões novas dos três modelos depois da rodada final. [PENDENTE: horas avaliáveis, RMSE e skill score prospectivos de cada versão, incluindo o `ridge v1`, em produção desde 09/11/2026.]
- **Causa das horas suspeitas.** A conferência hora a hora contra a CETESB sugere falha intermitente do sensor, sem prova. [PENDENTE: comparação das horas suspeitas de um nó com as leituras do outro no período lado a lado.]
- **Causa dos reinícios do `no-01`.** [PENDENTE: motivo de reset informado pelo firmware, depois de os nós serem regravados com a versão que o envia, e a contagem por motivo.]
- **Local da estação e convenção de hora.** [PENDENTE: coordenadas oficiais da estação Osasco, para substituir a distância estimada de 4,4 km, e confirmação pela CETESB da convenção de hora do QUALAR.]
- **Umidade medida.** [PENDENTE: posição do BME280 e o que a umidade medida representa (ar ambiente, ar sob a cobertura ou interior da caixa).]
