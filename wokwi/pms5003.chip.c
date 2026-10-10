// pms5003.chip.c
// PMS5003 custom chip for Wokwi
// UART PM sensor simulator
//
// O quadro preenche também os campos "atmospheric environment" (bytes 10 a 15), que o firmware usa
// como PM2,5 principal.
// No sensor real, os dois conjuntos coincidem em concentrações baixas e se afastam acima de
// ~30 µg/m³; aqui os dois recebem o valor do controle, o que basta para testar a cadeia.

#include "wokwi-api.h"

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// ============================================================================
// Configuration
// ============================================================================

#define DEBUG_PMS5003            0

#define PMS5003_FRAME_SIZE       32
#define PMS5003_BAUD_RATE        9600
#define PMS5003_INTERVAL_MS      1000

#define PMS5003_FRAME_LENGTH     0x001C

#define DEFAULT_PM1_0            12
#define DEFAULT_PM2_5            25
#define DEFAULT_PM10             35

// ============================================================================
// Debug
// ============================================================================

#if DEBUG_PMS5003
#define DEBUG_PRINT(...) printf(__VA_ARGS__)
#else
#define DEBUG_PRINT(...)
#endif

// ============================================================================
// Frame layout
// ============================================================================

enum
{
    FRAME_HEADER_H = 0,
    FRAME_HEADER_L = 1,

    FRAME_LENGTH = 2,

    FRAME_PM1_CF1 = 4,       // "standard particle" (CF=1)
    FRAME_PM25_CF1 = 6,
    FRAME_PM10_CF1 = 8,

    FRAME_PM1_ATM = 10,      // "atmospheric environment"
    FRAME_PM25_ATM = 12,
    FRAME_PM10_ATM = 14,

    FRAME_CHECKSUM = PMS5003_FRAME_SIZE - 2,
};

#define PMS5003_HEADER_H 0x42
#define PMS5003_HEADER_L 0x4D

// ============================================================================
// Chip state
// ============================================================================

typedef struct
{
    uart_dev_t uart;

    uint32_t pm1_attribute;
    uint32_t pm25_attribute;
    uint32_t pm10_attribute;

} pms5003_state_t;

// ============================================================================
// Utility functions
// ============================================================================

static inline void write_be16(
    uint8_t *dst,
    uint16_t value)
{
    dst[0] = (uint8_t)(value >> 8);
    dst[1] = (uint8_t)value;
}

static uint16_t calculate_checksum(
    const uint8_t *data,
    uint16_t length)
{
    uint16_t sum = 0;

    for (uint16_t i = 0; i < length; i++)
    {
        sum += data[i];
    }

    return sum;
}

static uint16_t read_pm(
    uint32_t attribute)
{
    uint32_t value = attr_read(attribute);

    if (value > UINT16_MAX)
    {
        value = UINT16_MAX;
    }

    return (uint16_t)value;
}

// ============================================================================
// PMS5003 frame generation
// ============================================================================

static void create_frame(
    uint8_t *frame,
    uint16_t pm1,
    uint16_t pm25,
    uint16_t pm10)
{
    memset(frame, 0, PMS5003_FRAME_SIZE);

    frame[FRAME_HEADER_H] = PMS5003_HEADER_H;
    frame[FRAME_HEADER_L] = PMS5003_HEADER_L;

    write_be16(&frame[FRAME_LENGTH], PMS5003_FRAME_LENGTH);

    write_be16(&frame[FRAME_PM1_CF1], pm1);
    write_be16(&frame[FRAME_PM25_CF1], pm25);
    write_be16(&frame[FRAME_PM10_CF1], pm10);

    write_be16(&frame[FRAME_PM1_ATM], pm1);
    write_be16(&frame[FRAME_PM25_ATM], pm25);
    write_be16(&frame[FRAME_PM10_ATM], pm10);

    const uint16_t checksum =
        calculate_checksum(frame, PMS5003_FRAME_SIZE - 2);

    write_be16(&frame[FRAME_CHECKSUM], checksum);
}

// ============================================================================
// Send measurement
// ============================================================================

static void send_measurement(
    pms5003_state_t *chip)
{
    uint8_t frame[PMS5003_FRAME_SIZE];

    const uint16_t pm1 =
        read_pm(chip->pm1_attribute);

    const uint16_t pm25 =
        read_pm(chip->pm25_attribute);

    const uint16_t pm10 =
        read_pm(chip->pm10_attribute);

    create_frame(
        frame,
        pm1,
        pm25,
        pm10
    );

    uart_write(
        chip->uart,
        frame,
        sizeof(frame)
    );

    DEBUG_PRINT(
        "[PMS5003] PM1=%u PM2.5=%u PM10=%u\n",
        pm1,
        pm25,
        pm10
    );
}

// ============================================================================
// Timer callback
// ============================================================================

static void timer_callback(
    void *user_data)
{
    pms5003_state_t *chip = user_data;

    send_measurement(chip);
}

// ============================================================================
// Chip initialization
// ============================================================================

void chip_init(void)
{
    pms5003_state_t *chip =
        calloc(1, sizeof(*chip));

    if (!chip)
    {
        printf("[PMS5003] allocation failed\n");
        return;
    }

    // Sensor attributes
    chip->pm1_attribute =
        attr_init(
            "pm1",
            DEFAULT_PM1_0
        );

    chip->pm25_attribute =
        attr_init(
            "pm25",
            DEFAULT_PM2_5
        );

    chip->pm10_attribute =
        attr_init(
            "pm10",
            DEFAULT_PM10
        );

    // UART configuration
    const uart_config_t uart_config =
    {
        .tx = pin_init("TX", OUTPUT),
        .rx = pin_init("RX", INPUT),
        .baud_rate = PMS5003_BAUD_RATE,
        .user_data = chip,
    };

    chip->uart =
        uart_init(
            &uart_config
        );

    // Periodic measurement timer
    const timer_config_t timer_config =
    {
        .callback = timer_callback,
        .user_data = chip,
    };

    timer_t timer =
        timer_init(
            &timer_config
        );

    timer_start(
        timer,
        PMS5003_INTERVAL_MS,
        true
    );

    printf(
        "[PMS5003] Simulator ready\n"
    );
}
