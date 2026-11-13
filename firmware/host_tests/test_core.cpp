// Testes da parte do firmware que não depende do hardware. Rode no computador:
//   g++ -std=c++17 -Wall -I../src test_core.cpp -o test_core && ./test_core
// O programa grava payload_exemplo.json, que o teste do servidor usa para conferir o contrato.
#include <assert.h>
#include <stdio.h>
#include <string.h>

#include <vector>

#include "pms5003.h"
#include "reading.h"

static std::vector<uint8_t> frame(uint16_t pm25_cf1, uint16_t pm25_atm, bool corrupt = false) {
  uint16_t data[13] = {0};
  data[0] = 3;          // PM1,0 CF=1
  data[1] = pm25_cf1;   // PM2,5 CF=1
  data[2] = 9;          // PM10 CF=1
  data[3] = 2;          // PM1,0 atm
  data[4] = pm25_atm;   // PM2,5 atm
  data[5] = 8;          // PM10 atm
  std::vector<uint8_t> f = {0x42, 0x4D, 0x00, 28};
  for (uint16_t v : data) {
    f.push_back(static_cast<uint8_t>(v >> 8));
    f.push_back(static_cast<uint8_t>(v & 0xFF));
  }
  uint16_t sum = 0;
  for (uint8_t b : f) sum += b;
  if (corrupt) sum++;
  f.push_back(static_cast<uint8_t>(sum >> 8));
  f.push_back(static_cast<uint8_t>(sum & 0xFF));
  assert(f.size() == 32);
  return f;
}

static int feedAll(PmsParser& p, const std::vector<uint8_t>& bytes, std::vector<PmsFrame>& out) {
  PmsFrame fr;
  int n = 0;
  for (uint8_t b : bytes) {
    if (p.feed(b, fr)) {
      out.push_back(fr);
      n++;
    }
  }
  return n;
}

