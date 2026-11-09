# Roteiro de fala da apresentação do TCC

Transcrição para ler e ensaiar em voz alta. Tempo estimado: 20 a 25 minutos de fala, seguidos da arguição. O que está em *itálico entre colchetes* é indicação de slide ou de tela, não é para falar. Os números vêm do banco congelado de 09/10 a 08/11/2026 (SHA-256 `2d6dfd45…3e87`) e de `docs/limitacoes-do-tcc.md`. Se rodar alguma análise de novo, confira os números antes de falar.

Regra de ouro da apresentação: **falar primeiro as limitações que a banca descobriria sozinha**. Neste trabalho a honestidade é o ponto forte; os resultados são preliminares e o texto diz isso desde o começo.

---

## Parte 1. Abertura e problema (≈ 2 min)

*[Slide: título, nome, orientador, UNIP, 2026]*

Bom dia a todos, e obrigado à banca por estar aqui. Eu vou apresentar um sistema de monitoramento de material particulado fino, o PM2,5, feito com sensores de baixo custo, e uma avaliação de quão bem dá para prever a média da hora seguinte.

*[Slide: PM2,5 e por que importa]*

O PM2,5 são partículas menores que 2,5 micrômetros. Elas entram fundo no pulmão e estão associadas a problemas respiratórios e cardiovasculares. As estações oficiais, como as da CETESB, medem muito bem, mas são poucas e caras. Sensores de baixo custo permitem medir em mais pontos, mas ninguém garante que os dados deles são confiáveis, nem que a coleta funciona por semanas sem perder leitura.

*[Slide: pergunta do trabalho]*

Então o trabalho responde a três perguntas, nesta ordem:

1. Dá para montar uma cadeia de coleta que **não perca dado** durante semanas, mesmo com queda de rede, de energia e de servidor?
2. Quanto os dados desse sensor **concordam com a estação de referência** da CETESB?
3. Dá para **prever a média horária da hora seguinte melhor que a persistência**, que é simplesmente repetir o último valor?

Já adianto: a terceira resposta é "não de forma clara, com a amostra que eu tenho", e eu vou mostrar por quê.

---

## Parte 2. O sistema (≈ 6 min)

*[Slide: diagrama de arquitetura. Nó ESP32 → HTTPS via túnel → API FastAPI → SQLite → dashboard, app Android, job de previsão, scripts de análise]*

O sistema tem quatro partes: o nó sensor, o servidor, o painel e o app Android.

### 2.1 O nó sensor

O nó é um ESP32 com um sensor de partículas PMS5003 e um BME280, que mede temperatura, umidade e pressão. Ele fecha **uma leitura por minuto de relógio** e envia em lotes, em JSON, para a API.

Três decisões deixam o nó robusto:

- **Buffer em flash de cinco dias.** Se a API não confirma o lote, o nó guarda e reenvia com espera crescente.
- **Watchdog e reinício.** Se o nó trava, ele reinicia sozinho; sem Wi-Fi por 15 minutos, também reinicia.
- **Só envia depois do NTP.** Sem hora válida não existe certificado TLS válido nem minuto confiável. Todos os horários são em UTC.

### 2.2 Identidade da leitura e idempotência

*[Slide: `(device_id, boot_id, seq)`]*

Essa é a decisão central do sistema distribuído. Cada leitura tem uma identidade: o nó, um contador de boot guardado na memória não volátil e um número de sequência que recomeça a cada boot.

Com isso, **reenviar um lote é sempre seguro**: a API descarta duplicata. É entrega "pelo menos uma vez" com efeito de "exatamente uma vez". E a identidade ainda separa os tipos de falha: salto de `seq` no mesmo boot é **mensagem perdida**; `boot_id` novo é **reinício**; tempo sem leitura e sem salto de `seq` é **falha do sensor**.

### 2.3 Servidor e banco

