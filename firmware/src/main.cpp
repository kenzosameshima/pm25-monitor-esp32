// Firmware do nó sensor de PM2,5: ESP32 + PMS5003 + BME280 ou DHT22.
//
// A cada minuto de relógio (UTC), fecha a média dos quadros do PMS5003, lê temperatura e umidade
// e envia a leitura à API por HTTP POST (HTTPS, com validação do certificado, quando a API_URL
// começa com https://). O que não for confirmado (HTTP 201) vai para um buffer em LittleFS, que
// sobrevive a reinícios, e é reenviado em lotes quando a rede volta.
//
// Identificação de cada leitura: (DEVICE_ID, boot_id, seq). O boot_id é um contador gravado na
// NVS e incrementado a cada inicialização; o seq recomeça do zero a cada boot. Assim, reenvios
// são descartados pela API sem risco de uma leitura nova colidir com uma antiga após um reinício.
#include <Arduino.h>
#include <HTTPClient.h>
#include <LittleFS.h>
#include <Preferences.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <esp_task_wdt.h>
#include <esp_timer.h>
#include <time.h>

#if __has_include("config.h")
#include "config.h"
#else
#error "Copie src/config.example.h para src/config.h e preencha os valores"
#endif

#include "pms5003.h"
#include "reading.h"

#if defined(TH_SENSOR_BME280) && defined(TH_SENSOR_DHT22)
#error "Escolha apenas um sensor de temperatura e umidade em config.h"
#elif defined(TH_SENSOR_BME280)
#include <Adafruit_BME280.h>
#include <Wire.h>
Adafruit_BME280 bme;
bool bmeOk = false;
#elif defined(TH_SENSOR_DHT22)
#include <DHT.h>
DHT dht(DHT_PIN, DHT22);
#else
#error "Defina TH_SENSOR_BME280 ou TH_SENSOR_DHT22 em config.h"
#endif

// ---------------- Parâmetros ----------------
static const uint32_t PMS_WARMUP_MS = 30000;        // ventoinha estabilizando após ligar
static const uint16_t MIN_SAMPLES_PER_MINUTE = 10;  // minutos com menos quadros válidos são descartados
static const time_t MIN_VALID_EPOCH = 1767225600;   // 2026-01-01T00:00:00Z: antes disso, relógio não sincronizado
static const size_t BATCH_SIZE = 60;                // leituras por requisição ao esvaziar o buffer
static const int MAX_BATCHES_PER_LOOP = 3;
static const uint32_t MAX_PENDING_RECORDS = 5UL * 24 * 60;  // 5 dias de leituras em buffer (~317 KB)
static const uint32_t HTTP_TIMEOUT_MS = 8000;
// HTTPS: a conexão TCP e o handshake TLS levam bem mais que um POST simples. No pior caso uma tentativa
// gasta 15 s (conexão) + 20 s (handshake) + 8 s (envio e resposta) = 43 s, abaixo do watchdog de 90 s.
// O padrão da biblioteca para o handshake é 120 s, o que estouraria o watchdog.
static const uint32_t HTTPS_CONNECT_TIMEOUT_MS = 15000;
static const unsigned long HTTPS_HANDSHAKE_TIMEOUT_S = 20;
static const uint32_t FIRST_BACKOFF_MS = 5000;
static const uint32_t MAX_BACKOFF_MS = 5UL * 60 * 1000;
static const uint32_t WIFI_RETRY_MS = 30000;
static const uint32_t WIFI_REBOOT_AFTER_MS = 15UL * 60 * 1000;  // o buffer em flash sobrevive ao reinício
static const uint32_t WDT_TIMEOUT_S = 90;

// Se a estrutura Reading mudar, troque os nomes (o static_assert em reading.h avisa).
static const char* PENDING_FILE = "/pending_v1.bin";
static const char* OFFSET_FILE = "/pending_v1.off";
static const char* TMP_FILE = "/pending_v1.tmp";

