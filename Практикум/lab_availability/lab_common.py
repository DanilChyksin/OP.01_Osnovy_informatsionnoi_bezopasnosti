"""Fixed, bounded classroom protocol. No arbitrary URLs or ports."""
import ipaddress
import http.client
import json

PORT = 8765
MARKER = 'oib-availability-v1'
NETWORKS = tuple(ipaddress.ip_network(n) for n in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '127.0.0.0/8'))

def lab_ip(value):
    try:
        ip = ipaddress.IPv4Address(value)
    except ValueError as e:
        raise ValueError('Use a literal private IPv4 address, not a hostname or URL') from e
    if not any(ip in n for n in NETWORKS) or ip.is_multicast or str(ip).endswith(('.0', '.255')):
        raise ValueError('Only loopback or a classroom RFC1918 IPv4 address is allowed')
    return str(ip)

def request(host, path):
    conn = http.client.HTTPConnection(host, PORT, timeout=1.5)
    try:
        conn.request('GET', path, headers={'User-Agent': MARKER, 'Connection': 'close'})
        response = conn.getresponse()
        body = response.read(4096)
        return response.status, body
    finally:
        conn.close()

def check_server(host):
    status, body = request(host, '/health')
    data = json.loads(body)
    if status != 200 or data.get('lab') != MARKER:
        raise ValueError('The destination is not the approved classroom service')
    return data
