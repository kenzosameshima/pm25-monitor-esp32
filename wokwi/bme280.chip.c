// BME280 custom chip for Wokwi
// Adafruit BME280 library compatible
//
// As conversões aplicam as mesmas fórmulas de compensação da biblioteca Adafruit (Bosch, aritmética
// inteira) e fazem uma busca binária pelo valor de ADC que reproduz o valor do controle. A leitura
// "pulada" (0x8000 / 0x80000), que a biblioteca interpreta como NAN, nunca é gerada.

#include "wokwi-api.h"

#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>



// ============================================================================
// Configuration
// ============================================================================

#define DEBUG_BME280 0

#define BME280_I2C_ADDRESS 0x76
#define BME280_CHIP_ID     0x60



// ============================================================================
// Register map
// ============================================================================

#define REG_CHIP_ID        0xD0
#define REG_RESET          0xE0

#define REG_CALIB_00       0x88
#define REG_CALIB_26       0xA1

#define REG_CALIB_HUM_00   0xE1
#define REG_CALIB_HUM_06   0xE7

#define REG_CTRL_HUM       0xF2
#define REG_STATUS         0xF3
#define REG_CTRL_MEAS      0xF4
#define REG_CONFIG         0xF5

#define REG_PRESS_MSB      0xF7
#define REG_HUM_LSB        0xFE



// ============================================================================
// Calibration (valores de exemplo do datasheet)
// ============================================================================

static const uint8_t calibration_88[26] =
{
    0x70, 0x6B,     // T1 = 27504
    0x43, 0x67,     // T2 = 26435
    0x18, 0xFC,     // T3 = -1000

    0x7D, 0x8E,     // P1 = 36477
    0x43, 0xD6,     // P2 = -10685
    0xD0, 0x0B,     // P3 = 3024
    0x27, 0x0B,     // P4 = 2855
    0x8C, 0x00,     // P5 = 140
    0xF9, 0xFF,     // P6 = -7
    0x8C, 0x3C,     // P7 = 15500
    0xF8, 0xC6,     // P8 = -14600
    0x70, 0x17,     // P9 = 6000

    0x00,           // 0xA0: não usado
    0x4B            // 0xA1: H1 = 75
};


static const uint8_t calibration_E1[7] =
{
    0x6A, 0x01,  // H2 = 362
    0x00,        // H3 = 0

    0x20,        // H4 MSB
    0x0A,        // H4 LSB + H5 LSB
    0x00,        // H5 MSB

    0x1E         // H6 = 30
};


// Coeficientes decodificados como a biblioteca faz em readCoefficients().
typedef struct
{
    uint16_t T1; int16_t T2, T3;
    uint16_t P1; int16_t P2, P3, P4, P5, P6, P7, P8, P9;
    uint8_t H1; int16_t H2; uint8_t H3; int16_t H4, H5; int8_t H6;
} calibration_t;

static calibration_t cal;

static uint16_t u16le(const uint8_t *p) { return (uint16_t)(p[0] | (p[1] << 8)); }

static void decode_calibration(void)
{
    const uint8_t *c = calibration_88;

    cal.T1 = u16le(c + 0);
    cal.T2 = (int16_t)u16le(c + 2);
    cal.T3 = (int16_t)u16le(c + 4);

    cal.P1 = u16le(c + 6);
    cal.P2 = (int16_t)u16le(c + 8);
    cal.P3 = (int16_t)u16le(c + 10);
    cal.P4 = (int16_t)u16le(c + 12);
    cal.P5 = (int16_t)u16le(c + 14);
    cal.P6 = (int16_t)u16le(c + 16);
    cal.P7 = (int16_t)u16le(c + 18);
    cal.P8 = (int16_t)u16le(c + 20);
    cal.P9 = (int16_t)u16le(c + 22);

    cal.H1 = c[25];
    cal.H2 = (int16_t)u16le(calibration_E1 + 0);
    cal.H3 = calibration_E1[2];
    cal.H4 = (int16_t)(((int8_t)calibration_E1[3] << 4) | (calibration_E1[4] & 0x0F));
    cal.H5 = (int16_t)(((int8_t)calibration_E1[5] << 4) | (calibration_E1[4] >> 4));
    cal.H6 = (int8_t)calibration_E1[6];
}