A API é em FastAPI. Ela autentica o nó por token, valida o contrato e só responde 201 **depois** de a leitura estar no disco. O banco é um único SQLite em modo WAL com `synchronous=FULL`. A tabela de medidas, `measurements`, é **imutável**: gatilhos bloqueiam UPDATE e DELETE. A leitura bruta nunca é alterada; limpeza e agregação ficam em tabelas e rotinas derivadas.

### 2.4 Segurança e publicação

*[Slide: API no loopback + túnel]*

A API escuta só em `127.0.0.1`. Quem a publica é um túnel gerenciado, o Tailscale Funnel, com certificado público. Não tem porta aberta no roteador, IP fixo, domínio ou autoridade certificadora própria. O túnel expõe só três caminhos: `/v1/measurements`, `/v1/devices` e `/health`. Há ainda tokens separados por papel (o nó não lê, o app não grava), bloqueio de IP após falhas de autenticação e limite de tamanho de corpo.

### 2.5 App Android e painel

*[Slide: telas do app: início, detalhe, previsão, alerta]*

O app, em Kotlin com Jetpack Compose, lê pelas rotas `GET /v1/devices`. Ele mostra o PM2,5 atual com a cor da faixa da CETESB, o histórico de 24 horas ou 7 dias, a saúde da coleta e a previsão contra o observado. Tem cache em arquivo para funcionar sem rede, e alertas em segundo plano: nó sem dados, ar Ruim, servidor sem resposta.

Um detalhe que eu considero importante para sistemas distribuídos: **o app não confia no relógio do celular**. Toda resposta traz o `generated_at` do servidor, e o app calcula a idade do dado só com diferenças entre dois instantes do próprio celular.

O painel em Streamlit é local, só leitura, e usa as mesmas regras de análise do app e dos scripts, centralizadas num módulo único. Por isso o número é o mesmo em qualquer lugar.

### 2.6 Previsão em produção

Um job roda a cada hora, aos cinco minutos, e grava as previsões direto na tabela `forecasts` do SQLite. Essa foi uma decisão registrada como ADR: uma rota POST manteria um escritor só, mas custaria mais código, outro token e mais superfície exposta. O job só escreve numa tabela que a API não usa, e a previsão é idempotente por nó, hora-alvo, modelo e versão.

---

## Parte 3. Qualidade dos dados (≈ 4 min)

*[Slide: o que foi coletado]*

O nó `no-01` está instalado em Osasco desde 09/10/2026, no apoio externo de uma janela, coberto, a 1,1 m do chão. O banco foi **congelado** com 31 dias, de 09/10 a 08/11, com cópia em dois discos e hash registrado. A partir daí toda análise roda sobre o mesmo arquivo, e qualquer pessoa pode conferir.

### 3.1 Resultado da coleta

- **Completude de 97,2%**: 43.390 de 44.640 minutos esperados.
- **651 horas válidas** de 744. Hora válida exige pelo menos 45 leituras boas.
- **Nenhuma mensagem perdida.** O buffer e o reenvio funcionaram, inclusive numa queda do túnel em que o nó guardou leituras por horas e enviou 291 de uma vez.
- **32 reinícios em 31 dias**, cerca de um por dia. 23 deles custaram no máximo 2 minutos. Eu **não sei a causa**: o firmware não informa o motivo do reset. Isso está registrado como limitação.

### 3.2 Horas suspeitas

*[Slide: gráfico com episódio de zeros]*

Aqui está o achado mais delicado. Em episódios, o sensor leu **0,0 em PM1, PM2,5 e PM10 por horas, enquanto respondia**. Defini como hora suspeita aquela com pelo menos 25% das leituras abaixo de 0,5 µg/m³ ou média abaixo de 1,0. Foram **70 horas de 744** (9,4%).

A decisão importante: essas horas **saem da análise, não do banco**. O banco continua intacto e a regra pode ser revista. A regra é a mesma no painel, na API, no treino, no job e nas métricas.

