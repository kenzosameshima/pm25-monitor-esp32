// Copie este arquivo para config.h (que não deve ser versionado) e ajuste os valores.
#pragma once

// ---- Rede ----
#define WIFI_SSID "nome-da-rede"
#define WIFI_PASS "senha-da-rede"

// ---- API ----
// Use o IP reservado do servidor na rede local. Para HTTPS, defina API_ROOT_CA com o certificado raiz.
#define API_URL "http://192.168.0.10:8000/v1/measurements"
#define DEVICE_ID "no-01"                      // letras, números, '-' e '_'
#define DEVICE_TOKEN "TROQUE-este-token-do-no-01"  // o mesmo cadastrado em PM25_DEVICE_TOKENS no servidor
// #define API_ROOT_CA "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----\n"

// ---- Horário (sempre UTC) ----
#define NTP_SERVER_1 "a.st1.ntp.br"
#define NTP_SERVER_2 "pool.ntp.org"

// ---- PMS5003 (UART2). O sensor é alimentado em 5 V; os sinais são de 3,3 V. ----
#define PMS_RX_PIN 16  // RX do ESP32 <- TX do PMS5003 (pino 5 do sensor)
#define PMS_TX_PIN 17  // TX do ESP32 -> RX do PMS5003 (pino 4 do sensor)

// ---- Temperatura e umidade: deixe apenas UMA das opções ----
#define TH_SENSOR_BME280
// #define TH_SENSOR_DHT22

#define BME280_ADDR 0x76  // alguns módulos usam 0x77
#define I2C_SDA_PIN 21
#define I2C_SCL_PIN 22
#define DHT_PIN 4
