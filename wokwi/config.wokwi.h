// config.h para rodar o firmware no Wokwi (copie para firmware/src/config.h).
#pragma once

// A rede simulada do Wokwi é sempre esta, sem senha, no canal 6.
#define WIFI_SSID "Wokwi-GUEST"
#define WIFI_PASS ""
#define WIFI_CHANNEL 6

// Com o gateway privado (Wokwi Club no navegador, ou Wokwi for VS Code), host.wokwi.internal
// aponta para o computador que roda a API. Sem ele, só a internet é alcançável: exponha a API
// local por um túnel (ngrok, cloudflared) e use a URL https gerada.
#define API_URL "http://host.wokwi.internal:8000/v1/measurements"
#define DEVICE_ID "no-01"
#define DEVICE_TOKEN "TROQUE-este-token-do-no-01"

#define NTP_SERVER_1 "pool.ntp.org"
#define NTP_SERVER_2 "a.st1.ntp.br"

// Mesma ligação dos chips simulados: PMS5003 na UART2 e BME280 em 0x76.
#define PMS_RX_PIN 16
#define PMS_TX_PIN 17
#define TH_SENSOR_BME280
#define BME280_ADDR 0x76
#define I2C_SDA_PIN 21
#define I2C_SCL_PIN 22
#define DHT_PIN 4
