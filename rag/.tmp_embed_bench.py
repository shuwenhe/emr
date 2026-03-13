import json, math, time, concurrent.futures, urllib.request
from collections import OrderedDict

URL='http://127.0.0.1:11434/api/embed'
MODEL='bge-m3:latest'
BATCH_SIZES=[32,64,96]
CONCURRENCIES=[4,8,12]
TOTAL_TEXTS_PER_CASE=512
TIMEOUT=90
TEXT='中医辨证论治用于性能压测。'


def percentile(vals, p):
    vals = sorted(vals)
    if not vals:
        return 0.0
    k=(len(vals)-1)*p
    f=math.floor(k); c=math.ceil(k)
    if f==c:
        return vals[int(k)]
    return vals[f]*(c-k)+vals[c]*(k-f)


def one_request(batch_size):
    body=json.dumps({'model':MODEL,'input':[TEXT]*batch_size}, ensure_ascii=False).encode('utf-8')
    req=urllib.request.Request(URL,data=body,headers={'Content-Type':'application/json'},method='POST')
    t0=time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            payload=resp.read()
            ok=(resp.status==200)
            if ok:
                obj=json.loads(payload.decode('utf-8'))
                ok=isinstance(obj.get('embeddings'), list) and len(obj['embeddings'])==batch_size
            return ok, time.perf_counter()-t0
    except Exception:
        return False, time.perf_counter()-t0


def run_case(batch_size, conc):
    reqs=max(math.ceil(TOTAL_TEXTS_PER_CASE/batch_size), conc)
    lat=[]; ok_reqs=0
    t0=time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=conc) as ex:
        futs=[ex.submit(one_request, batch_size) for _ in range(reqs)]
        for f in concurrent.futures.as_completed(futs):
            ok, elapsed=f.result()
            lat.append(elapsed)
            if ok:
                ok_reqs += 1
    wall=time.perf_counter()-t0
    fail_reqs=reqs-ok_reqs
    ok_texts=ok_reqs*batch_size
    return OrderedDict([
        ('batch_size', batch_size),
        ('concurrency', conc),
        ('requests', reqs),
        ('ok_requests', ok_reqs),
        ('failed_requests', fail_reqs),
        ('ok_texts', ok_texts),
        ('wall_sec', round(wall,4)),
        ('throughput_chunks_per_sec', round(ok_texts/wall if wall else 0.0,2)),
        ('avg_req_ms', round((sum(lat)/len(lat))*1000 if lat else 0.0,2)),
        ('p50_req_ms', round(percentile(lat,0.5)*1000,2)),
        ('p95_req_ms', round(percentile(lat,0.95)*1000,2)),
        ('error_rate_pct', round((fail_reqs/reqs*100.0) if reqs else 0.0,2)),
    ])

results=[]
for b in BATCH_SIZES:
    for c in CONCURRENCIES:
        results.append(run_case(b,c))

ranked=sorted(results, key=lambda x: x['throughput_chunks_per_sec'], reverse=True)
out={'results':results,'ranked':ranked,'meta':{'url':URL,'model':MODEL,'batch_sizes':BATCH_SIZES,'concurrencies':CONCURRENCIES,'total_texts_per_case':TOTAL_TEXTS_PER_CASE,'timeout_sec':TIMEOUT,'ts':time.time()}}
with open('.tmp_embed_bench_result.json','w',encoding='utf-8') as f:
    json.dump(out,f,ensure_ascii=False,indent=2)
print('wrote .tmp_embed_bench_result.json')
