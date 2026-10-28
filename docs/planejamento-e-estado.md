# Sistema de monitoramento de PM2,5: planejamento e estado atual

Situação em 26/10/2026, com o job horário de previsão e os alertas do app integrados à `main` e as correções da revisão de segurança aplicadas (resta o risco da implantação no Windows, ver seção 7). O [README](../README.md) é a referência de uso e de detalhes de cada parte; este documento reúne o plano, as decisões e o que está pronto, verificado ou pendente.

## 1. Objetivo e escopo

O sistema mede material particulado fino (PM2,5) com sensores de baixo custo em pontos urbanos, guarda as leituras de forma confiável e as disponibiliza para análise e consulta. Ele serve a dois trabalhos que compartilham o mesmo código:

- **TCC:** cadeia de coleta, qualidade dos dados, comparação com a estação de referência da CETESB e modelos de previsão da média horária de PM2,5 da hora seguinte.
- **Atividade semestral (aplicação de sistema distribuído para dispositivo móvel):** o app Android de consulta e as rotas de leitura da API, que transformam a cadeia de coleta num sistema distribuído com cliente móvel.

Um único tema ambiental basta para a atividade; o recorte é a poluição do ar.

## 2. Arquitetura

```
 nó sensor (ESP32)                     servidor (Windows ou Linux)                         clientes
 ┌─────────────────────┐   HTTPS POST  ┌──────────────────────────────────────────┐
 │ PMS5003 + BME280     │──────────────▶│ API FastAPI (127.0.0.1:8000)             │
 │ média de 1 min       │  via túnel    │  ingestão  POST /v1/measurements         │
 │ buffer em flash 5 d  │  (Funnel)     │  leitura   GET  /v1/devices...    ◀──────┼──── app Android
 │ NTP, watchdog        │               │  /health                                 │      (HTTPS pelo túnel,
 └─────────────────────┘               │        │                                 │       ou HTTP local em debug)
                                       │        ▼                                 │
                                       │ SQLite (WAL, measurements imutável)      │
                                       │   ├─▶ backup diário (pendrive/nuvem)     │
                                       │   ├─▶ job de previsão (HH:05, forecasts) │
                                       │   ├─▶ dashboard Streamlit (só local) ◀───┼──── navegador no servidor
                                       │   └─▶ scripts de análise (offline)       │
                                       │        train_forecast, period_metrics,   │
                                       │        compare_cetesb, fit_forecast      │
                                       └──────────────────────────────────────────┘
```

Fluxos:

1. **Coleta:** o nó fecha uma leitura por minuto de relógio e envia lotes em JSON (contrato v1). O que a API não confirma fica num buffer em LittleFS e é reenviado com espera crescente.
2. **Ingestão:** a API autentica o nó pelo token, valida o contrato, grava num único SQLite e só responde 201 depois de a leitura estar no disco.
3. **Análise:** o dashboard, os scripts e as rotas de leitura usam as mesmas regras, centralizadas em `server/app/analytics.py`.
4. **Consulta móvel:** o app lê só pelas rotas `GET /v1/devices…`, com um token de leitura separado dos tokens dos nós.

## 3. Decisões de projeto

O vocabulário do projeto está em [GLOSSARY.md](../GLOSSARY.md), e as decisões mais difíceis de reverter, com o que foi descartado, em [docs/adr](adr/).