// A API_URL https:// exige a CA raiz (API_ROOT_CA) ou, só em bancada, API_TLS_INSECURE_TEST.
constexpr bool urlIsHttps(const char* url) {
  return url[0] == 'h' && url[1] == 't' && url[2] == 't' && url[3] == 'p' && url[4] == 's' && url[5] == ':';
}
constexpr bool API_IS_HTTPS = urlIsHttps(API_URL);
#if defined(API_ROOT_CA) || defined(API_TLS_INSECURE_TEST)
constexpr bool API_TLS_CONFIGURED = true;
#else
constexpr bool API_TLS_CONFIGURED = false;
#endif
static_assert(!API_IS_HTTPS || API_TLS_CONFIGURED,
              "API_URL com https:// precisa de API_ROOT_CA em config.h (ver config.example.h)");

// ---------------- Estado ----------------
HardwareSerial& pmsSerial = Serial2;
PmsParser parser;
MinuteAccumulator acc;
uint32_t bootId = 0;
uint32_t seqCounter = 0;
int64_t currentMinute = -1;
uint32_t pendingSize = 0;    // bytes no arquivo de pendências
uint32_t pendingOffset = 0;  // bytes já confirmados pela API
uint32_t nextFlushAt = 0;
uint32_t backoffMs = 0;
uint32_t wifiDownSince = 0;
uint32_t lastWifiRetry = 0;
uint32_t lastNtpWarning = 0;
uint32_t sentOk = 0, droppedByServer = 0, droppedOverflow = 0;

// ---------------- Utilidades ----------------
static bool timeValid() { return time(nullptr) >= MIN_VALID_EPOCH; }
static uint32_t uptimeSeconds() { return (uint32_t)(esp_timer_get_time() / 1000000ULL); }
static uint32_t pendingRecords() { return (pendingSize - pendingOffset) / sizeof(Reading); }
static bool isSuccess(int code) { return code == 200 || code == 201; }

// Sem hora válida o handshake falha (o certificado ainda "não começou" para o relógio do ESP32).
// Em vez de acumular falhas e aumentar a espera, o envio só começa depois do NTP.
static bool clockReadyForSend() { return !API_IS_HTTPS || timeValid(); }

// 4xx que não se resolvem reenviando: o lote é descartado (a API guarda uma cópia para auditoria).
// 401/403 indicam token ou DEVICE_ID errado: os dados ficam no buffer até a configuração ser corrigida.
// 429: a API bloqueou o IP por tentativas inválidas. Falha de conexão ou de handshake TLS (código
// negativo) também não é rejeição: o lote continua no buffer e é reenviado com espera crescente.
static bool isRejected(int code) {
  return code >= 400 && code < 500 && code != 401 && code != 403 && code != 408 && code != 429;
}

static void scheduleRetry() {
  backoffMs = backoffMs == 0 ? FIRST_BACKOFF_MS : (backoffMs * 2 > MAX_BACKOFF_MS ? MAX_BACKOFF_MS : backoffMs * 2);
  nextFlushAt = millis() + backoffMs;
}

static void setupWatchdog() {
#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
  esp_task_wdt_config_t cfg = {};
  cfg.timeout_ms = WDT_TIMEOUT_S * 1000;
  cfg.idle_core_mask = 0;
  cfg.trigger_panic = true;
  if (esp_task_wdt_reconfigure(&cfg) != ESP_OK) esp_task_wdt_init(&cfg);
#else
  esp_task_wdt_init(WDT_TIMEOUT_S, true);
#endif
  esp_task_wdt_add(NULL);
}

// ---------------- Temperatura e umidade ----------------
static void initTemperatureHumidity() {
#if defined(TH_SENSOR_BME280)
  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
  bmeOk = bme.begin(BME280_ADDR, &Wire);
  if (!bmeOk) Serial.println("[bme280] não encontrado: confira a fiação e o endereço (0x76/0x77)");
#else
  dht.begin();
#endif
}

static void readTemperatureHumidity(float& t, float& h) {
#if defined(TH_SENSOR_BME280)
  if (!bmeOk) bmeOk = bme.begin(BME280_ADDR, &Wire);
  t = bmeOk ? bme.readTemperature() : NAN;
  h = bmeOk ? bme.readHumidity() : NAN;
#else
  t = dht.readTemperature();  // NAN em caso de falha
  h = dht.readHumidity();
#endif
}

