# Sistema de coleta de PM2,5 — TCC (UNIP, 2026)

Este repositório reúne a cadeia de coleta e o painel do projeto: o firmware dos nós sensores (ESP32 + PMS5003 + BME280 ou DHT22), a API de ingestão, o banco SQLite, o backup diário, o alerta no Telegram, o dashboard em Streamlit, um simulador de sensor e os chips simulados do Wokwi, para testar tudo sem hardware. O pipeline de modelagem e o job horário de previsão são as próximas etapas e vão ler e gravar no mesmo banco.

```
nó ESP32 ──HTTP POST (JSON) via Wi-Fi──▶ API FastAPI ──▶ SQLite (WAL) ──▶ backup diário
   │ buffer em flash se a rede cair                           ├──▶ alerta Telegram (sensor mudo 15 min)
                                                              └──▶ dashboard Streamlit (somente leitura)
```

## Estrutura

```
firmware/     código do ESP32 (PlatformIO); host_tests/ testa a parte sem hardware no computador
server/app/   API (main.py), contrato de dados (models.py), acesso ao banco (db.py), esquema (schema.sql)
server/scripts/  backup.py, alert_telegram.py, simulate_sensor.py
server/tests/    testes da API, incluindo o JSON gerado pelo próprio firmware
server/dashboard/  dashboard em Streamlit (status, séries, previsto × observado)
server/deploy/   serviços systemd (API e dashboard) e exemplo de crontab
wokwi/        chips simulados do PMS5003 e do BME280, config.h e bibliotecas para rodar o firmware no Wokwi
```

## Início rápido, sem hardware

No computador (Linux, macOS ou Windows), com Python 3.10 ou mais recente:

```bash
cd server
python -m venv .venv
source .venv/bin/activate            # no Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env                 # troque os tokens (ver comentário no arquivo)
pytest                               # 18 testes (API e dashboard)
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
| 401 ou 403 | Token ausente, inválido ou de outro nó | Mantém o lote e tenta de novo (erro de configuração) |
| 422 | Fora do contrato; cópia guardada em `invalid_messages` | Descarta o lote, para não reenviar o mesmo erro para sempre |
| Falha de rede ou 5xx | Nada foi gravado | Mantém o lote e tenta de novo com espera crescente |

Cada leitura é identificada por `(device_id, boot_id, seq)`. O `boot_id` é um contador gravado na memória não volátil do ESP32 e incrementado a cada inicialização; o `seq` recomeça do zero a cada boot. A API ignora leituras repetidas, então reenviar um lote é sempre seguro, e um reinício nunca faz uma leitura nova colidir com uma antiga. Isso também separa os tipos de falha: um salto de `seq` dentro do mesmo `boot_id` é perda de mensagem, um intervalo de tempo sem salto de `seq` é minuto sem leitura válida do sensor, e um `boot_id` novo é um reinício.

## Banco de dados

O arquivo único do SQLite opera em modo WAL, que deixa o dashboard ler enquanto a API grava, e com `synchronous=FULL`, para que o 201 só saia depois de a leitura estar no disco. A tabela `measurements` é imutável: gatilhos impedem `UPDATE` e `DELETE`, e toda limpeza ou agregação vai para tabelas derivadas. Na ingestão só se marcam valores fisicamente implausíveis na coluna `quality`; critérios que podem mudar depois, como a marcação de umidade alta, ficam no processamento em batch. A tabela `ingest_batches` registra cada requisição aceita, e a `forecasts` já está pronta para o job horário.

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

O dashboard lê o banco em modo somente leitura e tem três abas. Status mostra, para cada nó, a última leitura, há quanto tempo chegou o último envio e uma tabela de saúde da coleta nas últimas 24 horas: completude, maior lacuna, mensagens perdidas, reinícios, duplicatas descartadas e leituras marcadas; a aba se atualiza sozinha a cada minuto. Séries mostra PM2,5, PM10, PM1,0, temperatura e umidade por período, em médias horárias (só horas com pelo menos 45 minutos de leitura) ou minuto a minuto, com a linha de 75% de umidade e a parcela de registros acima dela, e exporta os dados em CSV. Previsto × observado compara as últimas 48 horas com a previsão de persistência, calculada na hora, e com as previsões que o job horário gravar na tabela `forecasts`, com MAE, RMSE e skill score. As linhas são interrompidas onde faltam dados, em vez de ligar pontos distantes. Os horários aparecem no fuso de Brasília; no banco, tudo continua em UTC.

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

Depois de ligado, o nó descarta os primeiros 30 segundos do PMS5003 (tempo de estabilização da ventoinha), espera o relógio sincronizar por NTP e passa a fechar uma leitura a cada minuto de relógio. O monitor serial mostra uma linha por minuto, por exemplo `[leitura] seq=41 pm2.5=13.2 quadros=58 T=23.9 UR=62.4 rssi=-64 pendentes=0`. O que a API não confirmar vai para um buffer em LittleFS com capacidade para cinco dias, que sobrevive a reinícios e quedas de energia. Se o Wi-Fi ficar 15 minutos fora, o ESP32 reinicia sozinho, e um watchdog de 90 segundos cobre travamentos.

O firmware foi compilado sem avisos (`--warnings all`) com os cores Arduino do ESP32 2.0.17 e 3.3.12, nas variantes BME280 e DHT22. A leitura dos quadros do sensor, a média do minuto e a montagem do JSON têm testes que rodam no computador:

```bash
cd firmware/host_tests
g++ -std=c++17 -Wall -I../src test_core.cpp -o test_core && ./test_core
```

O teste gera `payload_exemplo.json`, e o teste da API `test_contrato_payload_gerado_pelo_firmware_e_aceito` confere que a API aceita exatamente esse JSON. Nada disso substitui o teste com o hardware real, que ainda precisa ser feito.

## Simulação no Wokwi

Os chips simulados em `wokwi/` substituem os `.chip.c` do projeto no Wokwi e mantêm os mesmos controles (pm1, pm25 e pm10; temp, press e hum). As versões anteriores tinham dois problemas. O chip do PMS5003 só preenchia os campos CF=1 do quadro e deixava zerados os campos "atmospheric environment", que o firmware usa como PM2,5; com ele, o firmware novo leria sempre zero. O chip do BME280 convertia para os registradores com aproximações lineares: a temperatura saía certa, mas a pressão errava dezenas de hPa e a umidade só batia perto de 50% (20% virava 0% e 80% virava 100%), justamente a faixa que importa para a análise de umidade alta. O chip novo aplica as fórmulas de compensação da biblioteca Adafruit e procura o valor de registrador que reproduz cada controle. Testado fora do Wokwi, com um stub da API, o erro ficou abaixo de 0,01 °C, 0,01 hPa e 0,01% de umidade entre −10 e 45 °C, 900 e 1050 hPa e 0 e 100%, e os quadros do PMS5003 simulado passam no parser do firmware sem erro de checksum.

Para rodar o firmware no Wokwi, coloque no projeto `main.cpp`, `pms5003.h`, `reading.h`, um `sketch.ino` vazio e `wokwi/config.wokwi.h` renomeado para `config.h`, e use as bibliotecas de `wokwi/libraries.txt`. A ligação é a mesma do esboço anterior: PMS5003 na UART2 (GPIO16 e 17) e BME280 em 0x76 (GPIO21 e 22). A rede simulada é sempre `Wokwi-GUEST`, sem senha, no canal 6. Para o ESP32 simulado alcançar a API no seu computador é preciso o gateway privado do Wokwi (incluído no Wokwi for VS Code; no navegador, exige a assinatura Wokwi Club), e a URL passa a ser `http://host.wokwi.internal:8000/v1/measurements`. Sem o gateway, o simulador só alcança a internet: exponha a API local por um túnel (ngrok ou cloudflared) e use a URL `https` gerada.

Dá para exercitar no simulador os cenários que importam no campo. Suba a umidade acima de 75% e veja a marcação no dashboard. Pare a API por alguns minutos e religue: o nó guarda as leituras em flash e as reenvia num lote, e a tabela de saúde não deve registrar perdas. Reinicie o ESP32 simulado: o `boot_id` muda e as leituras seguem sem colisão.

## Implantação no servidor sempre ligado

Em um servidor Windows (notebook ou PC dedicado), use os scripts de `server/deploy/windows/` (veja o `README.md` dessa pasta), que fazem o papel dos serviços `systemd` e do crontab descritos abaixo.

O servidor precisa ficar ligado durante toda a coleta, com IP fixo na rede: reserve o IP do Raspberry Pi (ou PC) no roteador e use esse endereço em `API_URL`. Instale o projeto em `/home/pi/pm25-iot`, crie o ambiente virtual e o `.env` como no início rápido (com `requirements-dashboard.txt`; no Raspberry Pi, use o sistema de 64 bits) e ative os serviços e as tarefas agendadas:

```bash
sudo cp server/deploy/pm25-api.service /etc/systemd/system/
sudo cp server/deploy/pm25-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now pm25-api pm25-dashboard
crontab -e     # cole o conteúdo de server/deploy/crontab.example
curl http://<ip-do-servidor>:8000/health   # de outro computador da rede
```

Aponte `PM25_BACKUP_DIR` para um pendrive ou uma pasta sincronizada com a nuvem: um backup no mesmo cartão SD não protege contra falha do cartão, o risco mais comum em Raspberry Pi ligado por meses. Para o alerta, crie um bot com o @BotFather no Telegram, mande uma mensagem a ele e descubra o `chat_id` em `https://api.telegram.org/bot<token>/getUpdates`. Sem essas variáveis, `alert_telegram.py` só imprime as mensagens, o que serve para testar.

Antes de instalar cada nó, meça o RSSI no ponto exato de instalação (o log mostra o valor a cada minuto), confirme que a rede permite NTP (porta UDP 123) e deixe os dois sensores lado a lado nos primeiros 3 a 7 dias, para medir a concordância entre eles.

## Limitações conhecidas

Leituras anteriores à primeira sincronização NTP após um boot são descartadas, porque não teriam horário confiável; um módulo de relógio DS3231 resolveria isso, se as redes bloquearem NTP. Na rede local a comunicação é HTTP sem criptografia, protegida apenas pelo token; para expor a API na internet, use HTTPS e defina `API_ROOT_CA` no firmware. O alerta roda no próprio servidor, então não avisa se o servidor inteiro cair; um serviço externo de monitoramento de disponibilidade cobriria esse caso. O banco pressupõe um único processo escritor (a API), coerente com a decisão de usar SQLite; o alerta e o backup só leem.

## Avaliação de modelos de previsão

`server/scripts/train_forecast.py` compara, offline, a persistência, uma regressão Ridge e uma rede neural MLP em Keras na previsão da média horária de PM2,5 da hora seguinte, com validação progressiva (walk-forward) e teste final nos últimos dias. Lê o banco em modo somente leitura e não grava em `forecasts`.

```
pip install -r server/requirements-ml.txt
cd server
python -m scripts.train_forecast --out relatorio.json       # --no-mlp avalia só persistência e Ridge
```

Os hiperparâmetros (`--hidden`, `--lr`, `--epochs`, `--seed` etc.) vão para o relatório em JSON.

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

As estatísticas de PM2,5 usam médias horárias válidas, isto é, horas com pelo menos 45 leituras de qualidade `ok`: a regra e a função vêm de `train_forecast.py` (`MIN_SAMPLES` e `hourly_series`), então a análise descritiva e a avaliação dos modelos usam as mesmas horas. O desvio-padrão é o amostral e os percentis usam interpolação linear. Uma média de 24 h (dia de calendário de Brasília) só conta com pelo menos 18 horas válidas, o mesmo 75% da hora.

Limiares de média de 24 h (µg/m³), conferidos nos textos oficiais: OMS 2021 (Tabela 0.1 das diretrizes globais), nível-guia 15 e metas intermediárias 25, 37,5, 50 e 75; Resolução CONAMA nº 506/2024 (Anexo I), PI-1 60, PI-2 50, PI-3 37, PI-4 25 e PF 15. Para dados de 2026 o padrão nacional em vigor é o PI-2 (desde 2025-01-01). Cada limiar tem nome e comentário com a fonte em `period_metrics.py`. Nem a OMS nem o CONAMA definem limite horário de PM2,5: a contagem de horas acima de cada valor é só uma referência, e a comparação normativa é a das médias de 24 h.

Com `--freeze`, o banco é copiado para `--out-dir` pela API de backup do SQLite (cópia íntegra mesmo com a API gravando), convertido para arquivo único e verificado com `integrity_check`. O `periodo.json` registra o intervalo, a data da extração (UTC), o número de medições e o SHA-256 da cópia, e as métricas são calculadas sobre a cópia, de modo que o hash identifica exatamente os dados analisados. Os dispositivos de teste (por exemplo `teste-https`) ficam gravados no banco e são excluídos das métricas por padrão.

## Próximos passos

O pipeline de modelagem começa com os dados públicos da CETESB (QUALAR) e do INMET ou Open-Meteo, com baseline de persistência e validação walk-forward, e depois roda sobre este banco. O job horário grava previsões na tabela `forecasts` para a validação prospectiva. Com a coleta contínua em andamento, também fica possível simular ciclos de leitura do PMS5003 a partir dos dados de um minuto, para o estudo de consumo de energia.