int main() {
  // quadro válido
  {
    PmsParser p;
    std::vector<PmsFrame> out;
    assert(feedAll(p, frame(14, 12), out) == 1);
    assert(out[0].pm25_cf1 == 14 && out[0].pm25_atm == 12 && out[0].pm10_atm == 8 && out[0].pm1_cf1 == 3);
  }
  // lixo antes do quadro, incluindo 0x42 solto e 0x42 0x42 0x4D
  {
    PmsParser p;
    std::vector<uint8_t> bytes = {0x00, 0x42, 0x13, 0xFF, 0x42};
    std::vector<uint8_t> f = frame(20, 18);
    bytes.insert(bytes.end(), f.begin(), f.end());
    std::vector<PmsFrame> out;
    assert(feedAll(p, bytes, out) == 1);
    assert(out[0].pm25_atm == 18);
  }
  // checksum errado é rejeitado e o parser se recupera no quadro seguinte
  {
    PmsParser p;
    std::vector<uint8_t> bytes = frame(5, 5, true);
    std::vector<uint8_t> ok = frame(7, 6);
    bytes.insert(bytes.end(), ok.begin(), ok.end());
    std::vector<PmsFrame> out;
    assert(feedAll(p, bytes, out) == 1);
    assert(out[0].pm25_atm == 6);
    assert(p.errors() == 1);
  }
  // comprimento inválido é rejeitado
  {
    PmsParser p;
    std::vector<uint8_t> bad = frame(5, 5);
    bad[3] = 20;
    std::vector<PmsFrame> out;
    assert(feedAll(p, bad, out) == 0);
  }
  // média do minuto
  {
    MinuteAccumulator acc;
    PmsFrame a = {10, 12, 20, 8, 10, 18};
    PmsFrame b = {10, 14, 20, 8, 12, 18};
    acc.add(a);
    acc.add(b);
    assert(acc.n == 2);
    assert(acc.mean(acc.pm25) == 11.0f);
    assert(acc.mean(acc.pm25_cf1) == 13.0f);
    acc.reset();
    assert(acc.n == 0 && acc.mean(acc.pm25) == 0.0f);
  }
  // payload JSON
  {
    Reading rs[2];
    memset(rs, 0, sizeof rs);
    rs[0] = {3, 0, 1790078400u, 120, 8.2f, 12.46f, 15.0f, 13.0f, 23.4f, 61.0f, 931.27f, -63, 58};
    rs[1] = {3, 1, 1790078460u, 180, 8.0f, 12.0f, 14.9f, 12.8f, NAN, NAN, NAN, RSSI_NONE, 57};
    BootInfo boot = {3, "poweron"};
    std::string json = buildPayload("no-01", "build Oct 26 2026 12:00:00", &boot, rs, 2);
    assert(json.find("\"device_id\":\"no-01\",\"firmware\":\"build Oct 26 2026 12:00:00\","
                     "\"reset_reason\":\"poweron\",\"reset_boot_id\":3,\"readings\":[") != std::string::npos);
    assert(json.find("\"ts\":\"2026-09-22T12:00:00Z\"") != std::string::npos);
    assert(json.find("\"pm25\":12.5") != std::string::npos);
    assert(json.find("\"temperature\":null") != std::string::npos);
    assert(json.find("\"pressure\":931.3") != std::string::npos);
    assert(json.find("\"pressure\":null") != std::string::npos);
    assert(json.find("\"rssi\":null") != std::string::npos);
    assert(json.find("\"boot_id\":3,\"seq\":1") != std::string::npos);
    FILE* f = fopen("payload_exemplo.json", "w");
    fputs(json.c_str(), f);
    fclose(f);
    // versão sem escape: caracteres fora da lista viram '_', o limite é 64 e sem versão o campo some
    std::string odd = buildPayload("no-01", "a\"b\\c\n", nullptr, rs, 1);
    assert(odd.find("\"firmware\":\"a_b_c_\"") != std::string::npos);
    std::string longer = buildPayload("no-01", std::string(100, 'x').c_str(), nullptr, rs, 1);
    assert(longer.find("\"firmware\":\"" + std::string(64, 'x') + "\"") != std::string::npos);
    assert(longer.find(std::string(65, 'x')) == std::string::npos);
    assert(buildPayload("no-01", nullptr, nullptr, rs, 1).find("firmware") == std::string::npos);
    assert(buildPayload("no-01", "", nullptr, rs, 1).find("firmware") == std::string::npos);
    // motivo do reinício: campo opcional, sempre junto da inicialização a que se refere
    std::string plain = buildPayload("no-01", nullptr, nullptr, rs, 1);
    assert(plain.find("reset_") == std::string::npos);
    assert(plain.find("{\"schema_version\":\"1\",\"device_id\":\"no-01\",\"readings\":[") == 0);
    BootInfo none = {7, ""};
    assert(buildPayload("no-01", nullptr, &none, rs, 1).find("reset_") == std::string::npos);
    BootInfo wdt = {41, "task_wdt"};
    assert(buildPayload("no-01", nullptr, &wdt, rs, 1)
               .find("\"device_id\":\"no-01\",\"reset_reason\":\"task_wdt\",\"reset_boot_id\":41,\"readings\":[") !=
           std::string::npos);
    BootInfo odd_reason = {1, "a\"b"};  // nunca precisa de escape, como a versão
    assert(buildPayload("no-01", nullptr, &odd_reason, rs, 1).find("\"reset_reason\":\"a_b\"") != std::string::npos);
  }
  // nome do motivo do reinício: os códigos de esp_reset_reason(), iguais nos cores 2.0.17 e 3.3.12 até SDIO
  {
    assert(resetReasonName(0) == "unknown");
    assert(resetReasonName(1) == "poweron");
    assert(resetReasonName(3) == "sw");           // ESP.restart(): o reinício após 15 min sem Wi-Fi
    assert(resetReasonName(4) == "panic");
    assert(resetReasonName(5) == "int_wdt");
    assert(resetReasonName(6) == "task_wdt");     // o watchdog de 90 s do firmware
    assert(resetReasonName(7) == "wdt");
    assert(resetReasonName(9) == "brownout");
    assert(resetReasonName(15) == "cpu_lockup");  // só existe no core 3.x
    assert(resetReasonName(16) == "code_16");     // código que o firmware não conhece: vai o número
    assert(resetReasonName(-1) == "code_-1");
  }
  puts("firmware: todos os testes passaram");
  return 0;
}
