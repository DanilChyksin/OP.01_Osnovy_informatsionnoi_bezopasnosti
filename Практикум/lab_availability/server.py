"""A capacity-limited simulation, not a production web server."""
import argparse
import collections
import csv
import datetime
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from lab_common import PORT, MARKER, lab_ip

class State:
    def __init__(self, allow, protected, stream):
        self.allow = set(allow) | {'127.0.0.1'}
        self.protected = protected
        self.lock = threading.Lock()
        self.slots = threading.BoundedSemaphore(2)
        self.active = 0
        self.arrivals = collections.deque()
        self.by_ip = {}
        self.stream = stream
        self.csv = csv.writer(stream)
        self.csv.writerow(['utc', 'source', 'path', 'status', 'latency_ms', 'active', 'protected'])
        stream.flush()

class Handler(BaseHTTPRequestHandler):
    server_version = 'ClassroomLab/1'
    def setup(self):
        super().setup()
        self.connection.settimeout(2)
    def log_message(self, *args):
        pass
    def do_POST(self):
        self.send_error(405)
    def do_GET(self):
        st = self.server.state
        started = time.monotonic()
        ip = self.client_address[0]
        status = 200
        owns_slot = False
        payload = {'lab': MARKER}
        try:
            if ip not in st.allow:
                status = 403
            elif self.path == '/health':
                payload.update(protected=st.protected, workers=2, service_delay_ms=350)
            elif self.path != '/work':
                status = 404
            else:
                now = time.monotonic()
                with st.lock:
                    while st.arrivals and st.arrivals[0] <= now-1:
                        st.arrivals.popleft()
                    if len(st.arrivals) >= 20:
                        status = 429  # hard classroom ceiling, also in open mode
                    else:
                        st.arrivals.append(now)
                        if st.protected:
                            q = st.by_ip.setdefault(ip, collections.deque())
                            while q and q[0] <= now-1:
                                q.popleft()
                            if len(q) >= 1:
                                status = 429
                            else:
                                q.append(now)
                if status == 200:
                    owns_slot = st.slots.acquire(blocking=False)
                    if not owns_slot:
                        status = 503
                    else:
                        with st.lock:
                            st.active += 1
                        time.sleep(0.35)  # simulate bounded service work, no CPU burn
                        payload['result'] = 'work completed'
            payload['status'] = status
            body = json.dumps(payload).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Connection', 'close')
            if status == 429:
                self.send_header('Retry-After', '1')
            self.end_headers()
            self.wfile.write(body)
        except (OSError, TimeoutError):
            status = 0
        finally:
            with st.lock:
                if owns_slot:
                    st.active -= 1
                st.csv.writerow([datetime.datetime.now(datetime.timezone.utc).isoformat(), ip, self.path[:80], status, round((time.monotonic()-started)*1000, 2), st.active, int(st.protected)])
                st.stream.flush()
            if owns_slot:
                st.slots.release()
            self.close_connection = True

class Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 16

def main():
    p = argparse.ArgumentParser(description='Bounded classroom availability simulator')
    p.add_argument('--bind', type=lab_ip, default='127.0.0.1')
    p.add_argument('--allow', type=lab_ip, action='append', default=[])
    p.add_argument('--protected', action='store_true')
    p.add_argument('--seconds', type=int, default=1800)
    p.add_argument('--log', type=Path, required=True)
    a = p.parse_args()
    if not 30 <= a.seconds <= 1800 or len(set(a.allow)) > 4:
        p.error('Runtime must be30..1800 seconds; maximum4 LAN clients')
    if a.bind != '127.0.0.1' and not a.allow:
        p.error('Explicit client allowlist is required for LAN use')
    a.log.parent.mkdir(parents=True, exist_ok=True)
    with a.log.open('x', newline='', encoding='utf-8') as stream:
        state = State(a.allow, a.protected, stream)
        with Server((a.bind, PORT), Handler) as server:
            server.state = state
            timer = threading.Timer(a.seconds, server.shutdown)
            timer.daemon = True
            timer.start()
            print(f'Lab:{a.bind}:{PORT}; protected={a.protected}; stop=Ctrl+C; limit={a.seconds}s', flush=True)
            try:
                server.serve_forever(poll_interval=0.1)
            except KeyboardInterrupt:
                pass
            finally:
                timer.cancel()

if __name__ == '__main__':
    main()
