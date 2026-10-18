# Sistema de coleta de PM2,5 — TCC (UNIP, 2026)

Este repositório reúne a cadeia de coleta e o painel do projeto: o firmware dos nós sensores (ESP32 + PMS5003 + BME280 ou DHT22), a API de ingestão, o banco SQLite, o backup diário, o dashboard em Streamlit, as rotas de leitura para o app de consulta (com alertas no celular), um simulador de sensor e os chips simulados do Wokwi, para testar tudo sem hardware. A avaliação dos modelos de previsão e o job horário que grava as previsões no mesmo banco também estão aqui; o modelo do TCC depende das semanas de coleta real.

```
nó ESP32 ──HTTPS POST (JSON) via Wi-Fi e túnel──▶ API FastAPI ──▶ SQLite (WAL) ──▶ backup diário
   │ buffer em flash se a rede cair                           ├──▶ dashboard Streamlit (somente leitura)
                                                              └──▶ rotas de leitura (GET /v1/devices) ──HTTPS──▶ app de consulta
```

## Estrutura

```
firmware/     código do ESP32 (PlatformIO); host_tests/ testa a parte sem hardware no computador
server/app/   API (main.py), rotas de leitura (read_api.py), contrato de dados (models.py), acesso ao banco (db.py), regras de análise (analytics.py), dados e modelos de previsão (forecasting.py), esquema (schema.sql)
server/scripts/  backup.py, simulate_sensor.py, set_location.py, check_https.py, train_forecast.py, fit_forecast.py, forecast_job.py, period_metrics.py, compare_cetesb.py
server/tests/    testes da API, incluindo o JSON gerado pelo próprio firmware
server/dashboard/  dashboard em Streamlit (status, séries, previsto × observado)
server/deploy/   serviços systemd (API e dashboard) e exemplo de crontab
android/      app de consulta em Kotlin (Jetpack Compose), alimentado pelas rotas de leitura da API
docs/         planejamento do sistema e estado atual de cada parte (planejamento-e-estado.md)
wokwi/        circuito (diagram.json), chips simulados do PMS5003 e do BME280, config.h e bibliotecas para rodar o firmware no Wokwi
.githooks/    hook commit-msg e a checagem de commits usada também no CI (ver "Padrão de commits")
```

## Início rápido, sem hardware

No computador (Linux, macOS ou Windows), com Python 3.10 ou mais recente:

```bash
cd server
python -m venv .venv
source .venv/bin/activate            # no Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env                 # troque os tokens (ver comentário no arquivo)
pytest                               # testes da API, do dashboard e dos scripts
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Em outro terminal, simule seis horas de dados de um nó e depois uma leitura por minuto:

```bash
python -m scripts.simulate_sensor --device no-01 --token <token do no-01> --minutes 360 --realtime
```

A documentação interativa da API fica em `http://localhost:8000/docs`. O banco aparece em `server/data/pm25.db` e pode ser aberto no DB Browser for SQLite ou com pandas. Com dados chegando, abra o dashboard num terceiro terminal:

```bash
streamlit run dashboard/app.py       # abre em http://localhost:8501
```

## Contrato de dados (versão 1)

Cada leitura é a média de um minuto de relógio. O nó envia `POST /v1/measurements` com o cabeçalho `Authorization: Bearer <token do nó>`:

```json
{
  "schema_version": "1",
  "device_id": "no-01",
  "readings": [
    {"boot_id": 3, "seq": 0, "ts": "2026-09-22T12:00:00Z", "uptime_s": 120, "samples": 58,
     "pm1": 8.2, "pm25": 12.5, "pm10": 15.0, "pm25_cf1": 13.0,
     "temperature": 23.4, "humidity": 61.0, "rssi": -63}
  ]
}
```

O campo `ts` marca o início da janela de um minuto, sempre em UTC. `pm25` é o valor "atmospheric environment" do PMS5003, usado nas análises; `pm25_cf1` é o valor "standard particle", guardado porque as correções publicadas para sensores Plantower costumam partir dele. `samples` conta quantos quadros do sensor entraram na média, e `rssi` e `uptime_s` explicam lacunas depois. Temperatura, umidade e RSSI podem vir como `null`. Um lote aceita até 500 leituras.

| Resposta | Significado | O que o nó faz |
|---|---|---|
| 201 `{"inserted": n, "duplicates": m}` | Gravado no disco | Apaga o lote do buffer |
| 401 ou 403 | Token ausente ou inválido (401, mesma mensagem nos dois casos) ou de outro nó (403) | Mantém o lote e tenta de novo (erro de configuração) |
| 413 | Corpo acima do limite em bytes | Descarta o lote (um lote de 60 leituras fica muito abaixo do limite) |
| 429 | IP bloqueado por falhas de autenticação seguidas | Mantém o lote e tenta de novo com espera crescente |
| 422 | Fora do contrato; cópia guardada em `invalid_messages` | Descarta o lote, para não reenviar o mesmo erro para sempre |
| Falha de rede ou 5xx | Nada foi gravado | Mantém o lote e tenta de novo com espera crescente |

Cada leitura é identificada por `(device_id, boot_id, seq)`. O `boot_id` é um contador gravado na memória não volátil do ESP32 e incrementado a cada inicialização; o `seq` recomeça do zero a cada boot. A API ignora leituras repetidas, então reenviar um lote é sempre seguro, e um reinício nunca faz uma leitura nova colidir com uma antiga. Isso também separa os tipos de falha: um salto de `seq` dentro do mesmo `boot_id` é perda de mensagem, um intervalo de tempo sem salto de `seq` é minuto sem leitura válida do sensor, e um `boot_id` novo é um reinício.

## Rotas de leitura (app de consulta)

O app de consulta lê os dados pela própria API, sem acesso ao arquivo do banco. As rotas ficam sob `/v1/devices`, aceitam só `GET` e pedem `Authorization: Bearer <PM25_READ_TOKEN>`. Esse token é diferente dos tokens dos nós: um nó não lê e o app não grava, e a configuração recusa um token de leitura igual ao de um nó. Sem `PM25_READ_TOKEN`, as rotas respondem 503. As falhas de autenticação contam para o mesmo bloqueio de IP da ingestão. As rotas abrem o banco em modo somente leitura e usam as regras de `app/analytics.py`, as mesmas do dashboard, então os números do app e do painel coincidem.

| Rota | Devolve |
|---|---|
| `GET /v1/devices` | Para cada nó: local, estado (`online`, `late` a partir de 3 min sem envio, `silent` a partir de 15 min), minutos desde o último recebimento e a leitura mais recente |
| `GET /v1/devices/{id}/hourly?start=&end=` ou `?hours=` | Uma linha por hora de `[start, end)`, inclusive as horas sem leitura: `readings`, `valid` (pelo menos 45 leituras de qualidade `ok`) e as médias, nulas quando a hora não vale. Padrão: últimas 24 h; no máximo 31 dias; o início é arredondado para a hora cheia. Com `hours=N` (no lugar de `start`), vêm as últimas N horas completas, terminando na hora cheia atual pelo relógio do servidor |
| `GET /v1/devices/{id}/health?hours=24` | Saúde da coleta (1 a 168 h): completude, maior lacuna, mensagens perdidas, reinícios, duplicatas descartadas e leituras marcadas |
| `GET /v1/devices/{id}/forecast?hours=48` | Observado e previsões por hora (persistência e cada modelo gravado em `forecasts`), com MAE, RMSE e skill score de cada previsor |