Eu não afirmo que o sensor falhou. Conferi hora a hora contra a CETESB: nessas horas o nó marca em média 0,69 enquanto a estação marca de 5 a 27 em um terço das vezes. Isso não é compatível só com ar limpo, então a explicação mais provável é **falha intermitente do sensor**, mas não está provada. Por isso eu relato **os dois resultados**, com e sem essas horas.

### 3.3 Uma correção de método

Um exemplo de cuidado com número: o painel e o script de métricas calculavam a completude de jeitos diferentes, dando 98,19% e 97,53% para o mesmo período. Eu unifiquei a conta com janela fixa, em que os minutos antes da primeira leitura também contam como esperados. Fiquei com o número **menor**, que é o mais difícil de a banca questionar. Está registrado no ADR 0005.

---

## Parte 4. Comparação com a CETESB (≈ 3 min)

*[Slide: tabela e dispersão nó × estação]*

A referência é a estação Osasco da CETESB, com as médias horárias do QUALAR. O nó fica a cerca de **4,4 km** dela, uma estimativa, porque o endereço da estação não está bem documentado.

Com **641 horas pareadas**:

| Métrica | Valor |
|---|---|
| Média do nó | 21,2 µg/m³ |
| Média da CETESB | 12,9 µg/m³ |
| Viés | **+8,3 µg/m³** |
| MAE | 12,0 |
| RMSE | 16,0 |
| Correlação de Pearson | **0,43** (R² de 0,18) |

Incluindo as horas suspeitas, são 711 horas, viés de +6,8 e r de 0,45.

O que eu concluo: **o nó lê mais alto que a referência e acompanha pouco a variação horária dela**. O r baixo mistura vários fatores que eu **não consigo separar**: erro do sensor, distância de 4,4 km, microambiente (fachada, cobertura, altura) e a resolução em números inteiros da estação. O PMS5003 não foi calibrado. **Esta comparação não valida o sensor como instrumento de referência**, e eu não estou dizendo isso.

Uma observação sobre umidade: acima de 75% o PMS5003 tende a superestimar. Só 16 das 641 horas passaram desse limite, com viés de +21,4 contra +8,0 nas demais. Isso sugere o efeito, mas a amostra não permite concluir nem corrigir.

---

## Parte 5. Previsão (≈ 5 min)

*[Slide: pergunta e protocolo]*

Agora a parte de previsão. A pergunta é: dá para prever a média horária da **hora seguinte** melhor que a persistência?

### 5.1 Como eu evitei me enganar

Eu **registrei o protocolo de avaliação antes da rodada final** (`docs/protocolo-de-avaliacao.md`), com commit. Ele define quais modelos, quais métricas e o que não será feito: não alterar a grade ou a regra de relato depois de ver os números, não escolher modelo pelo teste final e não relatar só os que ficaram bem.

- **Modelos:** persistência (referência), Ridge, gradient boosting e uma MLP.
- **Validação progressiva**, respeitando o tempo: nunca se treina com o futuro.
- **Teste final** em 7 dias separados, avaliado uma vez.
- **Skill score** sobre a persistência, calculado nas **mesmas horas**. Comparar RMSE de horas diferentes distorce o resultado.
- **Hiperparâmetros fixos**, definidos antes de ver os dados. A MLP é relatada pela média de 5 sementes, nunca pela melhor.

### 5.2 Resultado no teste final (149 horas, só o `no-01`)

*[Slide: tabela]*

| Previsor | RMSE (µg/m³) | Skill vs. persistência |
|---|---|---|
| Persistência | 7,08 | 0 |
| Ridge | 6,50 | **+0,082** |
| MLP (5 sementes) | 6,90 ± 0,15 | +0,025 ± 0,021 |
| Gradient boosting | 7,47 | −0,055 |

