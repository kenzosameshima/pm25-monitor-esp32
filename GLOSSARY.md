# Monitoramento de PM2,5

Rede de nós sensores de baixo custo que medem material particulado fino em pontos urbanos, guardam as leituras de forma confiável e as comparam com a estação de referência da CETESB, para análise (TCC) e consulta no celular.

## Language

### Coleta

**Nó**:
A unidade de coleta instalada num ponto, com um microcontrolador e seus sensores, que envia leituras ao servidor.
_Avoid_: dispositivo, device, node, estação (a estação é da CETESB)

**Sensor**:
Um componente de medição de um nó, como o PMS5003 (particulado) e o BME280 (temperatura, umidade e pressão).
_Avoid_: nó (um nó tem sensores; não é um sensor)

**Nó de teste**:
Nó usado só para verificar a instalação ou a conexão, cujo identificador começa com "teste". Não aparece no painel, no app, nas métricas do período nem nas previsões.
_Avoid_: nó de desenvolvimento, nó falso

**Leitura**:
A média de um minuto de relógio das medições de um nó, com horário em UTC.
_Avoid_: medição, amostra, registro

**Inicialização**:
O período entre duas partidas do nó. Cada leitura pertence a uma inicialização, e uma inicialização nova é um reinício.
_Avoid_: boot, sessão

**Lote**:
O conjunto de leituras que um nó envia numa única remessa ao servidor.
_Avoid_: pacote, batch

**Versão do firmware**:
O texto que identifica a compilação gravada num nó, informado por ele em cada lote. Nó com um firmware anterior ao campo não tem versão.
_Avoid_: build, release

**Leitura marcada**:
Leitura que o servidor considerou implausível. Fica guardada, mas não entra nas médias horárias por padrão.
_Avoid_: leitura suspeita, leitura ruim, flagged

**Leitura zerada**:
Leitura em que PM1, PM2,5 e PM10 chegam todos em 0,0 µg/m³. Sozinha, não diz se o sensor parou de ver partículas ou se o ar está muito limpo.
_Avoid_: leitura suspeita (suspeita é a hora), leitura inválida

### Qualidade da coleta

**Estado do nó**:
Situação do nó pelo tempo desde o último envio ao servidor: em operação, atrasado ou sem dados.
_Avoid_: online/offline, ativo/inativo

**Saúde da coleta**:
O conjunto de indicadores de uma janela de tempo de um nó: completude, maior lacuna, mensagens perdidas, reinícios, duplicatas descartadas e leituras marcadas.
_Avoid_: qualidade da coleta (qualidade é da leitura)

**Completude**:
A fração dos minutos esperados que têm leitura.
_Avoid_: cobertura, disponibilidade

**Lacuna**:
Uma sequência de minutos sem leitura. A maior lacuna da janela é um indicador da saúde da coleta.
_Avoid_: buraco, falha

**Mensagem perdida**:
Salto na sequência das leituras dentro de uma mesma inicialização. Minutos sem leitura e sem salto de sequência indicam falha do sensor, não da rede.
_Avoid_: pacote perdido, leitura perdida

**Duplicata descartada**:
Leitura reenviada por um nó e ignorada pelo servidor por já estar guardada.
_Avoid_: repetição, leitura duplicada

### Análise e previsão

**Hora válida**:
Hora com leituras em pelo menos 75% dos minutos e que não é suspeita, a única que tem média horária.
_Avoid_: hora boa, hora completa

**Hora suspeita**:
Hora com leituras suficientes em que o sensor quase não viu partículas: pelo menos um quarto das leituras abaixo de 0,5 µg/m³ de PM2,5, ou média abaixo de 1,0 µg/m³. Fica sem média e é contada à parte.
_Avoid_: hora zerada, hora inválida (inválida é a de poucas leituras)

**Hora sem média**:
Hora que não é válida, por uma de três causas: nenhuma leitura, poucas leituras (menos de 75% dos minutos) ou suspeita. É a que fica em branco nos gráficos, e o dashboard diz a causa de cada uma.
_Avoid_: hora perdida, hora ruim

**Média horária**:
A média das leituras de uma hora válida de um nó, hora cheia em UTC.
_Avoid_: média da hora, média por hora

**Hora encerrada**:
Hora cheia que já terminou. A previsão usa as médias até a última hora encerrada para prever a hora em andamento.
_Avoid_: hora completa (confunde com hora válida)

**Persistência**:
Previsor de referência que repete a média da hora anterior. É o que qualquer modelo precisa superar.
_Avoid_: baseline, ingênuo

**Modelo**:
Um previsor treinado, de um tipo (ridge, gradient boosting ou MLP) e de uma versão que nunca muda depois de gravada.
_Avoid_: algoritmo, forecaster

**Previsor**:
Quem produz a previsão que se compara com o observado: a persistência ou um modelo numa versão.
_Avoid_: predictor

**Previsão**:
O PM2,5 médio previsto para a hora seguinte de um nó por um modelo, gravado antes de a hora terminar.
_Avoid_: predição, forecast

**Previsão retroativa**:
Previsão de uma hora-alvo recalculada depois do fato, só com as leituras anteriores a ela. Fica numa versão à parte e não vale como validação prospectiva.
_Avoid_: previsão atrasada, backfill

**Skill score**:
Um menos a razão entre o RMSE do previsor e o da persistência, calculados sobre as mesmas horas. Acima de zero, o previsor supera a persistência.
_Avoid_: ganho, melhoria

**Banco congelado**:
Cópia íntegra do banco, com hash, tirada ao fim da coleta, da qual saem as métricas do período, a avaliação dos modelos e a comparação com a CETESB.
_Avoid_: snapshot, backup (o backup é a cópia diária de segurança)

### Referência e acesso

**Estação de referência**:
A estação da CETESB cujas médias horárias de PM2,5 servem de padrão para comparar os nós.
_Avoid_: nó de referência

**Faixa de qualidade do ar**:
Uma das cinco faixas da CETESB para o PM2,5 (Boa, Moderada, Ruim, Muito ruim, Péssima). A CETESB as define para a média de 24 horas; aplicadas a uma leitura ou a uma média horária, servem só de referência visual.
_Avoid_: nível, índice de qualidade

**Token do nó**:
Segredo que identifica um nó ao enviar leituras. Cada nó tem o seu.
_Avoid_: chave do dispositivo

**Token de leitura**:
Segredo do app de consulta, que só lê. É sempre diferente dos tokens dos nós.
_Avoid_: token do app, chave de leitura
