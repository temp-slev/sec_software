"""Проверка Service Discovery и метрик Prometheus двух реплик FastAPI."""
import json
import os
import urllib.parse
import urllib.request

PROMETHEUS = os.getenv('PROMETHEUS_URL', 'http://localhost:19090')


def get(path):
    return json.load(urllib.request.urlopen(PROMETHEUS + path, timeout=15))


def query(expr):
    return get('/api/v1/query?' + urllib.parse.urlencode({'query': expr}))['data']['result']


targets = get('/api/v1/targets')['data']['activeTargets']
apps = [t for t in targets if t['labels'].get('namespace') == 'practice12']
assert len(apps) == 2 and all(t['health'] == 'up' for t in apps), apps
print('ServiceMonitor: две цели practice12 в состоянии UP')
for t in apps:
    print(t['labels']['pod'], t['scrapeUrl'], t['health'])
counters = query('my_custom_counter_total{namespace="practice12"}')
assert len(counters) == 2 and all(float(r['value'][1]) > 0 for r in counters), counters
for row in counters:
    print('my_custom_counter_total', row['metric']['pod'], row['value'][1])
requests = query('sum(rate(http_requests_total{namespace="practice12"}[1m]))')
assert requests and float(requests[0]['value'][1]) > 0
print('RPS (http_requests_total):', requests[0]['value'][1])
print('Метрики обеих реплик получены и доступны в Prometheus')
