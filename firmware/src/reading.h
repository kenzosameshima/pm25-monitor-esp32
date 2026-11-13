// Registro de uma leitura e montagem do JSON do contrato v1, sem dependências do Arduino.
#pragma once
#include <math.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <time.h>

#include <string>

// Gravado em binário no buffer da flash: se mudar a estrutura, mude o nome do arquivo de pendências.
struct Reading {
  uint32_t boot_id;   // contador de inicializações (NVS)
  uint32_t seq;       // sequência dentro da inicialização
  uint32_t ts;        // epoch UTC do início da janela de 1 minuto
  uint32_t uptime_s;
  float pm1, pm25, pm10, pm25_cf1;
  float temperature, humidity;  // NAN quando indisponível
  float pressure;               // hPa; NAN quando indisponível
  int16_t rssi;                 // RSSI_NONE quando indisponível
  uint16_t samples;             // quadros do PMS5003 na média
};
static_assert(sizeof(Reading) == 48, "tamanho do registro mudou: troque o nome do arquivo de pendências");

static const int16_t RSSI_NONE = INT16_MIN;

inline void appendFloat(std::string& s, const char* key, float v) {
  char buf[48];
  if (isnan(v) || isinf(v)) {
    snprintf(buf, sizeof buf, "\"%s\":null", key);
  } else {
    snprintf(buf, sizeof buf, "\"%s\":%.1f", key, (double)v);
  }
  s += buf;
}

inline void formatIsoUtc(uint32_t epoch, char* out, size_t n) {
  time_t t = (time_t)epoch;
  struct tm tmv;
  gmtime_r(&t, &tmv);
  strftime(out, n, "%Y-%m-%dT%H:%M:%SZ", &tmv);
}

// Texto diagnóstico no JSON: só letras, números, espaço e . _ + : / - (o resto vira '_', para o texto nunca
// precisar de escape), com no máximo `limit` caracteres.
inline void appendSafeText(std::string& s, const char* text, size_t limit) {
  for (size_t i = 0; text[i] != '\0' && i < limit; ++i) {
    char c = text[i];
    bool ok = (c >= '0' && c <= '9') || (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || c == ' ' || c == '.' ||
              c == '_' || c == '+' || c == ':' || c == '/' || c == '-';
    s += ok ? c : '_';
  }
}

// Versão do firmware no JSON, com no máximo 64 caracteres, como a API guarda. Sem versão, o campo é omitido.
inline void appendFirmware(std::string& s, const char* firmware) {
  if (firmware == nullptr || firmware[0] == '\0') return;
  s += ",\"firmware\":\"";
  appendSafeText(s, firmware, 64);
  s += '"';
}

// Nome do motivo do reinício a partir do código de esp_reset_reason() (esp_reset_reason_t). Os códigos de 0 a 10
// são os mesmos no ESP-IDF do core Arduino 2.0.17 e no do 3.3.12; de 11 a 15 só existem no do 3.x. Um código fora
// da lista vai como "code_<n>", para um core mais novo nunca ficar sem registro.
inline std::string resetReasonName(int code) {
  static const char* const names[] = {"unknown",  "poweron", "ext",       "sw",       "panic",      "int_wdt",
                                      "task_wdt", "wdt",     "deepsleep", "brownout", "sdio",       "usb",
                                      "jtag",     "efuse",   "pwr_glitch", "cpu_lockup"};
  if (code >= 0 && code < (int)(sizeof names / sizeof names[0])) return names[code];
  char buf[24];
  snprintf(buf, sizeof buf, "code_%d", code);
  return buf;
}

// A inicialização em curso e o motivo pelo qual o nó reiniciou para chegar a ela. Vai no lote, e não em cada
// leitura: o lote pode trazer leituras de inicializações anteriores, guardadas no buffer, e o motivo é só da atual.
struct BootInfo {
  uint32_t boot_id;
  const char* reset_reason;  // nome de resetReasonName(); vazio ou nullptr omite os dois campos
};

// Motivo do reinício no JSON: "reset_reason" (até 32 caracteres, como a API guarda) e "reset_boot_id", a
// inicialização a que ele se refere. Campos opcionais do contrato v1: sem motivo, os dois são omitidos.
inline void appendBoot(std::string& s, const BootInfo* boot) {
  if (boot == nullptr || boot->reset_reason == nullptr || boot->reset_reason[0] == '\0') return;
  s += ",\"reset_reason\":\"";
  appendSafeText(s, boot->reset_reason, 32);
  char buf[40];
  snprintf(buf, sizeof buf, "\",\"reset_boot_id\":%lu", (unsigned long)boot->boot_id);
  s += buf;
}

// deviceId deve conter só letras, números, '-' e '_' (a API valida o mesmo padrão).
inline std::string buildPayload(const char* deviceId, const char* firmware, const BootInfo* boot, const Reading* rs,
                                size_t count) {
  std::string s;
  s.reserve(224 + count * 260);
  s += "{\"schema_version\":\"1\",\"device_id\":\"";
  s += deviceId;
  s += '"';
  appendFirmware(s, firmware);
  appendBoot(s, boot);
  s += ",\"readings\":[";
  for (size_t i = 0; i < count; ++i) {
    const Reading& r = rs[i];
    char ts[24];
    formatIsoUtc(r.ts, ts, sizeof ts);
    char head[160];
    snprintf(head, sizeof head, "%s{\"boot_id\":%lu,\"seq\":%lu,\"ts\":\"%s\",\"uptime_s\":%lu,\"samples\":%u,",
             i ? "," : "", (unsigned long)r.boot_id, (unsigned long)r.seq, ts, (unsigned long)r.uptime_s,
             (unsigned)r.samples);
    s += head;
    appendFloat(s, "pm1", r.pm1);
    s += ',';
    appendFloat(s, "pm25", r.pm25);
    s += ',';
    appendFloat(s, "pm10", r.pm10);
    s += ',';
    appendFloat(s, "pm25_cf1", r.pm25_cf1);
    s += ',';
    appendFloat(s, "temperature", r.temperature);
    s += ',';
    appendFloat(s, "humidity", r.humidity);
    s += ',';
    appendFloat(s, "pressure", r.pressure);
    if (r.rssi == RSSI_NONE) {
      s += ",\"rssi\":null}";
    } else {
      char rs_[24];
      snprintf(rs_, sizeof rs_, ",\"rssi\":%d}", (int)r.rssi);
      s += rs_;
    }
  }
  s += "]}";
  return s;
}