Minha leitura: **nenhum modelo supera a persistência de forma clara**. O Ridge fica um pouco acima, mas com uma dobra de validação e 149 horas de teste a diferença não é sólida. A MLP é estatisticamente igual à persistência e o gradient boosting fica pior. Pelo protocolo, uma diferença só é "ganho" se for maior que o desvio entre sementes e mantiver o sinal em todas as dobras, e isso não aconteceu.

Esse resultado é válido. A pergunta do trabalho nunca foi "qual modelo ganha", foi "a previsão supera a persistência?", e a resposta honesta é: **ainda não dá para afirmar**.

### 5.3 Validação prospectiva

O `ridge v0` provisório, treinado em 17/10 com cerca de 8 dias de dados, rodou **em tempo real**. Em 304 horas avaliáveis, ficou **pior** que a persistência: RMSE de 8,83 contra 8,42, skill de −0,049, com intervalo de −0,094 a −0,015 por bootstrap em blocos diários. Eu relato isso mesmo sendo desfavorável. Ele é um modelo provisório e não representa os modelos da avaliação offline.

As previsões que recalculei depois de uma queda do túnel ficam em versão separada, `v0-retro`, e **não entram** na validação prospectiva, porque não foram gravadas antes do fato.

Em 09/11 entrou em produção o `ridge v1`, treinado só com o `no-01`, para acumular validação prospectiva.

---

## Parte 6. Limitações e trabalhos futuros (≈ 3 min)

*[Slide: limitações]*

Eu quero nomear as limitações em voz alta:

1. **Amostra curta.** 31 dias, abaixo das cerca de 5 semanas que eu mesmo recomendo. Os resultados são preliminares e não generalizam para outras estações do ano ou episódios de poluição que o mês não cobriu.
2. **Um nó confiável.** O segundo nó, o `no-02`, mede na zona sul da capital, a mais de 15 km, e teve só 18,6% de completude. Não existe medida de concordância entre dois sensores no mesmo ar.
3. **Horas suspeitas.** A causa não está decidida e a escolha de retirá-las afeta os resultados; por isso os dois relatos.
4. **Uma dobra de validação**, sem busca de hiperparâmetros. A grade já está registrada em `docs/grade-hiperparametros.json`, mas ainda não foi rodada com dados reais.
5. **Servidor único.** Se cair, os nós guardam cinco dias e o app avisa com 15 minutos ou mais de atraso. As tarefas do Windows rodam como SYSTEM sem restringir as permissões da pasta, um risco de implantação conhecido, ainda sem mitigação.
6. **Reinícios sem causa conhecida** e **comparação com a CETESB** que não separa as fontes de diferença.

*[Slide: próximos passos]*

Como trabalho futuro: levar o `no-02` para junto do `no-01` por uma ou duas semanas e medir a concordância; rodar a busca de hiperparâmetros só na validação, mantendo o teste intocado; registrar o motivo de reset no firmware; obter as coordenadas oficiais da estação e confirmar a convenção de hora do QUALAR; e acompanhar a validação prospectiva dos modelos novos.

---

## Parte 7. Fechamento (≈ 1 min)

*[Slide: conclusões]*

Para fechar, três conclusões:

1. **A cadeia de coleta funciona.** 97,2% de completude, nenhuma mensagem perdida, em 31 dias, com reinícios e quedas de túnel pelo caminho.
2. **O sensor lê mais alto que a estação e a acompanha pouco** (viés de +8,3, r de 0,43), por razões que este trabalho não consegue separar.
3. **Nenhum modelo superou a persistência de forma clara** nesta amostra, e o trabalho foi desenhado para que esse resultado fosse possível e aceitável.

O sistema todo, com testes, decisões documentadas e o protocolo de avaliação, está no repositório. Obrigado, e fico à disposição da banca.

---

# Banco de perguntas da banca, com respostas prontas

Respostas curtas, para falar em 30 a 60 segundos. Onde não há resposta boa, o roteiro diz isso: admitir é melhor que inventar.

