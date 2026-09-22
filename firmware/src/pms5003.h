// Leitura do PMS5003 sem dependências do Arduino, para poder ser testada no computador.
//
// Quadro do sensor (32 bytes, big-endian):
//   0-1   0x42 0x4D        cabeçalho
//   2-3   28               comprimento do restante
//   4-9   PM1,0 PM2,5 PM10 "standard particle" (CF=1), µg/m³
//   10-15 PM1,0 PM2,5 PM10 "atmospheric environment", µg/m³
//   16-29 contagens de partículas e campo reservado
//   30-31 checksum = soma dos bytes 0 a 29
#pragma once
#include <stddef.h>
#include <stdint.h>

struct PmsFrame {
  uint16_t pm1_cf1, pm25_cf1, pm10_cf1;
  uint16_t pm1_atm, pm25_atm, pm10_atm;
};

class PmsParser {
 public:
  static const int kFrameLen = 32;

  // Recebe um byte por vez. Retorna true quando completa um quadro válido em `out`.
  bool feed(uint8_t b, PmsFrame& out) {
    if (pos_ == 0) {
      if (b == 0x42) buf_[pos_++] = b;
      return false;
    }
    if (pos_ == 1) {
      if (b == 0x4D) {
        buf_[pos_++] = b;
      } else if (b != 0x42) {
        pos_ = 0;  // 0x42 repetido: continua esperando o 0x4D
      }
      return false;
    }
    buf_[pos_++] = b;
    if (pos_ == 4 && word(2) != 28) {
      pos_ = 0;
      errors_++;
      return false;
    }
    if (pos_ < kFrameLen) return false;
    pos_ = 0;
    uint16_t sum = 0;
    for (int i = 0; i < kFrameLen - 2; ++i) sum += buf_[i];
    if (sum != word(30)) {
      errors_++;
      return false;
    }
    out.pm1_cf1 = word(4);
    out.pm25_cf1 = word(6);
    out.pm10_cf1 = word(8);
    out.pm1_atm = word(10);
    out.pm25_atm = word(12);
    out.pm10_atm = word(14);
    return true;
  }

  uint32_t errors() const { return errors_; }

 private:
  uint16_t word(int i) const { return (uint16_t)((buf_[i] << 8) | buf_[i + 1]); }
  uint8_t buf_[kFrameLen] = {0};
  int pos_ = 0;
  uint32_t errors_ = 0;
};

// Acumula os quadros de uma janela de 1 minuto e calcula as médias.
struct MinuteAccumulator {
  double pm1 = 0, pm25 = 0, pm10 = 0, pm25_cf1 = 0;
  uint16_t n = 0;

  void add(const PmsFrame& f) {
    pm1 += f.pm1_atm;
    pm25 += f.pm25_atm;
    pm10 += f.pm10_atm;
    pm25_cf1 += f.pm25_cf1;
    if (n < 0xFFFF) n++;
  }
  void reset() { *this = MinuteAccumulator(); }
  float mean(double sum) const { return n ? (float)(sum / n) : 0.0f; }
};
