"""Сбор данных для расследования инцидента: Prometheus (метрики) и Loki (логи).

Требуются port-forward: Prometheus на 9090 и Loki на 3100.
Запуск: python collect_evidence.py 2026-10-24T11:06:43Z 2026-10-24T11:08:23Z
"""
import datetime as dt
import json
import sys
import urllib.parse
import urllib.request


def get(url, **params):
    return json.load(urllib.request.urlopen(url + "?" + urllib.parse.urlencode(params)))


def parse(ts):
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))


start, end = parse(sys.argv[1]), parse(sys.argv[2])
before = start - dt.timedelta(minutes=2)
after = end + dt.timedelta(seconds=30)


def prom_range(q):
    return get(
        "http://localhost:9090/api/v1/query_range",
        query=q, start=before.timestamp(), end=after.timestamp(), step=15,
    )["data"]["result"]


def loki(q, at):
    return get("http://localhost:3100/loki/api/v1/query", query=q, time=int(at.timestamp()))["data"]["result"]


print(f"Инцидент (нагрузка на /cpu и /crash): {start:%H:%M:%S} .. {end:%H:%M:%S} UTC")
queries = [
    ("CPU по подам, ядра", 'sum by (pod) (rate(container_cpu_usage_seconds_total{pod=~"fastapi-app.*"}[1m]))'),
    ("Память по подам, МиБ", 'sum by (pod) (container_memory_working_set_bytes{pod=~"fastapi-app.*"}) / 1048576'),
    ("Все запросы, запросов/с", "sum(rate(http_requests_total[1m]))"),
    ("Ошибки 5xx, запросов/с", 'sum(rate(http_requests_total{status=~"5.."}[1m]))'),
    ("p95 латентность, с", "histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket[1m])))"),
]
for title, q in queries:
    print(f"\n# PromQL: {q}")
    for r in prom_range(q):
        vals = [float(v[1]) for v in r["values"] if v[1] != "NaN"]
        if vals:
            print(f"  {title} [{r['metric'].get('pod', 'всего')}]: до нагрузки {vals[0]:.3f}, максимум {max(vals):.3f}")

rows = prom_range('sum(rate(http_requests_total{status=~"5.."}[1m]))')
peak = max(rows[0]["values"], key=lambda v: float(v[1]))
print(f"\nПик 5xx по Prometheus: {float(peak[1]):.2f}/с в {dt.datetime.fromtimestamp(peak[0], dt.timezone.utc):%H:%M:%S} UTC")

window = f"[{int((after - before).total_seconds())}s]"
print("\n# LogQL: количество строк ERROR по подам")
for r in loki('sum by (pod) (count_over_time({app="fastapi-app"} | json | level="ERROR" ' + window + "))", after):
    print("  ", r["metric"], r["value"][1])
print("# LogQL: запросы по эндпоинтам")
for r in loki('sum by (path) (count_over_time({app="fastapi-app"} | json ' + window + "))", after):
    print("  ", r["metric"], r["value"][1])
print("# LogQL: причины ошибок (поле reason)")
for r in loki('sum by (reason) (count_over_time({app="fastapi-app"} | json | level="ERROR" | reason!="" ' + window + "))", after):
    print("  ", r["metric"], r["value"][1])
print("# LogQL: медианная длительность запроса /cpu, с")
for r in loki('quantile_over_time(0.5, {app="fastapi-app"} | json | path="/cpu" | unwrap duration ' + window + ") by (app)", after):
    print("  ", r["value"][1])
print("# LogQL: максимальная длительность запроса /cpu, с")
for r in loki('max_over_time({app="fastapi-app"} | json | path="/cpu" | unwrap duration ' + window + ") by (app)", after):
    print("  ", r["value"][1])