Os horários são UTC, em ISO 8601 com `Z`, e cada resposta traz `generated_at`, o relógio do servidor: o app calcula a idade de um dado por ele, sem depender do relógio do celular. Um nó sem leituras responde 404, e parâmetros fora dos limites, ou datas sem fuso, respondem 422. O contrato completo aparece em `http://localhost:8000/docs`, que não é publicado pelo túnel.

```bash
curl -H "Authorization: Bearer <token de leitura>" http://localhost:8000/v1/devices
```

O local de cada nó aparece no app e no dashboard. Ele é gravado depois da primeira leitura do nó, que o cadastra no banco:

```bash
python -m scripts.set_location no-01 "EE Exemplo, Vila Mariana (fachada, 3 m do chão)"
```

## App Android

O app de consulta fica em `android/`, em Kotlin com Jetpack Compose, e só lê dados pelas rotas acima. A tela inicial mostra um cartão por nó com o PM2,5 da leitura mais recente, a cor da faixa da CETESB, temperatura, umidade, PM10, o estado do nó e a idade da leitura, calculada pelo relógio do servidor (`generated_at`). A tela se atualiza ao abrir, a cada minuto enquanto está visível e ao puxar a lista para baixo. Se uma atualização falhar, o app continua mostrando os últimos dados, com o motivo da falha e a hora da última atualização.

Tocar num nó abre o detalhe, com as últimas 24 horas ou os últimos 7 dias, pedidos com `hours` para a janela vir do relógio do servidor. O gráfico do PM2,5 por hora interrompe a linha nas horas inválidas, começa em zero e marca com uma linha tracejada o limite da faixa Boa (25 µg/m³). Abaixo dele aparecem a média, a máxima com o horário, as horas válidas, as horas acima de 25 µg/m³ e, quando houver, quantas horas tiveram umidade média acima de 75%. A saúde da coleta da mesma janela mostra completude, maior lacuna, reinícios, mensagens perdidas, duplicatas descartadas e leituras marcadas. O histórico e a saúde são pedidos em paralelo, e a tela só troca de dados quando os dois chegam. Ao mudar de janela, os dados da anterior saem da tela, para não serem lidos como os da nova.

Do detalhe se abre a previsão, com as últimas 48 horas de `/forecast`. No topo fica a hora em andamento, pelo relógio do servidor, com a média prevista por cada previsor e a faixa correspondente: a observada só fecha no fim da hora. O gráfico sobrepõe o observado (linha cheia) à persistência e a cada modelo gravado em `forecasts` (tracejados), com legenda e rótulos de dia e hora, porque as 48 horas cruzam a meia-noite. Abaixo vêm MAE, RMSE e skill score de cada previsor, com a leitura do skill em relação à persistência. Enquanto nenhum modelo publicar previsões, a tela mostra só a persistência e explica por quê.

O app guarda a última resposta de cada rota e janela (`devices`, `hourly-<nó>-<horas>`, `health-…`, `forecast-…`) como JSON em `cacheDir/respostas`. Ao abrir uma tela, a versão salva aparece enquanto a rede responde e é substituída pela resposta nova; sem rede, ela fica na tela com o aviso da falha e a data dos dados. A escrita vai para um arquivo temporário renomeado de uma vez, então um desligamento no meio dela deixa a versão anterior intacta, e uma versão que não siga mais o contrato é ignorada. O sistema pode limpar o `cacheDir` quando faltar espaço; tudo ali pode ser buscado de novo.

Cada resposta salva leva também o instante em que chegou, pelo relógio do celular. A idade das leituras usa a hora estimada do servidor agora: o `generated_at` da resposta mais o tempo desde a chegada. Do celular entra só a diferença entre dois instantes dele mesmo, então um relógio errado não afeta a conta, e uma leitura salva ontem aparece com um dia de idade, não com os minutos que tinha quando chegou. Pelo mesmo motivo, o estado de cada nó é recalculado com os limites que a própria resposta traz (`late_after_min` e `silent_after_min`): com a resposta recém-chegada o resultado é o do servidor, e com uma resposta salva um nó em operação passa a atrasado e depois a sem dados, em vez de continuar verde. E a previsão só chama de "hora em andamento" a hora atual de verdade.

Os alertas rodam em segundo plano. Na tela inicial, um cartão explica o que eles fazem e pede a permissão de notificação, exigida no Android 13 ou mais novo. Ele some quando as notificações estão ligadas e pode ser dispensado com "Agora não". Com a permissão, o WorkManager roda uma checagem quando os alertas são ligados e depois a cada 15 minutos ou mais, conforme o Android permitir: em economia de bateria ou com o celular parado, ele adia. Cada checagem consulta `/v1/devices` e a última hora completa de cada nó (`/hourly?hours=1`), e só avisa um fato novo:

- **Nó sem dados:** o nó passou ao estado "sem dados" (15 minutos sem envio). A volta dele substitui esse aviso na bandeja. Um nó que nunca enviou leituras não gera alerta.
- **Ar ruim:** a média da última hora completa ficou na faixa Ruim ou pior da CETESB (acima de 50 µg/m³), com as faixas de 24 horas usadas como referência. Avisa de novo a cada piora dentro do episódio; quando a média cai abaixo de Ruim, o episódio acaba e uma nova subida volta a avisar.
- **Servidor sem resposta:** duas checagens seguidas falharam. A volta do servidor também é avisada. Sem internet validada no celular, a checagem não roda, para não acusar o servidor quando quem está sem rede é o celular; com a API na rede local, basta a conexão.

O que já foi avisado fica em `filesDir/alertas`, que o sistema não limpa. Cada tipo de alerta tem um canal (Sensores, Qualidade do ar, Servidor), que pode ser silenciado nas configurações do Android. Como a checagem roda no celular, fora do servidor, ela percebe também o servidor fora do ar. Na versão de depuração, `adb shell am broadcast -n br.unip.pm25/.alerts.CheckNowReceiver` roda uma checagem na hora, sem esperar o agendamento; só o `adb` e o sistema conseguem chamá-lo.

Para rodar no emulador, com a API e o simulador no mesmo computador:

1. Defina `PM25_READ_TOKEN` no `server/.env`, inicie a API e o simulador (ver "Início rápido").
2. Abra a pasta `android/` no Android Studio e deixe o Gradle sincronizar.
3. Copie as linhas de `android/local.properties.example` para `android/local.properties` (o Android Studio cria esse arquivo) e coloque o token de leitura. No emulador, `http://10.0.2.2:8000/` é a API do computador.
4. Rode a configuração `app` num emulador. Na primeira abertura, o app explica e pede o acesso à rede local (ver abaixo).

