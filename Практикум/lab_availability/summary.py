"""Summarize each client/run separately; never average percentiles."""
import argparse
import csv
import glob
import math
import sys
from collections import defaultdict
from pathlib import Path

def summarize(files):
    groups = defaultdict(list)
    seen = set()
    for pattern in files:
        matches = glob.glob(pattern)
        if not matches:
            raise ValueError('No files match:'+pattern)
        for filename in matches:
            path = Path(filename).resolve()
            if path in seen:
                continue
            seen.add(path)
            with path.open(encoding='utf-8-sig', newline='') as f:
                reader = csv.DictReader(f)
                if not {'phase','client','server','window_s','status','latency_ms'} <= set(reader.fieldnames or []):
                    continue  # server logs and earlier summaries have another schema
                for row in reader:
                    groups[(path.name,row['phase'],row['client'],row['server'])].append(row)
    result = []
    for (filename,phase,client,server), rows in sorted(groups.items()):
        windows={float(r['window_s']) for r in rows}
        if len(windows)!=1 or min(windows)<=0:
            raise ValueError('Inconsistent window:'+filename)
        n=len(rows)
        ok=[r for r in rows if int(r['status'])==200]
        latency=sorted(float(r['latency_ms']) for r in ok)
        result.append(dict(file=filename, phase=phase, client=client, requests=n, success=len(ok), http429=sum(int(r['status'])==429 for r in rows), http503=sum(int(r['status'])==503 for r in rows), other=sum(int(r['status']) not in (200,429,503) for r in rows), success_percent=round(100*len(ok)/n,2), success_rps=round(len(ok)/windows.pop(),3), p95_success_ms=latency[math.ceil(.95*len(latency))-1] if latency else 'NA'))
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument('files', nargs='+')
    p.add_argument('--out', type=Path)
    a=p.parse_args()
    rows=summarize(a.files)
    if not rows:
        p.error('No client measurements found')
    stream=a.out.open('x',newline='',encoding='utf-8') if a.out else sys.stdout
    try:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)
    finally:
        if a.out:stream.close()
if __name__=='__main__':main()
