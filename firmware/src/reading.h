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
  int16_t rssi;                 // RSSI_NONE quando indisponível
  uint16_t samples;             // quadros do PMS5003 na média
};
static_assert(sizeof(Reading) == 44, "tamanho do registro mudou: troque o nome do arquivo de pendências");

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

// deviceId deve conter só letras, números, '-' e '_' (a API valida o mesmo padrão).
inline std::string buildPayload(const char* deviceId, const Reading* rs, size_t count) {
  std::string s;
  s.reserve(64 + count * 240);
  s += "{\"schema_version\":\"1\",\"device_id\":\"";
  s += deviceId;
  s += "\",\"readings\":[";
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