## Sobre o sensor e os dados

**1. Por que usar o PMS5003? Ele é confiável?**
É um sensor de baixo custo, baseado em espalhamento de luz, muito usado e bem documentado, por isso foi escolhido. Ele **não é um instrumento de referência**: superestima com umidade alta e não foi calibrado aqui. O trabalho trata ele como sensor a ser avaliado, não como verdade.

**2. As horas suspeitas não são um defeito do sensor? Por que não descartou o nó?**
Pode ser, e a evidência aponta nessa direção: nelas a estação marca de 5 a 27 enquanto o nó marca zero. Mas não está provado, e descartar tudo jogaria fora 651 horas boas. Por isso retiro só as horas suspeitas da análise, mantenho o banco intacto e relato os resultados **com e sem** elas.

**3. Não é manipular os dados remover 70 horas?**
A regra foi definida por critério objetivo (25% das leituras abaixo de 0,5 ou média abaixo de 1,0), vale igual em todo o sistema, e o banco não é alterado. Os números com as horas incluídas também estão relatados (r de 0,45, viés de +6,8). E há a ressalva no ADR: se a CETESB mostrasse ar tão limpo quanto o nó nessas horas, a regra deveria ser descartada.

**4. Por que a correlação com a CETESB é tão baixa (0,43)?**
Porque mistura causas que eu não separo: erro do sensor, 4,4 km de distância, microambiente (fachada, coberto, 1,1 m do chão) e a estação reportar números inteiros. Eu **não** afirmo que o sensor é ruim nem que é bom; afirmo que a comparação não o valida.

**5. Fez calibração ou correção por umidade?**
Não. Só 16 horas passaram de 75% de umidade, pouco para ajustar qualquer correção. Fica como trabalho futuro, depois de verificar o que o BME280 está medindo, já que ele pode estar sob a cobertura ou dentro da caixa.

**6. A distância de 4,4 km é exata?**
Não, é uma estimativa pelo OpenStreetMap, com incerteza de poucas centenas de metros, porque o endereço da estação não está bem documentado. Um segundo endereço candidato foi descartado; com ele seriam cerca de 2,5 km. Pendência declarada.

**7. Por que o rótulo de hora do QUALAR foi tratado como fim da hora?**
Segui a documentação do pacote qualR. Testei a outra convenção: com o rótulo como início, o r cai para 0,39 e o RMSE sobe para 16,4. A convenção precisa ser confirmada com a CETESB, e isso consta como pendência.

**8. Por que só 31 dias?**
O nó entrou em operação em 09/10 e o prazo do TCC fechou o banco em 08/11. O README recomenda cerca de 5 semanas para avaliar modelos; por isso os resultados são preliminares, e eu digo isso no texto.

**9. E o segundo nó?**
Entrou em 21/10 e mede na zona sul, a mais de 15 km do `no-01`. Teve 18,6% de completude e 37 reinícios, então não serve para concordância entre sensores. Entra só como análise de sensibilidade. A concordância exige colocá-lo junto do `no-01`, e isso fica como trabalho futuro.

**10. Por que o nó reinicia 32 vezes em 31 dias?**
Não sei a causa. A maioria deixou no máximo 2 minutos sem leitura, o que aponta para reinício por software (watchdog ou rotina) e não para falta de energia, e nenhuma leitura se perdeu. O firmware não registra o motivo do reset; registrar isso é o próximo passo para investigar.

## Sobre o sistema distribuído

**11. O que torna isto um sistema distribuído?**
Há nós autônomos (ESP32), servidor, clientes móveis, rede não confiável, relógios diferentes e falhas parciais. Os problemas clássicos aparecem de verdade: entrega pelo menos uma vez com idempotência, tolerância a queda de rede e servidor, sincronização de relógio, detecção de falha por alertas e concorrência no banco.