O Android 17 bloqueia a rede local para apps com `targetSdk` 37, e o `10.0.2.2` do emulador é um endereço privado. Por isso o app declara `ACCESS_LOCAL_NETWORK` e, só quando a URL configurada aponta para a rede local (endereço privado, link-local ou `.local`), mostra uma tela com o motivo antes do pedido do sistema, que aparece como "Dispositivos próximos". Pela URL pública do túnel nada é pedido. Se a permissão for negada, a tela indica onde liberá-la nas configurações.

O HTTP sem criptografia só é aceito na versão de depuração e só para `10.0.2.2` e `localhost`; a versão de release exige HTTPS, que é o caminho do túnel. O token de leitura vai embutido no APK e pode ser extraído dele: ele só dá acesso de leitura e pode ser trocado no `.env` a qualquer momento.

O projeto usa o Android Gradle Plugin 9.4 (com o Kotlin embutido), Gradle 9.8.1, Kotlin 2.4 e `compileSdk` 37. O wrapper confere o SHA-256 da distribuição do Gradle. Pela linha de comando, use o JDK do Android Studio:

```powershell
cd android
$env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"
.\gradlew.bat testDebugUnitTest lintDebug assembleDebug
```

Os testes de unidade cobrem o contrato JSON (com respostas reais da API), a classificação de erros, a detecção de endereços da rede local, as faixas, a idade da leitura, o resumo do histórico, a hora em andamento e a leitura do skill score na previsão, o cache em arquivo (escrita atômica, cópia por rota e janela, cópia estragada ignorada), a hora estimada do servidor, o estado das três telas quando uma atualização falha ou o app reabre sem rede, as regras dos alertas (um aviso por fato, volta do nó, faixas, falhas seguidas do servidor, estado salvo entre execuções ou estragado) e os textos e identificadores das notificações. O fluxo completo foi verificado no emulador (API 37) contra a API local alimentada pelo simulador e por um banco sintético de 3 dias com lacuna e reinício, inclusive o pedido de permissão, a troca de janela no detalhe, a previsão com um modelo de demonstração gravado em `forecasts`, a queda da API com os dados mantidos na tela e o app reaberto minutos depois sem servidor, mostrando as três telas a partir do cache. Os alertas foram verificados no emulador contra uma API de desenvolvimento na porta 8001: o pedido da permissão pelo cartão, o nó sem dados, a volta do nó com a última hora na faixa Ruim, uma nova checagem sem repetir avisos, o servidor parado (aviso só na segunda falha) e de volta. Num celular de verdade, foi testado em 18/10/2026 num Galaxy S23 Ultra (Android 16), pela URL pública do túnel:

- a versão de depuração da `main` instalada por cima da anterior, com os dados do app mantidos;
- a tela inicial com os dados da produção;
- o pedido da permissão pelo cartão;
- na checagem imediata, um alerta real de PM2,5 Ruim no `no-01`, com média de 59,5 µg/m³ das 00:00 à 01:00, mostrada como 60.

Ainda não foram medidos a checagem periódica ao longo de horas, o atraso em Doze e a economia de bateria da Samsung. Para checagens mais regulares, deixe a bateria do app como "Sem restrições" (Configurações > Aplicativos > PM2,5 > Bateria).

## Banco de dados

O arquivo único do SQLite opera em modo WAL, que deixa o dashboard ler enquanto a API grava, e com `synchronous=FULL`, para que o 201 só saia depois de a leitura estar no disco. A tabela `measurements` é imutável: gatilhos impedem `UPDATE` e `DELETE`, e toda limpeza ou agregação vai para tabelas derivadas. Na ingestão só se marcam valores fisicamente implausíveis na coluna `quality`; critérios que podem mudar depois, como a marcação de umidade alta, ficam no processamento em batch. A tabela `ingest_batches` registra cada requisição aceita, e a `forecasts` recebe as previsões do job horário (ver "Previsão em produção").

Consultas que viram métricas de infraestrutura no capítulo de resultados:

```sql
-- Completude horária: horas com pelo menos 45 minutos (75%) entram nas médias
SELECT device_id, substr(ts_sensor, 1, 13) AS hora_utc, COUNT(*) AS minutos
FROM measurements GROUP BY device_id, hora_utc ORDER BY hora_utc;

-- Reinícios por nó
SELECT device_id, COUNT(DISTINCT boot_id) - 1 AS reinicios FROM measurements GROUP BY device_id;

-- Mensagens perdidas: lacunas de seq dentro de cada inicialização
SELECT device_id, boot_id, MAX(seq) + 1 - COUNT(*) AS perdidas FROM measurements GROUP BY device_id, boot_id;

-- Duplicatas descartadas e maior lote (lotes grandes indicam buffer esvaziado após queda de rede)
SELECT device_id, SUM(n_duplicates) AS duplicatas, MAX(n_readings) AS maior_lote
FROM ingest_batches GROUP BY device_id;
```

## Dashboard

O dashboard lê o banco em modo somente leitura e tem três abas. Status mostra, para cada nó, a última leitura, há quanto tempo chegou o último envio e uma tabela de saúde da coleta nas últimas 24 horas: completude, maior lacuna, mensagens perdidas, reinícios, duplicatas descartadas e leituras marcadas; a aba se atualiza sozinha a cada minuto. Dispositivos de teste (identificadores que começam com `teste`, como o `teste-https`) não aparecem no painel, e um nó cadastrado em `PM25_DEVICE_TOKENS` que ainda não enviou leituras aparece com um card reservado, "aguardando instalação". Séries mostra PM2,5, PM10, PM1,0, temperatura e umidade por período, em médias horárias (só horas com pelo menos 45 minutos de leitura) ou minuto a minuto, com a linha de 75% de umidade e a parcela de registros acima dela, e exporta os dados em CSV. Previsto × observado compara as últimas 48 horas com a previsão de persistência, calculada na hora, e com as previsões que o job horário gravar na tabela `forecasts`, com MAE, RMSE e skill score. Cada previsor é medido só nas horas que têm observação, persistência e previsão dele, para o skill score comparar o modelo e a persistência nas mesmas horas, como em `train_forecast.py`. As linhas são interrompidas onde faltam dados, em vez de ligar pontos distantes. Os horários aparecem no fuso de Brasília; no banco, tudo continua em UTC.

## Firmware

| PMS5003 | ESP32 |
|---|---|
| Pino 1 (VCC) | 5 V (VIN) |
| Pino 2 (GND) | GND |
| Pino 4 (RX) | GPIO17 (TX2) |
| Pino 5 (TX) | GPIO16 (RX2) |
| Pinos 3 (SET) e 6 (RESET) | Desconectados: o sensor opera continuamente |