| Decisão | Motivo |
|---|---|
| Identidade da leitura `(device_id, boot_id, seq)` e descarte de duplicatas | Reenviar um lote é sempre seguro (entrega pelo menos uma vez com efeito de exatamente uma vez), e os tipos de falha ficam separáveis: salto de `seq` é perda, `boot_id` novo é reinício, minuto sem salto é falha do sensor |
| Buffer de cinco dias em flash, reenvio com espera crescente, watchdog de 90 s, reinício após 15 min sem Wi-Fi | Tolerância a quedas de rede, de servidor e de energia sem perder dado |
| Envio só depois do NTP; horários em UTC | Sem hora válida não há certificado TLS válido nem minuto confiável |
| SQLite em WAL, `synchronous=FULL`, `measurements` imutável por gatilhos | Um arquivo, leitores concorrentes com as gravações serializadas, e a leitura bruta nunca é alterada; limpezas e agregações vão para tabelas e rotinas derivadas |
| Job de previsão grava direto no SQLite, só em `forecasts` | A API deixa de ser o único escritor, mas o job faz uma transação curta por hora numa tabela que a API não usa; o WAL serializa as gravações e a conexão espera até 10 s por uma trava. Uma rota `POST` na API manteria um escritor só, com mais código, outro token e mais superfície exposta |
| Dados e modelos de previsão num módulo só (`forecasting.py`) | A avaliação, o treino do modelo de produção e o job horário montam as variáveis com o mesmo código, então o modelo em produção vê o que viu no treino |
| Versão de modelo imutável (`<modelo>-<versão>.joblib`) | Cada linha de `forecasts` aponta para um único modelo; versões diferentes aparecem lado a lado no painel e no app |
| Túnel gerenciado (Tailscale Funnel) com certificado público, API presa ao loopback | Sem porta aberta, IP fixo, domínio ou CA própria; o túnel publica só `/v1/measurements`, `/v1/devices` e `/health` |
| Token de leitura separado dos tokens dos nós | Um nó não lê e o app não grava; a configuração recusa um token de leitura igual ao de um nó |
| Regras de análise num módulo só (`analytics.py`) | A hora válida (45 leituras), o estado do nó, a saúde da coleta e as métricas de previsão dão o mesmo número no painel, nos scripts e no app |
| Hora suspeita (sensor quase sem partículas) fica sem média na análise, não no banco | Em episódios, o `no-01` leu 0,0 em todos os canais por horas. A regra (25% das leituras abaixo de 0,5 µg/m³, ou média abaixo de 1,0) vale em `analytics.hourly_means`, então painel, API, treino, job e métricas usam as mesmas horas; o banco imutável e o congelado ficam intactos. Detalhes em `docs/adr/0004-…` |
| Skill score calculado sobre as mesmas horas da persistência | Comparar RMSEs de horas diferentes distorcia o resultado; o painel e a avaliação offline usam agora a mesma função |
| `generated_at` (relógio do servidor) em toda resposta de leitura | O app calcula a idade dos dados sem depender do relógio do celular |
| Cache de respostas em arquivo, com escrita atômica, no app | O app só precisa da última resposta de cada tela; Room traria SQLite, KSP e migrações sem ganho |
| Hora estimada do servidor no app (`generated_at` + tempo desde a chegada) | Um dado salvo envelhece corretamente e o estado do nó é recalculado com os limites que a própria resposta traz |
| Permissão de rede local pedida só para endereço local | O Android 17 bloqueia a rede local para apps com `targetSdk` 37; pela URL pública do túnel nada é pedido |

## 4. Conceitos de sistemas distribuídos no projeto

| Conceito | Onde aparece |
|---|---|
| Comunicação e contrato | REST com JSON, `schema_version` no contrato de ingestão, campos novos ignorados pelo app (`ignoreUnknownKeys`) |
| Tolerância a falhas | Buffer e reenvio no nó; no app, últimos dados mantidos na tela e cache em disco quando a rede ou a API caem |
| Semântica de entrega e idempotência | Pelo menos uma vez com descarte de duplicatas por `(device_id, boot_id, seq)`; duplicatas contadas em `ingest_batches` e mostradas no app |
| Relógios | NTP no nó; `generated_at` do servidor; idade e estado calculados no app com diferenças do relógio do celular, nunca com o valor absoluto dele |
| Detecção de falhas | Alertas do app (nó sem dados, servidor sem resposta); estado `online`/`late`/`silent`; saúde da coleta com lacunas, perdas e reinícios |
| Concorrência e consistência | WAL com dois escritores (a API e o job de previsão, que se revezam na trava) e vários leitores; previsões idempotentes por `UNIQUE (nó, hora-alvo, modelo, versão)`; o app troca histórico e saúde juntos, só quando as duas respostas chegam |
| Segurança | TLS com raiz embutida no nó, tokens por papel, bloqueio de IP após falhas, limite de corpo, HTTP só no debug para endereços locais |
| Limites | Servidor e banco únicos (ponto único de falha); se o próprio servidor cair, os alertas do app avisam com 15 minutos ou mais de atraso |