// ---------------- Buffer persistente (LittleFS) ----------------
// Arquivo só de acréscimo + deslocamento das leituras já confirmadas. Se a energia cair entre o 201
// e a gravação do deslocamento, o lote é reenviado e a API descarta as duplicatas.
static void writeOffset() {
  File f = LittleFS.open(OFFSET_FILE, FILE_WRITE);
  if (f) {
    f.write((const uint8_t*)&pendingOffset, sizeof pendingOffset);
    f.close();
  }
}

static void clearPending() {
  LittleFS.remove(PENDING_FILE);
  LittleFS.remove(OFFSET_FILE);
  pendingSize = pendingOffset = 0;
}

// Reescreve o arquivo só com as leituras pendentes (no máximo `keep`, as mais recentes).
static void compactPending(uint32_t keep) {
  File in = LittleFS.open(PENDING_FILE, FILE_READ);
  if (!in) {
    clearPending();
    return;
  }
  uint32_t avail = pendingRecords();
  uint32_t skip = avail > keep ? avail - keep : 0;
  in.seek(pendingOffset + skip * sizeof(Reading));
  File out = LittleFS.open(TMP_FILE, FILE_WRITE);
  if (!out) {
    in.close();
    return;
  }
  Reading r;
  uint32_t kept = 0;
  while (in.read((uint8_t*)&r, sizeof r) == sizeof r) {
    out.write((const uint8_t*)&r, sizeof r);
    if (++kept % 256 == 0) esp_task_wdt_reset();
  }
  in.close();
  out.close();
  LittleFS.remove(PENDING_FILE);
  LittleFS.rename(TMP_FILE, PENDING_FILE);
  LittleFS.remove(OFFSET_FILE);
  pendingOffset = 0;
  pendingSize = kept * sizeof(Reading);
  droppedOverflow += skip;
  Serial.printf("[buffer] compactado: %lu leituras pendentes\n", (unsigned long)kept);
}

static void loadPending() {
  pendingSize = pendingOffset = 0;
  if (!LittleFS.exists(PENDING_FILE)) {
    LittleFS.remove(OFFSET_FILE);
    return;
  }
  File f = LittleFS.open(PENDING_FILE, FILE_READ);
  if (f) {
    pendingSize = f.size();
    f.close();
  }
  File o = LittleFS.open(OFFSET_FILE, FILE_READ);
  if (o) {
    if (o.read((uint8_t*)&pendingOffset, sizeof pendingOffset) != sizeof pendingOffset) pendingOffset = 0;
    o.close();
  }
  if (pendingOffset > pendingSize || pendingOffset % sizeof(Reading) != 0) pendingOffset = 0;
  // Gravação interrompida por queda de energia deixa um registro incompleto no fim: realinha.
  if ((pendingSize - pendingOffset) % sizeof(Reading) != 0) compactPending(MAX_PENDING_RECORDS);
  if (pendingRecords() == 0) clearPending();
}

static void appendPending(const Reading& r) {
  if (pendingRecords() >= MAX_PENDING_RECORDS) {  // buffer cheio: descarta a leitura mais antiga
    pendingOffset += sizeof(Reading);
    droppedOverflow++;
    writeOffset();
  }
  if (pendingSize >= 3 * MAX_PENDING_RECORDS * sizeof(Reading) / 2) compactPending(MAX_PENDING_RECORDS);
  File f = LittleFS.open(PENDING_FILE, FILE_APPEND);
  if (!f) {
    Serial.println("[buffer] falha ao gravar na flash: leitura perdida");
    return;
  }
  size_t written = f.write((const uint8_t*)&r, sizeof r);
  f.close();
  pendingSize += written;
  if (written != sizeof r) compactPending(MAX_PENDING_RECORDS);
}

static size_t readPendingBatch(Reading* out, size_t max) {
  File f = LittleFS.open(PENDING_FILE, FILE_READ);
  if (!f) return 0;
  f.seek(pendingOffset);
  size_t n = 0;
  while (n < max && f.read((uint8_t*)&out[n], sizeof(Reading)) == sizeof(Reading)) n++;
  f.close();
  return n;
}

