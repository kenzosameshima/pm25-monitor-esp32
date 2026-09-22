-- Esquema do banco (SQLite, modo WAL). Todos os horários em UTC, formato ISO 8601 ("2026-09-22T12:00:00Z").

CREATE TABLE IF NOT EXISTS devices (
    device_id   TEXT PRIMARY KEY,
    first_seen  TEXT NOT NULL,
    location    TEXT,
    notes       TEXT
);

-- Tabela bruta: só recebe INSERT. Limpeza, agregações e features ficam em tabelas derivadas.
CREATE TABLE IF NOT EXISTS measurements (
    id              INTEGER PRIMARY KEY,
    device_id       TEXT    NOT NULL REFERENCES devices(device_id),
    boot_id         INTEGER NOT NULL,   -- contador de inicializações do nó (gravado na NVS)
    seq             INTEGER NOT NULL,   -- sequência da leitura dentro de uma inicialização
    ts_sensor       TEXT    NOT NULL,   -- início da janela de 1 minuto medida pelo nó
    ts_received     TEXT    NOT NULL,   -- momento em que o servidor recebeu a leitura
    pm1             REAL,
    pm25            REAL    NOT NULL,   -- PM2,5 "atmospheric environment" do PMS5003, µg/m³
    pm10            REAL,
    pm25_cf1        REAL,               -- PM2,5 "standard particle" (CF=1), usado em correções
    temperature     REAL,
    humidity        REAL,
    rssi            INTEGER,
    uptime_s        INTEGER,
    samples         INTEGER,            -- quadros do PMS5003 que entraram na média do minuto
    schema_version  TEXT    NOT NULL,
    quality         TEXT    NOT NULL DEFAULT 'ok',
    UNIQUE (device_id, boot_id, seq)
);
CREATE INDEX IF NOT EXISTS idx_measurements_device_ts ON measurements (device_id, ts_sensor);
CREATE INDEX IF NOT EXISTS idx_measurements_received  ON measurements (device_id, ts_received);

CREATE TRIGGER IF NOT EXISTS measurements_no_update BEFORE UPDATE ON measurements
BEGIN SELECT RAISE(ABORT, 'measurements é imutável'); END;
CREATE TRIGGER IF NOT EXISTS measurements_no_delete BEFORE DELETE ON measurements
BEGIN SELECT RAISE(ABORT, 'measurements é imutável'); END;

-- Um registro por requisição aceita: base das métricas de infraestrutura (lotes, duplicatas).
CREATE TABLE IF NOT EXISTS ingest_batches (
    id            INTEGER PRIMARY KEY,
    received_at   TEXT    NOT NULL,
    device_id     TEXT    NOT NULL,
    n_readings    INTEGER NOT NULL,
    n_inserted    INTEGER NOT NULL,
    n_duplicates  INTEGER NOT NULL,
    remote_addr   TEXT
);

-- Requisições rejeitadas, guardadas para auditoria.
CREATE TABLE IF NOT EXISTS invalid_messages (
    id           INTEGER PRIMARY KEY,
    received_at  TEXT NOT NULL,
    remote_addr  TEXT,
    device_id    TEXT,
    reason       TEXT NOT NULL,
    raw_payload  TEXT
);

-- Previsões gravadas pelo job horário antes de o valor observado existir (validação prospectiva).
CREATE TABLE IF NOT EXISTS forecasts (
    id              INTEGER PRIMARY KEY,
    device_id       TEXT NOT NULL,
    generated_at    TEXT NOT NULL,
    target_hour     TEXT NOT NULL,      -- início da hora prevista
    predicted_pm25  REAL NOT NULL,
    model_name      TEXT NOT NULL,
    model_version   TEXT NOT NULL,
    UNIQUE (device_id, target_hour, model_name, model_version)
);