## 5. Estado por componente

Legenda: **pronto** (implementado, com testes ou verificação descrita), **parcial**, **pendente**.

| Componente | Estado | O que existe | Verificação | Falta |
|---|---|---|---|---|
| Firmware do nó (`firmware/`) | parcial | Leitura do PMS5003 e do BME280, média de 1 min, buffer de 5 dias, HTTPS com raiz embutida, watchdog | Compila sem avisos nos cores 2.0.17 e 3.3.12; parser, média e JSON testados no computador; o JSON gerado é aceito pela API | Nó `no-01` (PMS5003 + BME280) montado, fixado e em operação em Osasco desde 09/10/2026, enviando pelo túnel; 14 mil leituras de 09 a 19/10/2026, nenhuma marcada nem recusada; medir o pico de memória do handshake TLS; o firmware lê a pressão do BME280 e a envia, e o servidor a guarda, mas nenhuma análise, rota de leitura, painel ou o app a usa; o nó passa a informar a versão do firmware em cada lote assim que for regravado com esta versão, e o painel a mostra |
| Simulação no Wokwi (`wokwi/`) | pronto | Chips do PMS5003 e do BME280 corrigidos (campos e compensação) | Erro abaixo de 0,01 nas faixas testadas, quadros aceitos pelo parser | Execução completa do firmware no Wokwi não registrada |
| API de ingestão | pronto | Contrato v1, idempotência, auditoria de mensagens inválidas, limite de corpo, bloqueio de IP | Testes da API, inclusive com o JSON do firmware | — |
| API de leitura | pronto | `/v1/devices`, `/hourly` (`start`/`end` ou `hours`), `/health`, `/forecast`, token de leitura, banco somente leitura | Testes da API e teste de ponta a ponta com o simulador e `curl` | ETag/respostas condicionais (opcional) |
| Banco | pronto | Esquema com `measurements`, `ingest_batches`, `invalid_messages`, `forecasts` e `devices.location` | Testes | Coordenadas para mapa (exigiria migração) |
| Backup e dashboard | pronto | Backup diário com verificação de integridade; dashboard local de 3 abas | Dashboard testado com o AppTest do Streamlit; backup e cópia íntegra do banco com testes automáticos | — |
| Regras de análise (`analytics.py`) | pronto | Hora válida, estado, saúde da coleta, comparação de previsões, métricas | Testes próprios e comparação com a implementação anterior | Unificar a saúde da coleta do painel com a do `period_metrics` (definições diferentes; decisão pendente) |
| Avaliação de modelos (`train_forecast.py`) | parcial | Persistência, Ridge, gradient boosting e MLP (scikit-learn), validação progressiva, teste final, relatório reproduzível | Testes com dados sintéticos | **Rodar com os dados reais da coleta** |
| Job horário de previsão (`fit_forecast.py`, `forecast_job.py`) | parcial | Treino e gravação do modelo versionado, job a cada hora (HH:05) na tarefa `pm25-forecast` e no crontab, `ridge v0` provisório | Testes com dados sintéticos; uma execução pelo `run-forecast.cmd` no banco local, vista na série `ridge v0` do previsto × observado | **Treinar o modelo do TCC e instalar a tarefa no servidor** |
| Métricas do período e comparação CETESB | pronto | `period_metrics.py` (com congelamento do banco) e `compare_cetesb.py` | Testes | Rodar com os dados reais e o CSV do QUALAR |
| Implantação | parcial | Scripts do Windows (tarefas agendadas), serviços systemd e crontab para Linux, passo a passo do túnel | Scripts escritos; em uso desde 09/10/2026, com o nó enviando pelo túnel (Tailscale Funnel) e o app lendo pela URL pública | Testar os subcaminhos de `/v1/devices` de outra rede; segundo nó |
| App Android (`android/`) | pronto para demonstração | Tela inicial, detalhe com 24 h ou 7 dias e saúde da coleta, previsão previsto × observado, cache offline, permissão de rede local, alertas em segundo plano (nó sem dados, PM2,5 Ruim, servidor sem resposta) | testes de unidade e lint sem problemas; fluxo completo no emulador (API 37) contra a API local, inclusive offline e os alertas; no Galaxy S23 Ultra (Android 16) pelo túnel, com os dados da produção e um alerta real de PM2,5 Ruim | Medir o atraso dos alertas no celular ao longo do tempo; build de release assinado |

