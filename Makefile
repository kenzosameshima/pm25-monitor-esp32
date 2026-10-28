# Compilação estrita das partes em C e C++ que rodam fora do ESP32 (use Linux, WSL ou MSYS2).
#   make test    compila e roda firmware/host_tests/test_core.cpp
#   make chips   compila, sem gerar arquivo, os chips simulados do Wokwi. O wokwi-api.h não está no
#                repositório: aponte WOKWI_API para a pasta que o contém (make chips WOKWI_API=/pasta)
#   make         roda o test e, se WOKWI_API estiver definido, também o chips
#   make clean   apaga o que o test gerou
# Com clang: make CC=clang CXX=clang++ ANALYZER=   (o -fanalyzer só existe no GCC)
# O firmware do ESP32 (firmware/src/main.cpp) é compilado pelo PlatformIO e não passa por aqui.

CC       = gcc
CXX      = g++
STD      ?= c11
CXXSTD   ?= c++17
ANALYZER ?= -fanalyzer
OPT      ?= -O2

# Avisos comuns ao C e ao C++.
WARN = -Wall \
	-Wextra \
	-Wpedantic \
	-Werror \
	-Wconversion \
	-Wsign-conversion \
	-Wshadow \
	-Wformat=2 \
	-Wundef \
	-Wcast-qual \
	-Wcast-align \
	-Wwrite-strings

# -Wstrict-prototypes e -Wmissing-prototypes só existem para C; no g++ com -Werror viram erro.
CFLAGS   = -std=$(STD) \
	$(WARN) \
	-Wstrict-prototypes \
	-Wmissing-prototypes \
	$(ANALYZER) \
	$(OPT) \
	-g

CXXFLAGS = -std=$(CXXSTD) \
	$(WARN) \
	$(OPT) \
	-g

TEST_DIR = firmware/host_tests
TEST_BIN = $(TEST_DIR)/test_core
CHIPS    = wokwi/pms5003.chip.c wokwi/bme280.chip.c

.PHONY: all test chips clean $(CHIPS)

all: test
ifdef WOKWI_API
all: chips
endif

$(TEST_BIN): $(TEST_DIR)/test_core.cpp firmware/src/pms5003.h firmware/src/reading.h
	$(CXX) $(CXXFLAGS) -Ifirmware/src $< -o $@

# O teste grava payload_exemplo.json na pasta atual, por isso roda de dentro de host_tests.
test: $(TEST_BIN)
	cd $(TEST_DIR) && ./test_core

chips: $(CHIPS)

# -isystem: os avisos do wokwi-api.h, que não é nosso, não derrubam o -Werror.
$(CHIPS):
	@test -n "$(WOKWI_API)" || { echo "defina WOKWI_API com a pasta que contém wokwi-api.h"; exit 1; }
	$(CC) $(CFLAGS) -isystem $(WOKWI_API) -c $@ -o /dev/null

clean:
	rm -f $(TEST_BIN) $(TEST_DIR)/payload_exemplo.json