static void confirmPending(size_t n) {
  pendingOffset += n * sizeof(Reading);
  if (pendingOffset >= pendingSize) {
    clearPending();
  } else {
    writeOffset();
  }
}

// ---------------- Envio ----------------
static int postReadings(const Reading* rs, size_t n) {
  if (WiFi.status() != WL_CONNECTED || !clockReadyForSend()) return -1;
  std::string body = buildPayload(DEVICE_ID, rs, n);
  static WiFiClient plainClient;
  static WiFiClientSecure secureClient;
  HTTPClient http;
  bool began;
  if (API_IS_HTTPS) {
#if defined(API_ROOT_CA)
    secureClient.setCACert(API_ROOT_CA);
#else
    secureClient.setInsecure();  // API_TLS_INSECURE_TEST: cifra, mas não autentica o servidor
#endif
    secureClient.setHandshakeTimeout(HTTPS_HANDSHAKE_TIMEOUT_S);
    began = http.begin(secureClient, API_URL);
  } else {
    began = http.begin(plainClient, API_URL);
  }
  if (!began) return -1;
  http.setConnectTimeout(API_IS_HTTPS ? HTTPS_CONNECT_TIMEOUT_MS : HTTP_TIMEOUT_MS);
  http.setTimeout(HTTP_TIMEOUT_MS);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("Authorization", "Bearer " DEVICE_TOKEN);
  int code = http.POST((uint8_t*)body.data(), body.size());
  if (!isSuccess(code)) {
    String detail = code > 0 ? http.getString() : HTTPClient::errorToString(code);
    Serial.printf("[http] %d %s\n", code, detail.c_str());
    if (API_IS_HTTPS && code < 0) {  // falha de conexão ou de handshake: trata como falha de rede
      char tlsError[100] = "";
      int tlsCode = secureClient.lastError(tlsError, sizeof tlsError);
      Serial.printf("[tls] erro %d: %s (heap livre %lu)\n", tlsCode, tlsError,
                    (unsigned long)ESP.getFreeHeap());
    }
  }
  http.end();
  return code;
}

static void enqueue(const Reading& r) {
  if (pendingRecords() == 0 && WiFi.status() == WL_CONNECTED && (int32_t)(millis() - nextFlushAt) >= 0) {
    int code = postReadings(&r, 1);
    if (isSuccess(code)) {
      sentOk++;
      backoffMs = 0;
      return;
    }
    if (isRejected(code)) {
      droppedByServer++;
      return;
    }
    scheduleRetry();
  }
  appendPending(r);
}

static void flushPending() {
  if (pendingRecords() == 0 || WiFi.status() != WL_CONNECTED) return;
  if ((int32_t)(millis() - nextFlushAt) < 0 || !clockReadyForSend()) return;
  static Reading batch[BATCH_SIZE];
  for (int i = 0; i < MAX_BATCHES_PER_LOOP && pendingRecords() > 0; ++i) {
    esp_task_wdt_reset();
    size_t n = readPendingBatch(batch, BATCH_SIZE);
    if (n == 0) {
      Serial.println("[buffer] arquivo ilegível: descartando pendências");
      clearPending();
      return;
    }
    int code = postReadings(batch, n);
    if (isSuccess(code)) {
      sentOk += n;
      backoffMs = 0;
      confirmPending(n);
      Serial.printf("[buffer] lote de %u enviado; restam %lu\n", (unsigned)n, (unsigned long)pendingRecords());
    } else if (isRejected(code)) {
      droppedByServer += n;
      confirmPending(n);
    } else {
      scheduleRetry();
      return;
    }
  }
}

// ---------------- Medição ----------------
static void readPms() {
  PmsFrame f;
  while (pmsSerial.available() > 0) {
    if (parser.feed((uint8_t)pmsSerial.read(), f) && millis() >= PMS_WARMUP_MS && timeValid()) acc.add(f);
  }
}