## 6. Testes e verificação

| Parte | Automatizado | Verificado à mão |
|---|---|---|
| Servidor | Testes de ingestão, leitura, análise, previsão, backup e dashboard (`pytest`, em `server/`) | API real com o simulador e `curl` nas rotas de leitura |
| Firmware | Testes no computador (parser, média, JSON) e compilação nas quatro combinações | — |
| App Android | Testes de unidade: contrato JSON com respostas geradas pela própria API, erros, rede local, faixas, idade, hora estimada do servidor, resumo, previsão, cache em arquivo, estado das três telas, regras dos alertas e textos das notificações | Emulador: permissão de rede local, as três telas, troca de janela, banco de 3 dias com lacuna e reinício, modelo de demonstração em `forecasts`, queda da API e reabertura sem servidor; alertas de nó sem dados e de volta, ar Ruim, servidor sem resposta e de volta, sem avisos repetidos. Celular (Galaxy S23 Ultra, Android 16, pelo túnel): atualização por cima da versão anterior, dados da produção, permissão pelo cartão e alerta real de PM2,5 Ruim |

**Nunca verificado:** o modelo do TCC em produção; a concordância entre dois nós (há um só); a comparação com a CETESB. O nó `no-01` opera em Osasco desde 09/10/2026 e envia pelo túnel. Os resultados do emulador usaram dados sintéticos e um modelo de demonstração (`demo v1`), que não é o modelo do TCC; no celular, os dados e o alerta foram os reais da produção.

## 7. Pendências e riscos

Em ordem de prioridade:

1. **Coleta contínua.** O nó `no-01` coleta desde 09/10/2026. A coleta segue até 27 ou 28/10/2026 (cerca de 19 dias), quando o banco é congelado para as métricas do período, a avaliação dos modelos e a comparação com a CETESB. É menos que as cerca de 5 semanas recomendadas no README para a avaliação, então os resultados do TCC serão preliminares e a limitação deve constar no texto.
2. **Túnel em produção.** Seguir o passo a passo do README e testar de outra rede, com `check_https.py` para a ingestão e `curl` para `/v1/devices` e seus subcaminhos.
3. **Modelo do TCC em produção.** O job horário e o `ridge v0` provisório estão prontos. Falta escolher o modelo na avaliação offline, com os dados coletados até 27 ou 28/10/2026, treiná-lo numa versão nova e instalar a tarefa `pm25-forecast` no servidor.
4. **Atraso dos alertas no celular.** Os alertas funcionam no emulador e no Galaxy S23 Ultra pelo túnel, inclusive com um alerta real de PM2,5 Ruim. Falta acompanhar a checagem periódica por alguns dias e medir o atraso com a economia de bateria da Samsung.
5. **Saúde da coleta com duas definições.** O painel e o `period_metrics` calculam completude e maior lacuna de jeitos diferentes; os números do app (que segue o painel) podem não bater com os do capítulo de resultados. Decidir se unifica.
6. **Release do app.** Assinar o APK e testar a versão de release, que exige HTTPS.