// ============================================================================
// Chip state
// ============================================================================

typedef struct
{
    uint8_t register_pointer;
    uint8_t write_phase;

    uint8_t ctrl_humidity;
    uint8_t ctrl_measurement;
    uint8_t configuration;

    uint8_t raw_data[8];

    uint32_t temperature_attribute;
    uint32_t pressure_attribute;
    uint32_t humidity_attribute;

} bme280_state_t;



// ============================================================================
// Debug
// ============================================================================

#if DEBUG_BME280
#define DEBUG_PRINT(...) printf(__VA_ARGS__)
#else
#define DEBUG_PRINT(...)
#endif



// ============================================================================
// Compensação (idêntica à da biblioteca Adafruit BME280)
// ============================================================================

static int32_t compensate_t_fine(int32_t adc_T)
{
    int32_t var1 = (adc_T / 8) - ((int32_t)cal.T1 * 2);
    var1 = (var1 * (int32_t)cal.T2) / 2048;

    int32_t var2 = (adc_T / 16) - (int32_t)cal.T1;
    var2 = (((var2 * var2) / 4096) * (int32_t)cal.T3) / 16384;

    return var1 + var2;
}

static float t_fine_to_celsius(int32_t t_fine)
{
    return (float)((t_fine * 5 + 128) / 256) / 100.0f;
}

static float compensate_pressure_hpa(int32_t adc_P, int32_t t_fine)
{
    int64_t var1 = (int64_t)t_fine - 128000;
    int64_t var2 = var1 * var1 * (int64_t)cal.P6;
    var2 = var2 + ((var1 * (int64_t)cal.P5) * 131072);
    var2 = var2 + ((int64_t)cal.P4 * 34359738368LL);
    var1 = ((var1 * var1 * (int64_t)cal.P3) / 256) + (var1 * (int64_t)cal.P2 * 4096);
    var1 = (140737488355328LL + var1) * (int64_t)cal.P1 / 8589934592LL;

    if (var1 == 0)
        return 0.0f;

    int64_t var4 = 1048576 - adc_P;
    var4 = (((var4 * 2147483648LL) - var2) * 3125) / var1;
    var1 = ((int64_t)cal.P9 * (var4 / 8192) * (var4 / 8192)) / 33554432;
    var2 = ((int64_t)cal.P8 * var4) / 524288;
    var4 = ((var4 + var1 + var2) / 256) + ((int64_t)cal.P7 * 16);

    return (float)(var4 / 256.0 / 100.0);
}

static float compensate_humidity(int32_t adc_H, int32_t t_fine)
{
    int32_t var1 = t_fine - 76800;
    int32_t var2 = adc_H * 16384;
    int32_t var3 = (int32_t)cal.H4 * 1048576;
    int32_t var4 = (int32_t)cal.H5 * var1;
    int32_t var5 = (((var2 - var3) - var4) + 16384) / 32768;

    var2 = (var1 * (int32_t)cal.H6) / 1024;
    var3 = (var1 * (int32_t)cal.H3) / 2048;
    var4 = ((var2 * (var3 + 32768)) / 1024) + 2097152;
    var2 = ((var4 * (int32_t)cal.H2) + 8192) / 16384;
    var3 = var5 * var2;
    var4 = ((var3 / 32768) * (var3 / 32768)) / 128;
    var5 = var3 - ((var4 * (int32_t)cal.H1) / 16);
    var5 = var5 < 0 ? 0 : var5;
    var5 = var5 > 419430400 ? 419430400 : var5;

    return (float)((uint32_t)(var5 / 4096)) / 1024.0f;
}