O PMS5003 precisa de 5 V na alimentação, mas seus sinais são de 3,3 V e ligam direto no ESP32. O BME280 vai em 3,3 V, com SDA no GPIO21 e SCL no GPIO22; o DHT22 vai em 3,3 V, com o dado no GPIO4 e resistor de pull-up de 10 kΩ, se o módulo não tiver um. Os pinos podem ser trocados em `config.h`.

Com o PlatformIO (VS Code), copie `firmware/src/config.example.h` para `firmware/src/config.h`, preencha Wi-Fi, URL da API, `DEVICE_ID`, token e o sensor de temperatura e umidade usado, e rode:

```bash
cd firmware
pio run -t upload
pio device monitor
```

Na Arduino IDE, crie uma pasta `pm25_node` com um arquivo `pm25_node.ino` vazio, copie para ela `main.cpp`, `pms5003.h`, `reading.h` e o seu `config.h`, instale as bibliotecas "Adafruit BME280 Library" e "DHT sensor library" e compile para a placa "ESP32 Dev Module".

Depois de ligado, o nó descarta os primeiros 30 segundos do PMS5003 (tempo de estabilização da ventoinha), espera o relógio sincronizar por NTP e passa a fechar uma leitura a cada minuto de relógio. Com HTTPS o envio só começa depois do NTP (sem hora válida o certificado não é aceito), e uma falha de conexão ou de handshake TLS vale como falha de rede: o lote continua no buffer e é reenviado com espera crescente. Cada tentativa HTTPS espera no máximo 15 s pela conexão, 20 s pelo handshake e 8 s pela resposta, abaixo do watchdog de 90 s. O monitor serial mostra uma linha por minuto, por exemplo `[leitura] seq=41 pm2.5=13.2 quadros=58 T=23.9 UR=62.4 rssi=-64 pendentes=0`. O que a API não confirmar vai para um buffer em LittleFS com capacidade para cinco dias, que sobrevive a reinícios e quedas de energia. Se o Wi-Fi ficar 15 minutos fora, o ESP32 reinicia sozinho, e um watchdog de 90 segundos cobre travamentos.

O firmware foi compilado sem avisos (`-Wall`) nas quatro combinações dos cores Arduino do ESP32 2.0.17 e 3.3.12 com BME280 e DHT22 (inclusive com HTTPS e a CA raiz embutida). Para o core 3.x no PlatformIO, a plataforma testada foi `https://github.com/pioarduino/platform-espressif32/releases/download/55.03.312-1/platform-espressif32.zip`; no Windows, rode o `pio` do PowerShell, não do Git Bash (o instalador do core 3.x recusa o MSYS). Uso de memória, em bytes (RAM estática / flash), antes e depois do HTTPS:

| Combinação | Antes | Depois |
|---|---|---|
| Core 2.0.17, BME280 | 50 808 / 1 005 265 | 50 808 / 1 005 573 |
| Core 2.0.17, DHT22 | 50 312 / 979 241 | 50 312 / 979 521 |
| Core 3.3.12, BME280 | 54 120 / 1 144 780 | 54 120 / 1 145 032 |
| Core 3.3.12, DHT22 | 54 056 / 1 139 320 | 54 056 / 1 139 564 |

A RAM estática não muda, e a flash cresce menos de 310 bytes; o buffer de cinco dias fica em LittleFS e o lote de 60 leituras segue sendo um vetor estático, então ambos continuam cabendo. As duas medidas "antes" usam o mesmo `config.h` da "depois", com a CA embutida. O que não foi medido, por falta de hardware, é o pico de memória dinâmica durante o handshake TLS (da ordem de dezenas de KiB de heap, liberados ao fim de cada envio): ao testar o nó, confira a linha `[tls] ... heap livre` do monitor serial. Com `https://` na `API_URL` e sem `API_ROOT_CA`, o firmware não compila, a menos que se defina `API_TLS_INSECURE_TEST` (só para bancada). A leitura dos quadros do sensor, a média do minuto e a montagem do JSON têm testes que rodam no computador:

```bash
cd firmware/host_tests
g++ -std=c++17 -Wall -I../src test_core.cpp -o test_core && ./test_core
```

O teste gera `payload_exemplo.json`, e o teste da API `test_contrato_payload_gerado_pelo_firmware_e_aceito` confere que a API aceita exatamente esse JSON. Nada disso substitui o teste com o hardware real, que ainda precisa ser feito.

## Simulação no Wokwi

A pasta `wokwi/` traz o projeto completo do simulador, exceto o código do firmware: o circuito (`diagram.json`), os dois chips simulados (`.chip.c` com o comportamento e `.chip.json` com os pinos e os controles: pm1, pm25 e pm10 no PMS5003; temp, press e hum no BME280), o `config.wokwi.h` e a lista de bibliotecas. Os chips substituem os do primeiro esboço do projeto no Wokwi, cujas versões tinham dois problemas. O chip do PMS5003 só preenchia os campos CF=1 do quadro e deixava zerados os campos "atmospheric environment", que o firmware usa como PM2,5; com ele, o firmware novo leria sempre zero. O chip do BME280 convertia para os registradores com aproximações lineares: a temperatura saía certa, mas a pressão errava dezenas de hPa e a umidade só batia perto de 50% (20% virava 0% e 80% virava 100%), justamente a faixa que importa para a análise de umidade alta. O chip novo aplica as fórmulas de compensação da biblioteca Adafruit e procura o valor de registrador que reproduz cada controle. Testado fora do Wokwi, com um stub da API, o erro ficou abaixo de 0,01 °C, 0,01 hPa e 0,01% de umidade entre −10 e 45 °C, 900 e 1050 hPa e 0 e 100%, e os quadros do PMS5003 simulado passam no parser do firmware sem erro de checksum.

Para montar o projeto em wokwi.com, crie um projeto ESP32 e coloque nele os arquivos de `wokwi/`: `diagram.json`, `libraries.txt`, os quatro arquivos dos chips e `config.wokwi.h` renomeado para `config.h`. Some a eles `main.cpp`, `pms5003.h` e `reading.h` de `firmware/src/` e deixe o `sketch.ino` vazio, porque o firmware está todo no `main.cpp`. O circuito liga o PMS5003 na UART2 (GPIO16 e 17) e o BME280 em 0x76 (GPIO21 e 22), como no `config.wokwi.h`. No Wokwi for VS Code os chips precisam ser compilados para `.wasm` e declarados num `wokwi.toml`, que ainda não estão no repositório. A rede simulada é sempre `Wokwi-GUEST`, sem senha, no canal 6. Para o ESP32 simulado alcançar a API no seu computador é preciso o gateway privado do Wokwi (incluído no Wokwi for VS Code; no navegador, exige a assinatura Wokwi Club), e a URL passa a ser `http://host.wokwi.internal:8000/v1/measurements`. Sem o gateway, o simulador só alcança a internet: exponha a API local por um túnel (ngrok ou cloudflared), use a URL `https` gerada e ative `API_TLS_INSECURE_TEST` no `config.h` (o simulador não valida o certificado; esse modo é só para testes).

