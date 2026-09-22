"""Simulador de nó sensor: gera leituras sintéticas e envia à API, como o firmware faria.

Serve para testar a cadeia de coleta (e depois o dashboard e o pipeline) antes do hardware.

Exemplos:
  # 6 horas de histórico, em lotes de 60 (como o nó esvaziando o buffer após uma queda de rede)
  python -m scripts.simulate_sensor --device no-01 --token SEU_TOKEN --minutes 360
  # depois, uma leitura por minuto, em tempo real
  python -m scripts.simulate_sensor --device no-01 --token SEU_TOKEN --minutes 0 --realtime
  # reinício do nó: novo boot_id, seq recomeça do zero sem colidir com os dados anteriores
  python -m scripts.simulate_sensor --device no-01 --token SEU_TOKEN --minutes 30 --boot-id 2
"""

import argparse
import json
import math
import random
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone


def synthetic(ts: datetime, state: dict) -> dict:
    """PM2,5 com picos de trânsito às 8h e às 19h (horário de Brasília) e ruído autocorrelacionado."""
    local_hour = (ts.hour - 3) % 24 + ts.minute / 60
    peaks = 14 * math.exp(-((local_hour - 8) ** 2) / 3) + 10 * math.exp(-((local_hour - 19) ** 2) / 4)
    state["noise"] = 0.95 * state.get("noise", 0.0) + random.gauss(0, 0.8)
    pm25 = max(0.0, 12 + peaks + state["noise"])
    temperature = 20 + 6 * math.sin(2 * math.pi * (local_hour - 9) / 24) + random.gauss(0, 0.2)
    humidity = min(100.0, max(20.0, 75 - 2.2 * (temperature - 20) + random.gauss(0, 1.5)))
    return {
        "pm1": round(pm25 * 0.7, 1),
        "pm25": round(pm25, 1),
        "pm10": round(pm25 * 1.3, 1),
        "pm25_cf1": round(pm25 * 1.05, 1),
        "temperature": round(temperature, 1),
        "humidity": round(humidity, 1),
        "rssi": random.randint(-75, -55),
        "samples": random.randint(55, 60),
    }


def post(url: str, token: str, device: str, readings: list[dict]) -> tuple[int, str]:
    body = json.dumps({"schema_version": "1", "device_id": device, "readings": readings}).encode()
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://127.0.0.1:8000/v1/measurements")
    ap.add_argument("--device", required=True)
    ap.add_argument("--token", required=True)
    ap.add_argument("--minutes", type=int, default=360, help="minutos de histórico a enviar (terminando agora)")
    ap.add_argument("--batch", type=int, default=60, help="leituras por requisição no histórico")
    ap.add_argument("--boot-id", type=int, default=1)
    ap.add_argument("--realtime", action="store_true", help="depois do histórico, envia 1 leitura por minuto")
    args = ap.parse_args()

    state: dict = {}
    seq = 0
    now_min = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    start = now_min - timedelta(minutes=args.minutes)
    uptime0 = time.time() - args.minutes * 60

    pending = []
    for i in range(args.minutes):
        ts = start + timedelta(minutes=i)
        pending.append({"boot_id": args.boot_id, "seq": seq, "ts": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "uptime_s": i * 60, **synthetic(ts, state)})
        seq += 1
    for k in range(0, len(pending), args.batch):
        code, text = post(args.url, args.token, args.device, pending[k:k + args.batch])
        print(f"lote {k // args.batch + 1}: HTTP {code} {text}")
        if code not in (200, 201):
            return 1

    while args.realtime:
        ts = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        reading = {"boot_id": args.boot_id, "seq": seq, "ts": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "uptime_s": int(time.time() - uptime0), **synthetic(ts, state)}
        code, text = post(args.url, args.token, args.device, [reading])
        print(f"{reading['ts']} pm25={reading['pm25']}: HTTP {code} {text}")
        seq += 1
        time.sleep(60 - datetime.now().second)
    return 0


if __name__ == "__main__":
    sys.exit(main())