**12. Como garante que não perde nem duplica leitura?**
Pela identidade `(device_id, boot_id, seq)`. O nó só apaga o lote do buffer depois do 201, que só sai depois de gravar no disco; se reenviar, a API descarta a duplicata. Foram 0 mensagens perdidas no período, e 53 duplicatas descartadas.

**13. E se o servidor cair?**
É um ponto único de falha, e eu assumo isso. O nó guarda 5 dias de leituras em flash e reenvia depois; foi o que aconteceu na queda do túnel, com 291 leituras enviadas de uma vez e nenhuma perdida. Os alertas do app avisam, com atraso de 15 minutos ou mais.

**14. Por que SQLite e não PostgreSQL?**
Um nó coletando uma leitura por minuto gera pouquíssima escrita. SQLite em WAL com `synchronous=FULL` dá durabilidade e leitores concorrentes com um arquivo só, mais simples de fazer backup e de congelar com hash. Um servidor de banco só se justificaria com muitos nós.

**15. Por que o job de previsão escreve direto no banco e não pela API?**
Foi a decisão do ADR 0001. A rota POST manteria um escritor só, mas custaria mais código, outro token e mais superfície exposta. O job só escreve na tabela `forecasts`, numa transação curta por hora, e o WAL serializa as gravações.

**16. É seguro expor isso na internet?**
A API escuta só em loopback; o túnel publica só três caminhos, com certificado público e HTTPS. Há tokens por papel, bloqueio de IP e limite de corpo. Fragilidades que eu conheço: o token de leitura vai embutido no APK e pode ser extraído (só dá leitura e pode ser trocado), e as tarefas do Windows rodam como SYSTEM sem restringir permissões da pasta, mitigação pendente.

**17. Por que o app não usa o relógio do celular?**
Porque ele pode estar errado. A resposta traz o `generated_at` do servidor, e o app só usa a diferença entre dois instantes do próprio celular para envelhecer o dado. Assim, um relógio errado não distorce a idade.

**18. O app foi testado em celular real?**
Sim, em 18/10/2026, num Galaxy S23 Ultra com Android 16, pelo túnel, com dados reais de produção e um alerta real de PM2,5 Ruim (60 µg/m³). **Não foi medido** o atraso dos alertas ao longo de horas com a economia de bateria da Samsung, e falta o build de release assinado.

## Sobre a previsão

**19. Por que comparar com a persistência?**
Porque é a linha de base mais difícil de vencer em curto prazo: a poluição muda devagar de uma hora para outra. Um modelo que não bate a persistência não está entregando informação nova.

**20. Seu resultado não é um fracasso?**
Não. É um resultado válido, registrado em protocolo antes da rodada final. Com 31 dias e uma dobra, o Ridge fica a +0,082, mas sem solidez. O que o trabalho mostra é o que se consegue dizer com essa amostra, e que a pergunta ainda não pode ser respondida com "sim".

**21. Por que não escolheu o melhor modelo e usou no sistema?**
Porque escolher pelo desempenho no teste final seria justamente o erro que o protocolo proíbe. O trabalho compara os previsores e não elege um "modelo do TCC". Para ter um recomendado, a regra registrada é: Ridge, a menos que outro tenha RMSE de validação pelo menos 5% menor e melhor em todas as dobras.

**22. Por que não fez busca de hiperparâmetros?**
Os hiperparâmetros foram fixados antes de ver os dados, de propósito, e a rodada oficial usa eles. Preparei a trilha ajustada (`--tune`), com grade registrada, escolhida só na validação, com o teste final intocado, como análise de sensibilidade. Ainda não foi rodada com dados reais. Se a banca pedir, é uma rodada pequena.

**23. Por que a MLP e o gradient boosting foram pior?**
Com 494 horas, modelos flexíveis tendem a perder para o Ridge e para a persistência, e sem ajuste de hiperparâmetros podem perder só por estarem mal calibrados. Não consigo separar essas duas causas com esta amostra.

