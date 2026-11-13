"""Sequential rate-capped client for the matching classroom service only."""
import argparse
import csv
import datetime
import re
import time
from pathlib import Path
from lab_common import lab_ip, check_server, request

def main():
    p = argparse.ArgumentParser(description='Low-rate classroom measurement client')
    p.add_argument('--server', type=lab_ip, required=True)
    p.add_argument('--client', required=True)
    p.add_argument('--phase', choices=['baseline', 'load', 'protected', 'recovery'], required=True)
    p.add_argument('--seconds', type=int, default=30)
    p.add_argument('--rps', type=float, default=1)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    if not 10 <= a.seconds <= 45 or not 0.2 <= a.rps <= 2:
        p.error('Runtime10..45 seconds and rate0.2..2 requests/s only')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,24}', a.client):
        p.error('Client label:1..24 ASCII letters/digits/_/-')
    try:
        info = check_server(a.server)
    except Exception as e:
        p.exit(2, 'Lab handshake failed:'+type(e).__name__+'; check the IP and server allowlist\n')
    if (a.phase == 'protected' and not info['protected']) or (a.phase in ('baseline', 'load') and info['protected']):
        p.exit(2, 'Phase does not match server protection mode\n')
    a.out.parent.mkdir(parents=True, exist_ok=True)
    fields = ['utc', 'phase', 'client', 'server', 'window_s', 'status', 'latency_ms', 'error']
    rows = []
    with a.out.open('x', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        deadline = time.monotonic()+a.seconds
        next_at = time.monotonic()
        try:
            while time.monotonic() < deadline:
                time.sleep(max(0, next_at-time.monotonic()))
                if time.monotonic() >= deadline:
                    break
                next_at = time.monotonic()+1/a.rps  # no catch-up bursts
                ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
                started = time.monotonic()
                status, error = 0, ''
                try:
                    status, _ = request(a.server, '/work')
                except (OSError, TimeoutError) as e:
                    error = type(e).__name__
                row = dict(utc=ts, phase=a.phase, client=a.client, server=a.server, window_s=a.seconds, status=status, latency_ms=round((time.monotonic()-started)*1000, 2), error=error)
                rows.append(row)
                writer.writerow(row)
                f.flush()
        except KeyboardInterrupt:
            print('Stopped. Partial run:exclude from full-window throughput comparisons.')
    ok = sum(r['status'] == 200 for r in rows)
    print(f'Requests={len(rows)}; HTTP200={ok}; HTTP429={sum(r["status"]==429 for r in rows)}; HTTP503={sum(r["status"]==503 for r in rows)}; network_errors={sum(r["status"]==0 for r in rows)}')

if __name__ == '__main__':
    main()