Dá para exercitar no simulador os cenários que importam no campo. Suba a umidade acima de 75% e veja a marcação no dashboard. Pare a API por alguns minutos e religue: o nó guarda as leituras em flash e as reenvia num lote, e a tabela de saúde não deve registrar perdas. Reinicie o ESP32 simulado: o `boot_id` muda e as leituras seguem sem colisão.

## Implantação no servidor sempre ligado

Em um servidor Windows (notebook ou PC dedicado), use os scripts de `server/deploy/windows/` (veja o `README.md` dessa pasta), que fazem o papel dos serviços `systemd` e do crontab descritos abaixo. Eles gravam os logs em `server\data` em UTF-8, como no Linux, com o modo UTF-8 do Python (`PYTHONUTF8=1`).

O servidor precisa ficar ligado durante toda a coleta. A API escuta só em `127.0.0.1` (o acesso dos nós é pelo túnel HTTPS, descrito na seção "Transporte HTTPS entre redes"); só para a alternativa HTTP na rede local é preciso IP fixo e `--host 0.0.0.0`. Instale o projeto em `/home/pi/pm25-iot`, crie o ambiente virtual e o `.env` como no início rápido (com `requirements-dashboard.txt`; no Raspberry Pi, use o sistema de 64 bits) e ative os serviços e as tarefas agendadas:

```bash
sudo cp server/deploy/pm25-api.service /etc/systemd/system/
sudo cp server/deploy/pm25-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now pm25-api pm25-dashboard
crontab -e     # cole o conteúdo de server/deploy/crontab.example
curl http://127.0.0.1:8000/health   # no próprio servidor; de fora, pelo túnel
```

Para a previsão horária, instale também o `requirements-ml.txt` e treine um modelo (seção "Previsão em produção"); sem modelo em `data/models`, a linha do job no crontab só registra o aviso no log.

Aponte `PM25_BACKUP_DIR` para um pendrive ou uma pasta sincronizada com a nuvem: um backup no mesmo cartão SD não protege contra falha do cartão, o risco mais comum em Raspberry Pi ligado por meses.

Antes de instalar cada nó, meça o RSSI no ponto exato de instalação (o log mostra o valor a cada minuto), confirme que a rede permite NTP (porta UDP 123) e deixe os dois sensores lado a lado nos primeiros 3 a 7 dias, para medir a concordância entre eles.

## Transporte HTTPS entre redes

Os nós ficam em redes diferentes da do servidor, então a leitura viaja pela internet. A solução adotada é um **túnel gerenciado com certificado público válido**: o Tailscale Funnel. Não há porta aberta no roteador, nem IP fixo, nem domínio próprio, nem CA própria (que esbarraria em CGNAT, IP dinâmico e renovação). O cliente do Tailscale no Windows do servidor recebe as conexões HTTPS, termina o TLS ali mesmo e repassa a requisição para a API em `127.0.0.1`.

```
                       internet                                    computador do servidor (Windows)
nó ESP32 ──HTTPS──▶ Funnel (retransmissão da Tailscale) ──TCP cifrado──▶ tailscaled ──HTTP──▶ API (127.0.0.1:8000) ──▶ SQLite
 valida o certificado    https://MAQUINA.TAILNET.ts.net                  termina o TLS            uvicorn --proxy-headers
 (ISRG Root X1)          /v1/measurements, /v1/devices e /health         coloca X-Forwarded-For   (o dashboard, :8501, não é publicado)
```

O túnel publica só três caminhos: `/v1/measurements` (ingestão), `/v1/devices` (leitura, para o app de consulta) e `/health`. A documentação e o painel interativo da API (`/docs`, `/openapi.json`) não passam, e o dashboard Streamlit não é exposto. A API continua escutando apenas em `127.0.0.1`, e o `--proxy-headers` do uvicorn (aceito só de `127.0.0.1`) faz o IP gravado em `ingest_batches` e `invalid_messages` ser o do nó, não o do túnel.

### Passos do usuário

Nada disto foi executado na implementação: dependem da sua conta e do computador do servidor.