**24. Seu `ridge v0` foi pior que a persistência. Por quê?**
Foi treinado em 17/10 com cerca de 8 dias de dados e nunca retreinado, então é um modelo provisório com pouco histórico. Ele não representa os modelos da avaliação offline, e um resultado não se transfere para o outro. Eu relato os dois, e o `v1`, treinado com 494 horas, começa a validação prospectiva a partir de 09/11.

**25. Houve vazamento de dados do futuro?**
A validação é progressiva, só treina com dados anteriores, e o job usa só leituras anteriores à hora-alvo. As previsões retroativas, calculadas depois de uma queda, ficam em versão separada (`v0-retro`) justamente para não se misturarem com as prospectivas.

**26. Por que o skill score é calculado nas mesmas horas?**
Comparar RMSEs de conjuntos diferentes de horas distorce o resultado, porque o modelo e a persistência exigem condições diferentes para existir. A mesma função é usada no painel e na avaliação offline.

**27. O intervalo de confiança do bootstrap é confiável?**
É aproximado: o bootstrap é em blocos diários, mas dias seguidos são correlacionados. Eu digo isso no texto.

## Perguntas difíceis e honestas

**28. O que você mudaria se começasse de novo?**
Começaria a coleta mais cedo, para ter mais semanas; colocaria os dois nós juntos desde o início; registraria o motivo do reset no firmware; e verificaria a posição do BME280. Todos são limites que eu já identifiquei, não surpresas.

**29. Qual a principal contribuição do trabalho?**
Uma cadeia de coleta que funciona e é verificável (banco congelado com hash, regras únicas em todo o sistema) e uma avaliação de previsão desenhada para não se enganar, com protocolo registrado antes e resultados desfavoráveis relatados. Não é um modelo que vence a persistência.

**30. Os resultados valem para outro lugar?**
Não. É um nó em Osasco por 31 dias. Não se generaliza para outros locais, estações do ano nem episódios de poluição que o mês não cobriu.

**31. Qual a pendência mais séria?**
A amostra curta, porque ela limita todas as conclusões, em especial a de previsão. Em segundo lugar, a causa das horas suspeitas, porque a escolha de retirá-las afeta as médias e a comparação.

**32. Isso serve para decisão de saúde pública?**
Não. Os dados do nó são sem calibração e a comparação com a estação não os valida. O sistema é um protótipo de coleta e avaliação, e o app mostra alertas como informação, não como orientação de saúde.

---

# Cola rápida de números (para consultar antes de entrar)

| Item | Valor |
|---|---|
| Período congelado | 09/10 a 08/11/2026, 31 dias |
| Completude `no-01` | 97,2% (43.390 de 44.640 minutos) |
| Horas válidas | 651 de 744 |
| Horas suspeitas | 70 (9,4%); mais 23 sem média por falta de leituras |
| Reinícios do `no-01` | 32 em 31 dias; 0 mensagens perdidas |
| Distância até a CETESB | ≈ 4,4 km (estimada) |
| Pareadas com a CETESB | 641 horas (711 com as suspeitas) |
| Viés / MAE / RMSE / r | +8,3 / 12,0 / 16,0 / 0,43 (com suspeitas: +6,8 e 0,45) |
| Teste final | 149 horas |
| RMSE no teste | persistência 7,08; Ridge 6,50; MLP 6,90 ± 0,15; boosting 7,47 |
| Skill no teste | Ridge +0,082; MLP +0,025 ± 0,021; boosting −0,055 |
| `ridge v0` prospectivo | 304 horas; RMSE 8,83 contra 8,42; skill −0,049 (−0,094 a −0,015) |
| `no-02` | 18,6% de completude, 37 reinícios, 76 horas válidas |
| Alerta real no celular | 59,5 µg/m³ (mostrado como 60), 18/10/2026 |