// ============================================================================
// Conversão inversa: busca binária pelo ADC que reproduz o valor desejado
// ============================================================================

static int32_t temperature_to_adc(float celsius)
{
    int32_t lo = 0, hi = 0xFFFFF;              // cresce com o ADC

    while (lo < hi)
    {
        int32_t mid = lo + (hi - lo) / 2;

        if (t_fine_to_celsius(compensate_t_fine(mid)) < celsius)
            lo = mid + 1;
        else
            hi = mid;
    }

    return lo == 0x80000 ? lo + 1 : lo;        // 0x80000 = leitura pulada (NAN)
}

static int32_t pressure_to_adc(float hpa, int32_t t_fine)
{
    int32_t lo = 0, hi = 0xFFFFF;              // decresce com o ADC

    while (lo < hi)
    {
        int32_t mid = lo + (hi - lo) / 2;

        if (compensate_pressure_hpa(mid, t_fine) > hpa)
            lo = mid + 1;
        else
            hi = mid;
    }

    return lo == 0x80000 ? lo + 1 : lo;
}

static int32_t humidity_to_adc(float percent, int32_t t_fine)
{
    int32_t lo = 0, hi = 0xFFFF;               // cresce com o ADC

    while (lo < hi)
    {
        int32_t mid = lo + (hi - lo) / 2;

        if (compensate_humidity(mid, t_fine) < percent)
            lo = mid + 1;
        else
            hi = mid;
    }

    return lo == 0x8000 ? lo + 1 : lo;         // 0x8000 = leitura pulada (NAN)
}



// ============================================================================
// Sensor update
// ============================================================================

static void update_sensor_data(bme280_state_t *chip)
{
    float temperature = attr_read_float(chip->temperature_attribute);
    float pressure = (float)attr_read(chip->pressure_attribute);
    float humidity = attr_read_float(chip->humidity_attribute);

    if (temperature < -40.0f) temperature = -40.0f;
    if (temperature > 85.0f)  temperature = 85.0f;
    if (pressure < 300.0f)    pressure = 300.0f;
    if (pressure > 1100.0f)   pressure = 1100.0f;
    if (humidity < 0.0f)      humidity = 0.0f;
    if (humidity > 100.0f)    humidity = 100.0f;

    int32_t adc_temperature = temperature_to_adc(temperature);
    int32_t t_fine = compensate_t_fine(adc_temperature);
    int32_t adc_pressure = pressure_to_adc(pressure, t_fine);
    int32_t adc_humidity = humidity_to_adc(humidity, t_fine);

    chip->raw_data[0] = (uint8_t)(adc_pressure >> 12);
    chip->raw_data[1] = (uint8_t)(adc_pressure >> 4);
    chip->raw_data[2] = (uint8_t)((adc_pressure & 0x0F) << 4);

    chip->raw_data[3] = (uint8_t)(adc_temperature >> 12);
    chip->raw_data[4] = (uint8_t)(adc_temperature >> 4);
    chip->raw_data[5] = (uint8_t)((adc_temperature & 0x0F) << 4);

    chip->raw_data[6] = (uint8_t)(adc_humidity >> 8);
    chip->raw_data[7] = (uint8_t)adc_humidity;

    DEBUG_PRINT(
        "[BME280] T=%.2f P=%.1f RH=%.2f -> ADC T=%ld P=%ld H=%ld\n",
        temperature, pressure, humidity,
        (long)adc_temperature, (long)adc_pressure, (long)adc_humidity
    );
}



// ============================================================================
// Register reading
// ============================================================================