static void closeMinute(int64_t minute) {
  if (acc.n < MIN_SAMPLES_PER_MINUTE) {
    Serial.printf("[pms] minuto com %u quadros válidos (mínimo %u): descartado\n", (unsigned)acc.n,
                  (unsigned)MIN_SAMPLES_PER_MINUTE);
    acc.reset();
    return;
  }
  Reading r;
  memset(&r, 0, sizeof r);
  r.boot_id = bootId;
  r.seq = seqCounter++;
  r.ts = (uint32_t)(minute * 60);
  r.uptime_s = uptimeSeconds();
  r.pm1 = acc.mean(acc.pm1);
  r.pm25 = acc.mean(acc.pm25);
  r.pm10 = acc.mean(acc.pm10);
  r.pm25_cf1 = acc.mean(acc.pm25_cf1);
  readTemperatureHumidity(r.temperature, r.humidity);
  r.rssi = WiFi.status() == WL_CONNECTED ? (int16_t)WiFi.RSSI() : RSSI_NONE;
  r.samples = acc.n;
  acc.reset();
  Serial.printf("[leitura] seq=%lu pm2.5=%.1f quadros=%u T=%.1f UR=%.1f rssi=%d pendentes=%lu\n",
                (unsigned long)r.seq, r.pm25, (unsigned)r.samples, r.temperature, r.humidity, (int)r.rssi,
                (unsigned long)pendingRecords());
  enqueue(r);
}

static void handleClock() {
  if (!timeValid()) {
    if (millis() - lastNtpWarning > 60000) {
      Serial.println("[ntp] aguardando sincronização do relógio (leituras ainda não são registradas)");
      lastNtpWarning = millis();
    }
    return;
  }
  int64_t minute = (int64_t)time(nullptr) / 60;
  if (currentMinute < 0) {  // primeiro minuto após sincronizar é incompleto: começa do próximo
    currentMinute = minute;
    acc.reset();
    return;
  }
  if (minute != currentMinute) {
    closeMinute(currentMinute);
    currentMinute = minute;
  }
}

// ---------------- Wi-Fi ----------------
static void beginWifi() {
#ifdef WIFI_CHANNEL
  WiFi.begin(WIFI_SSID, WIFI_PASS, WIFI_CHANNEL);  // canal fixo agiliza a conexão (útil no Wokwi)
#else
  WiFi.begin(WIFI_SSID, WIFI_PASS);
#endif
}

static void handleWifi() {
  if (WiFi.status() == WL_CONNECTED) {
    if (wifiDownSince != 0) {
      Serial.printf("[wifi] reconectado, RSSI %d dBm\n", (int)WiFi.RSSI());
      wifiDownSince = 0;
    }
    return;
  }
  uint32_t now = millis();
  if (wifiDownSince == 0) {
    wifiDownSince = now;
    lastWifiRetry = now;
    Serial.println("[wifi] desconectado");
  }
  if (now - lastWifiRetry > WIFI_RETRY_MS) {
    WiFi.disconnect();
    beginWifi();
    lastWifiRetry = now;
  }
  if (now - wifiDownSince > WIFI_REBOOT_AFTER_MS) {
    Serial.println("[wifi] sem conexão há 15 min: reiniciando (o buffer em flash é preservado)");
    delay(200);
    ESP.restart();
  }
}

// ---------------- Arduino ----------------
void setup() {
  Serial.begin(115200);
  delay(200);
  setupWatchdog();

  Preferences prefs;
  prefs.begin("pm25", false);
  bootId = prefs.getULong("boot_id", 0) + 1;
  prefs.putULong("boot_id", bootId);
  prefs.end();

  if (LittleFS.begin(true)) {
    loadPending();
  } else {
    Serial.println("[fs] falha ao montar LittleFS: leituras não enviadas serão perdidas");
  }

  pmsSerial.setRxBufferSize(1024);
  pmsSerial.begin(9600, SERIAL_8N1, PMS_RX_PIN, PMS_TX_PIN);
  initTemperatureHumidity();

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  beginWifi();
  configTime(0, 0, NTP_SERVER_1, NTP_SERVER_2);  // relógio em UTC; o SNTP ressincroniza periodicamente

  Serial.printf("[boot] %s boot_id=%lu pendentes=%lu\n", DEVICE_ID, (unsigned long)bootId,
                (unsigned long)pendingRecords());
}

void loop() {
  esp_task_wdt_reset();
  readPms();
  handleClock();
  handleWifi();
  flushPending();
  delay(5);
}