Riscos já conhecidos:

- **Servidor único.** Se o servidor parar, os nós guardam 5 dias de leituras, e os alertas do app avisam, com 15 minutos ou mais de atraso.
- **Tarefas do Windows como SYSTEM.** O `install.ps1` registra as tarefas como SYSTEM sem restringir as permissões da pasta do servidor; quem pode escrever nela (ou em `data\models`, lido com `joblib.load`) executa código como SYSTEM. Mitigação pendente: conta de baixo privilégio e ACLs na pasta.
- **Previsões recalculadas retroativamente.** Em 19/10/2026 foram recalculadas 5 horas-alvo do `ridge v0` que ficaram sem previsão porque o servidor ficou sem receber dados: 17/10 18:00 UTC (15:00 em Brasília) e 18/10 de 18:00 a 21:00 UTC (15:00 a 18:00 em Brasília). Na segunda, o nó guardou as leituras de 17:09 a 21:50 UTC durante uma queda do túnel e as enviou em bloco às 21:51 UTC (291 leituras, nenhuma perdida). O recálculo (`forecast_job.py --replay-from ... --replay-to ...`) usa o mesmo modelo e só as leituras anteriores à hora-alvo, mas não foi gravado antes do fato: está na versão `v0-retro`, separada das 28 previsões em tempo real (`v0`), e deve ser tratado como previsão retroativa, não prospectiva, no texto do TCC. Desde 20/10/2026 os scripts agendados do repositório (`run-forecast.cmd` e `crontab.example`) rodam com `--backfill-hours 24` e cobrem sozinhos quedas de até 24 horas, também na versão `-retro`; uma lacuna mais antiga ainda pede o `--replay-from` manual.
- **Token de leitura embutido no APK.** Ele pode ser extraído, mas só dá acesso de leitura e pode ser trocado no `.env`.
- **Umidade alta.** Acima de 75%, o PMS5003 tende a superestimar o PM2,5. O app avisa quantas horas da janela passaram desse limite.
- **Sensor do `no-01` sem partículas em episódios.** 10 episódios de pelo menos 20 minutos entre 12/10 e 26/10 (5,3% das leituras), com PM1, PM2,5 e PM10 em 0,0 e o sensor respondendo. 26 horas viraram suspeitas e saem da análise; a causa não está decidida (defeito do sensor ou ar muito limpo). Conferir contra o CSV da CETESB com `compare_cetesb --include-suspect` e relatar as duas análises, com e sem essas horas.

## 8. Próximos passos sugeridos

1. Instalar um segundo nó e deixar os dois lado a lado de 3 a 7 dias para medir a concordância.
2. Registrar o local do nó com `set_location` e manter o túnel e o app apontados para a URL pública.
3. Em 27 ou 28/10/2026, com a coleta encerrada, rodar `train_forecast.py` sobre o banco congelado, escolher o modelo e treiná-lo com `fit_forecast.py` numa versão nova, que o job horário passa a gravar ao lado do `ridge v0`.
4. Acompanhar os alertas no celular por alguns dias, com a bateria do app sem restrições.
5. Rodar `period_metrics.py` e `compare_cetesb.py` para o capítulo de resultados.

## 9. Como reproduzir o estado atual

```bash
# servidor, testes e API local
cd server && pip install -r requirements-dev.txt && pytest
uvicorn app.main:app --host 127.0.0.1 --port 8000          # com PM25_READ_TOKEN no .env
python -m scripts.simulate_sensor --device no-01 --token <token do no-01> --minutes 360 --realtime
python -m scripts.set_location no-01 "Local do nó"
```

```powershell
# app Android (no Windows, com o JDK do Android Studio)
cd android
$env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"
.\gradlew.bat testDebugUnitTest lintDebug assembleDebug
```

No emulador, o app fala com a API do computador por `http://10.0.2.2:8000/`, configurado em `android/local.properties` junto com o token de leitura.