1. Crie a conta em [tailscale.com](https://tailscale.com) e instale o cliente no Windows do servidor. Entre com a mesma conta.
2. No painel de administração, em DNS, ative o **MagicDNS** e o **HTTPS Certificates** (a Tailscale emite o certificado pela Let's Encrypt).
3. Ative a exposição pública (o atributo `funnel`). Ao rodar o primeiro `tailscale funnel`, o cliente abre uma página para aprovar. Também dá para editar a política da conta (Access controls) e acrescentar `"nodeAttrs": [{"target": ["autogroup:member"], "attr": ["funnel"]}]`; restrinja `target` ao seu usuário ou à máquina do servidor se a conta tiver outros membros.
4. Atualize o servidor: reinstale as tarefas com `server\deploy\windows\install.ps1` (a API passa a escutar só em `127.0.0.1` e a regra de firewall da porta 8000 é removida), e reinicie a API.
5. Cadastre um token para o dispositivo de teste e um para cada nó em `server\.env`, por exemplo `PM25_DEVICE_TOKENS=no-01:<token>,no-02:<token>,teste-https:<token>`. Gere cada token com `python -c "import secrets; print(secrets.token_urlsafe(24))"`. Para o app de consulta, gere mais um e grave em `PM25_READ_TOKEN`.
6. Publique só os três caminhos, apontando para a API local (PowerShell, no servidor):

   ```powershell
   tailscale funnel --bg --set-path=/v1/measurements http://127.0.0.1:8000/v1/measurements
   tailscale funnel --bg --set-path=/v1/devices http://127.0.0.1:8000/v1/devices
   tailscale funnel --bg --set-path=/health http://127.0.0.1:8000/health
   tailscale funnel status
   ```

   O Funnel só aceita as portas 443, 8443 e 10000 (a padrão é a 443, sem porta na URL). O `--bg` mantém a publicação depois de reinicializações. O prefixo do caminho é removido antes de a requisição chegar à API, por isso o destino repete o caminho. A URL pública é `https://<máquina>.<tailnet>.ts.net`, exibida pelo `status`. Para desfazer: repita o comando com `off` no fim.
7. Confira o isolamento, de qualquer rede: `curl -i https://<URL pública>/health` deve responder 200, e `/docs` e `/` devem responder 404. `/v1/devices` deve responder 401 sem token e 200 com `-H "Authorization: Bearer <token de leitura>"`; `/v1/devices/<id>/hourly` com o mesmo token confirma que os subcaminhos passam pelo túnel (o código-fonte do cliente repassa o resto do caminho, mas isso não foi testado com o Funnel).
8. Teste o caminho completo, **de outra rede** (por exemplo, o celular como roteador ou outro computador), com o `check_https.py`:

   ```bash
   cd server
   python -m scripts.check_https --url https://<URL pública>/v1/measurements --token <token do teste-https>
   ```

   Saída esperada: `OK: HTTP 201 ...`. Em caso de falha o script sai com código diferente de zero e diz o motivo (2 certificado, 3 token recusado, 4 device_id incompatível, 5 IP bloqueado, 6 tempo esgotado, 8 sem conexão). A leitura sintética fica gravada com o `device_id` `teste-https`, pois `measurements` é imutável. Identificadores que começam com `teste` ficam fora do dashboard, das rotas de leitura do app (e, com elas, dos alertas) e das métricas do período. O erro de certificado exige TLS real e não tem teste automático; para vê-lo, aponte o script a um servidor HTTPS com certificado autoassinado.
9. Em cada nó, copie `firmware/src/config.example.h` para `config.h` e preencha `WIFI_SSID`, `WIFI_PASS`, `API_URL` (a URL pública terminando em `/v1/measurements`), `DEVICE_ID` e `DEVICE_TOKEN` (o token daquele nó). Mantenha `API_ROOT_CA` como está no exemplo e grave o firmware. No monitor serial, a primeira leitura enviada aparece como `[leitura] ... pendentes=0`; um `[tls] erro` indica falha no certificado ou na rede.

### Proteções da API

| Situação | Resposta | Registro |
|---|---|---|
| Corpo acima de `PM25_MAX_BODY_BYTES` (padrão 256 KiB; um lote de 500 leituras ocupa ~125 KiB) | 413 | nenhum |
| Token ausente ou inválido | 401 com a mesma mensagem nos dois casos | `invalid_messages`, sem o token |
| Token válido para outro `device_id` | 403 | `invalid_messages` |
| Rota de leitura sem o token de leitura (inclusive com o token de um nó) | 401 | nenhum (conta para o bloqueio do IP) |
| `PM25_AUTH_MAX_FAILS` (10) falhas de autenticação seguidas do mesmo IP | 429 com `Retry-After`, por `PM25_AUTH_BLOCK_MIN` (5) minutos, mesmo com token correto | nenhum |

O contador fica só na memória, por IP, e zera com uma autenticação válida (um 403 conta como autenticação válida). Reiniciar a API libera todos os IPs. O firmware trata 401, 403 e 429 como erro a corrigir ou a esperar: o lote continua no buffer e é reenviado com espera crescente.

### Certificado raiz embutido

O nó confere o servidor contra a **ISRG Root X1**, embutida em `API_ROOT_CA` (impressão digital SHA-256 `96:BC:EC:06:26:49:76:F3:74:60:77:9A:CF:28:C5:A7:CF:E8:A3:C0:AA:E1:1A:8F:FC:EE:05:C0:BD:DF:08:C6`, conferida contra o PEM de `letsencrypt.org/certs/isrgrootx1.pem`). O certificado vale até **2035-06-04**; a página da Let's Encrypt (consultada em 2026-10-08) a lista como confiável até cerca de 2030-06-04, por política dos programas de raízes. Como o relógio do ESP32 só é válido depois do NTP, o nó não tenta enviar por HTTPS antes disso.

Plano de rotação:

- Em **2030-01**, reveja a página de certificados da Let's Encrypt. Se a X1 deixar de ser a raiz das cadeias, troque o PEM em `config.h` e regrave os nós.
- A Let's Encrypt já emite pela nova hierarquia (intermediárias YE/YR, cadeias que ainda terminam na X1 por certificação cruzada). Se a Tailscale passar a servir uma cadeia que não termina na X1, o handshake falha com `certificate verify failed` no log `[tls]`. Os nós continuam guardando as leituras (cinco dias de buffer): troque `API_ROOT_CA` pela nova raiz e regrave dentro desse prazo. O upload normal do PlatformIO não apaga a partição do LittleFS, onde fica o buffer.
- Para aceitar mais de uma raiz durante a transição, concatene os PEMs em `API_ROOT_CA`.

### Diferenças em relação ao planejado

Conferidas na documentação e no código-fonte do Tailscale e na página da Let's Encrypt, em 2026-10-08:

- O Funnel exige Tailscale 1.38.3 ou mais recente, MagicDNS, HTTPS habilitado e o atributo `funnel`; as portas permitidas são só 443, 8443 e 10000; há limite de banda, não configurável nem numerado na documentação.
- A página do Funnel não afirma suporte ao Windows, nem fala de restrição por caminho. A restrição aqui se apoia em `--set-path` e no código-fonte do cliente (`ipn/ipnlocal/serve.go`): caminhos sem publicação respondem 404, e o prefixo do caminho é removido antes do repasse. **Valide com o passo 7.**
- A documentação não menciona `X-Forwarded-For`; o código-fonte o grava (`Set`, não acrescenta) com o IP de origem nas requisições do Funnel. Se não chegasse, todas as requisições pareceriam vir de `127.0.0.1` e dez tentativas inválidas bloqueariam todos os nós por cinco minutos (eles guardariam as leituras e reenviariam). Confira com `SELECT remote_addr, COUNT(*) FROM ingest_batches GROUP BY remote_addr;` depois do primeiro envio: o endereço deve ser público, não `127.0.0.1`.
- A Let's Encrypt lista a X1 como confiável até 2030-06-04, enquanto o certificado vale até 2035-06-04.
- **O túnel não foi testado com um ESP32 nesta implementação** (sem conta Tailscale nem hardware). Se, ao seguir os passos, o handshake não completar, a alternativa é HTTP na rede local, descrita abaixo.

### Alternativa: HTTP na rede local

Quando nó e servidor estão na mesma rede, dá para dispensar o túnel. Defina a variável de sistema `PM25_API_HOST=0.0.0.0`, rode `install.ps1 -OpenApiPort` (libera a TCP 8000 nas redes Privada e Domínio), reserve o IP do servidor no roteador e use `API_URL "http://<IP>:8000/v1/measurements"` no `config.h`. Não há criptografia: só o token protege.

## Limitações conhecidas

Leituras anteriores à primeira sincronização NTP após um boot são descartadas, porque não teriam horário confiável; um módulo de relógio DS3231 resolveria isso, se as redes bloquearem NTP. Entre redes, a comunicação depende do serviço de túnel (conta Tailscale, retransmissão e limite de banda da Tailscale, nome público atrelado à conta): se o serviço cair, os nós guardam até cinco dias de leituras em flash e reenviam depois. Na alternativa HTTP da rede local não há criptografia, só o token. Se o servidor inteiro cair, os alertas do app avisam, com o atraso do WorkManager (15 minutos ou mais); um serviço externo de monitoramento de disponibilidade avisaria mais rápido. Dois processos gravam no banco: a API, nas tabelas de ingestão, e o job horário de previsão, só em `forecasts`, numa transação curta por hora. O SQLite em WAL serializa as gravações, e cada conexão espera até 10 s por uma trava; com mais escritores ou gravações longas, a escolha do SQLite teria de ser revista. O backup, o dashboard e os scripts de análise só leem.

## Avaliação de modelos de previsão

`server/scripts/train_forecast.py` compara, offline, a persistência, uma regressão Ridge, um gradient boosting de árvores (`HistGradientBoostingRegressor`) e uma rede neural MLP (`MLPRegressor`), todos do scikit-learn, na previsão da média horária de PM2,5 da hora seguinte, com validação progressiva (walk-forward) e teste final nos últimos dias. Lê o banco em modo somente leitura e não grava em `forecasts`.

```
pip install -r server/requirements-ml.txt
cd server
python -m scripts.train_forecast --out relatorio.json       # --no-mlp pula a MLP, a etapa mais demorada
```

Para a avaliação final, três opções registram o que é preciso para reproduzir e para o gráfico de previsto × observado:

```
python -m scripts.train_forecast --db ../resultados/pm25-congelado-<início>_<fim>.db \
    --out ../resultados/previsao.json --predictions-csv ../resultados/previsao_teste.csv --seeds 5
```

- **Reprodutibilidade:** o relatório traz `environment` (versões de Python, numpy, pandas e scikit-learn) e `database` (nome, tamanho e SHA-256 do arquivo lido). Use o banco congelado por `scripts.period_metrics --freeze`: no banco em uso, parte dos dados pode estar no arquivo `-wal` e o hash não identificaria o conjunto.
- **`--predictions-csv`:** grava as previsões do teste final, uma linha por hora e nó, com `hora` (hora-alvo prevista, em UTC), `no`, `observado`, `persistencia`, `ridge`, `gboost` e `mlp` (sem `mlp` com `--no-mlp`). As colunas reproduzem as métricas do relatório.
- **`--seeds N`** (padrão 1): repete o treino da MLP com as sementes `--seed`, `--seed + 1`, ... A semente de referência (42) continua sendo a do resultado principal e a do CSV. Com `N > 1`, a MLP ganha em `results` o bloco `seeds`, com os resultados de cada semente e a média e o desvio-padrão amostral do RMSE e do índice de habilidade, na validação e no teste.

A execução com dados reais só faz sentido com pelo menos cerca de 5 semanas de coleta, deixando os 7 últimos dias para o teste final. Os hiperparâmetros foram fixados antes de ver os dados e não devem ser alterados depois de olhar o teste final: MLP com 32 e 16 unidades, Adam com taxa 0,001, lote 32, até 200 épocas e paciência 15; Ridge com alpha 10; gradient boosting com os valores padrão do scikit-learn (taxa 0,1, 100 iterações, 31 folhas, 20 amostras por folha) e sem parada antecipada; semente 42.

A MLP é treinada época a época (`partial_fit`), com parada antecipada nos 15% finais do treino, em ordem cronológica, e os pesos da melhor época restaurados. O `early_stopping` do próprio `MLPRegressor` sorteia a validação e, numa série temporal, validaria com horas intercaladas às de treino. O gradient boosting dispensa a parada antecipada pelo mesmo motivo: a dele também sorteia a validação.

Os hiperparâmetros (`--hidden`, `--lr`, `--epochs`, `--seed` etc.) vão para o relatório em JSON.

## Previsão em produção

A avaliação offline escolhe o modelo; dois scripts o colocam no ar. Os três passam por `server/app/forecasting.py`, então o modelo em produção vê as mesmas variáveis e usa os mesmos hiperparâmetros fixos da avaliação.

```
pip install -r server/requirements-ml.txt
cd server
python -m scripts.fit_forecast --model ridge --version v0   # grava data/models/ridge-v0.joblib
python -m scripts.forecast_job                              # o que a tarefa horária executa
```

- **`fit_forecast.py`** treina o modelo (`ridge`, `gboost` ou `mlp`) com todas as horas completas do banco, sem os nós de teste, e grava `<modelo>-<versão>.joblib` em `PM25_MODELS_DIR` (padrão `data/models`). Exige pelo menos 100 horas completas. Uma versão nunca é sobrescrita: um modelo novo, ou o mesmo modelo treinado com mais dados, ganha outra versão, para que cada linha de `forecasts` aponte para um único modelo. O arquivo registra a versão do scikit-learn do treino e só carrega com ela; depois de atualizar o scikit-learn, treine uma versão nova. O arquivo é um pickle: só carregue modelos gerados no próprio servidor.
- **`forecast_job.py`** roda a cada hora, aos 5 minutos, para dar tempo de chegarem as últimas leituras da hora: tarefa `pm25-forecast` no Windows, linha do `crontab.example` no Linux, log em `data/forecast.log`. Para cada nó e cada modelo da pasta, usa as médias até a última hora completa e grava em `forecasts` a previsão da hora em andamento. Como a hora-alvo ainda não terminou, toda previsão antecede o valor observado (validação prospectiva). Um nó sem média válida na última hora, ou sem algum dos atrasos, fica sem previsão nessa hora, e uma hora perdida com o servidor desligado não é preenchida depois. Rodar de novo na mesma hora não duplica nada. O job termina com código 1 se nenhum modelo carregar ou se algum arquivo falhar (os outros modelos rodam assim mesmo), o que aparece no `LastTaskResult` da tarefa.
- **Onde aparece:** cada modelo vira uma série "<modelo> <versão>" (por exemplo, `ridge v0`) na aba Previsto × observado do dashboard, na rota `/forecast` e na tela de previsão do app, ao lado da persistência, com MAE, RMSE e skill score medidos nas horas já observadas. Nenhum dos três precisou mudar.
- **Trocar ou aposentar um modelo:** treine a versão nova e deixe as duas na pasta enquanto quiser compará-las lado a lado; para aposentar uma, tire o arquivo de `data/models`. As previsões já gravadas continuam no banco.

Antes das cerca de 5 semanas de coleta, dá para pôr o caminho todo no ar com um Ridge provisório (`--version v0`), treinado com o que houver: ele começa a acumular previsões prospectivas e não interfere na avaliação offline, porque não influencia nenhuma escolha de hiperparâmetro. O modelo do TCC sai da avaliação e entra como uma versão nova.

## Métricas do período

`server/scripts/period_metrics.py` consolida a coleta para a QP1 (completude, lacunas, reinícios) e para as estatísticas de PM2,5. Lê o banco em modo somente leitura e, com `--freeze`, congela o conjunto de dados usado.

```
cd server
python -m scripts.period_metrics --start 2026-10-01 --end 2026-11-15 --out-dir ../resultados --freeze
```

Precisa de `pandas` (já instalado com o dashboard). Por padrão analisa todos os nós, exceto os de teste (identificadores que começam com `teste`); `--devices no-01,no-02` escolhe os nós e `--db` aponta outro banco. Saídas em `--out-dir`:

| Arquivo | Conteúdo | Uso |
|---|---|---|
| `periodo.json` | Por nó: métricas operacionais, lacunas por origem, estatísticas de PM2,5 e excedências | Tabelas 21 e 22 |
| `completude_diaria.csv` | Leituras e completude por nó e por dia | Gráfico 1 |
| `perfil_hora.csv`, `perfil_dia_semana.csv` | Média de PM2,5 por hora do dia e por dia da semana (Brasília) | Gráfico 2 |

Definições. O período vai de `--start` 00:00 até o fim de `--end`, em horário de Brasília (UTC-3), e espera uma leitura por minuto. Completude é a fração dos minutos esperados com ao menos uma leitura recebida. A classificação das lacunas usa as definições do contrato de dados: entre duas leituras consecutivas, mudança de `boot_id` é **reinício**, salto de `seq` na mesma inicialização é **comunicação** (limitada aos minutos que faltam) e o restante é **aquisição**; o início e o fim do período sem leitura entram na completude e na maior lacuna como `bordas`, e `comunicacao + aquisicao + reinicio + bordas` soma os minutos faltantes. Mensagens perdidas são os saltos de `seq` na mesma inicialização; reinícios, as trocas de `boot_id`; duplicatas, a soma de `n_duplicates` dos lotes recebidos no período; RSSI, a média das leituras.

As estatísticas de PM2,5 usam médias horárias válidas, isto é, horas com pelo menos 45 leituras de qualidade `ok`: a regra e a função vêm de `app/analytics.py` (`MIN_READINGS_PER_HOUR` e `hourly_means`, usadas pelo `hourly_series` de `app/forecasting.py`), então o dashboard, a análise descritiva e a avaliação dos modelos usam as mesmas horas. O desvio-padrão é o amostral e os percentis usam interpolação linear. Uma média de 24 h (dia de calendário de Brasília) só conta com pelo menos 18 horas válidas, o mesmo 75% da hora.

Limiares de média de 24 h (µg/m³), conferidos nos textos oficiais: OMS 2021 (Tabela 0.1 das diretrizes globais), nível-guia 15 e metas intermediárias 25, 37,5, 50 e 75; Resolução CONAMA nº 506/2024 (Anexo I), PI-1 60, PI-2 50, PI-3 37, PI-4 25 e PF 15. Para dados de 2026 o padrão nacional em vigor é o PI-2 (desde 2025-01-01). Cada limiar tem nome e comentário com a fonte em `period_metrics.py`. Nem a OMS nem o CONAMA definem limite horário de PM2,5: a contagem de horas acima de cada valor é só uma referência, e a comparação normativa é a das médias de 24 h.

Com `--freeze`, o banco é copiado para `--out-dir` pela API de backup do SQLite (cópia íntegra mesmo com a API gravando), convertido para arquivo único e verificado com `integrity_check`. O `periodo.json` registra o intervalo, a data da extração (UTC), o número de medições e o SHA-256 da cópia, e as métricas são calculadas sobre a cópia, de modo que o hash identifica exatamente os dados analisados. Os dispositivos de teste (por exemplo `teste-https`) ficam gravados no banco e são excluídos das métricas por padrão.

## Comparação com a CETESB

`server/scripts/compare_cetesb.py` compara as médias horárias de PM2,5 de cada nó com as de uma estação da CETESB, usada como referência regulatória. Lê o banco em modo somente leitura e o CSV de MP2,5 (média horária) exportado do QUALAR; não grava no banco.

```
cd server
python -m scripts.compare_cetesb --cetesb ../resultados/cetesb_osasco.csv --db ../resultados/pm25-congelado-<início>_<fim>.db
```

Gera `comparacao_cetesb.json` (por nó: horas pareadas, viés, MAE, RMSE, correlação de Pearson e reta de regressão, no total e separando as horas com umidade acima de 75% e até 75%) e `comparacao_cetesb_pares.csv` (colunas `hora_utc`, `device_id`, `pm25_no`, `pm25_cetesb` e `umidade`; uma linha por hora pareada, base do gráfico de dispersão). Só entram horas válidas nos dois lados: a hora do nó segue a mesma regra de 45 leituras da avaliação dos modelos, e os valores vazios da CETESB ficam de fora. O viés é a média de nó menos CETESB, e a regressão é a do nó em função da CETESB. Horas pareadas sem umidade no nó entram no total e são contadas em `sem_umidade`, fora das duas faixas, de modo que alta + baixa + sem umidade = total. Com `--start` e `--end` (dias de Brasília) o período fica restrito; sem eles, vale o período do arquivo.

O CSV pode estar em Latin-1 (como sai do QUALAR) ou UTF-8, com `;` como separador e vírgula decimal. A estação e o código vêm do cabeçalho (`Nome da estação`, `Código da estação`). Uma linha de dados com valor não numérico, hora fora de `HH:00`, data inválida, hora repetida ou mais de uma coluna de valores interrompe o script com a linha do problema e código de saída 2 (arquivo ou banco ausente: código 1).

O rótulo `HH:00` da CETESB é tratado como o fim da hora (`01:00` cobre 00:00 a 01:00, e `24:00` fecha o dia), no horário de Brasília. Isso é uma suposição, ainda não confirmada na documentação oficial: os arquivos LEIA-ME do QUALAR estavam inacessíveis na consulta. A favor dela há a documentação do pacote [qualR](https://docs.ropensci.org/qualR/) (rOpenSci), que descreve a média horária do QUALAR como a média até a hora do rótulo e a meia-noite como `24:00`, e o próprio arquivo exportado, que vai de `01:00` a `24:00` sem `00:00`. Se a CETESB indicar outra convenção, use `--hour-label start`; um rótulo errado desloca todo o pareamento em uma hora e piora as métricas, então rodar as duas opções e comparar `r` e RMSE também ajuda a conferir. Os valores da CETESB são inteiros, e a distância entre o nó e a estação não é corrigida: a comparação mede a concordância entre os dois pontos, não o erro absoluto do sensor. Com menos de 24 horas pareadas, ou com uma das séries constante, a correlação e a regressão não são calculadas e o JSON traz um `aviso`.

O arquivo da CETESB precisa cobrir as mesmas datas da coleta do nó: horas fora da interseção simplesmente não pareiam.

## Padrão de commits

As mensagens seguem Conventional Commits (`tipo(escopo): descrição`, no imperativo, até 72 caracteres no cabeçalho). O hook `commit-msg` em `.githooks/` recusa mensagens fora do formato e as que têm termos proibidos, como rodapés de coautoria; a lista está em `.githooks/check-commit.sh`. Ative uma vez em cada clone:

```bash
git config core.hooksPath .githooks
```

O hook pode ser pulado localmente, então o workflow `commit-standards` repete a checagem em cada PR e em cada envio para a `main`, conferindo também o autor e o committer de cada commit e o título do PR, que vira a mensagem num squash merge.

## Próximos passos

O pipeline de modelagem começa com os dados públicos da CETESB (QUALAR) e do INMET ou Open-Meteo, com baseline de persistência e validação walk-forward, e depois roda sobre este banco. O job horário já grava previsões na tabela `forecasts` para a validação prospectiva; falta o modelo escolhido com os dados reais. Com a coleta contínua em andamento, também fica possível simular ciclos de leitura do PMS5003 a partir dos dados de um minuto, para o estudo de consumo de energia.