static uint8_t read_register(
    bme280_state_t *chip,
    uint8_t address)
{
    if (address == REG_CHIP_ID)
        return BME280_CHIP_ID;


    if (address >= REG_CALIB_00 &&
        address <= REG_CALIB_26)
    {
        return calibration_88[address - REG_CALIB_00];
    }


    if (address >= REG_CALIB_HUM_00 &&
        address <= REG_CALIB_HUM_06)
    {
        return calibration_E1[address - REG_CALIB_HUM_00];
    }


    if (address >= REG_PRESS_MSB &&
        address <= REG_HUM_LSB)
    {
        return chip->raw_data[address - REG_PRESS_MSB];
    }


    switch(address)
    {
        case REG_CTRL_HUM:
            return chip->ctrl_humidity;

        case REG_STATUS:
            return 0x00;

        case REG_CTRL_MEAS:
            return chip->ctrl_measurement;

        case REG_CONFIG:
            return chip->configuration;

        default:
            return 0x00;
    }
}



// ============================================================================
// I2C callbacks
// ============================================================================

static bool on_i2c_connect(
    void *user_data,
    uint32_t address,
    bool connected)
{
    (void)connected;

    bme280_state_t *chip = user_data;

    chip->write_phase = 0;

    return address == BME280_I2C_ADDRESS;
}



static void on_i2c_disconnect(void *user_data)
{
    bme280_state_t *chip = user_data;

    chip->write_phase = 0;
}



static uint8_t on_i2c_read(void *user_data)
{
    bme280_state_t *chip = user_data;

    uint8_t reg = chip->register_pointer;

    uint8_t value =
        read_register(chip, reg);

    chip->register_pointer++;

    return value;
}



static bool on_i2c_write(
    void *user_data,
    uint8_t data)
{
    bme280_state_t *chip = user_data;


    if (chip->write_phase == 0)
    {
        chip->register_pointer = data;
        chip->write_phase = 1;
        return true;
    }


    uint8_t reg =
        chip->register_pointer++;


    switch(reg)
    {
        case REG_RESET:

            if(data == 0xB6)
            {
                chip->register_pointer = 0;
                chip->write_phase = 0;

                chip->ctrl_humidity = 0;
                chip->ctrl_measurement = 0;
                chip->configuration = 0;

                update_sensor_data(chip);
            }

            break;


        case REG_CTRL_HUM:
            chip->ctrl_humidity = data;
            break;


        case REG_CTRL_MEAS:
            chip->ctrl_measurement = data;

            if(data & 0x03)
                update_sensor_data(chip);

            break;


        case REG_CONFIG:
            chip->configuration = data;
            break;
    }


    return true;
}



// ============================================================================
// Timer callback
// ============================================================================

static void timer_callback(void *user_data)
{
    update_sensor_data(user_data);
}



// ============================================================================
// Chip initialization
// ============================================================================

void chip_init(void)
{
    decode_calibration();

    bme280_state_t *chip =
        malloc(sizeof(*chip));


    if (!chip)
    {
        printf("[BME280] allocation failed\n");
        return;
    }

    memset(chip, 0, sizeof(*chip));


    chip->temperature_attribute =
        attr_init_float("temp", 25.0);


    chip->pressure_attribute =
        attr_init("press", 1013);


    chip->humidity_attribute =
        attr_init_float("hum", 50.0);



    update_sensor_data(chip);



    const i2c_config_t i2c =
    {
        .user_data = chip,
        .address = BME280_I2C_ADDRESS,

        .scl = pin_init("SCL", INPUT_PULLUP),
        .sda = pin_init("SDA", INPUT_PULLUP),

        .connect = on_i2c_connect,
        .read = on_i2c_read,
        .write = on_i2c_write,
        .disconnect = on_i2c_disconnect
    };


    i2c_init(&i2c);



    const timer_config_t timer =
    {
        .callback = timer_callback,
        .user_data = chip
    };


    timer_t refresh_timer =
        timer_init(&timer);


    timer_start(
        refresh_timer,
        500,
        true);

    printf(
        "[BME280] Simulator ready\n");
}
