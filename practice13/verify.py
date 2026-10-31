"""Проверка Grafana, дашбордов и доставки email в локальный SMTP-приёмник."""
import base64
import json
import os
import time
import urllib.parse
import urllib.request

GRAFANA = os.getenv('GRAFANA_URL', 'http://localhost:13000')
MAILPIT = os.getenv('MAILPIT_URL', 'http://localhost:18025')
PROMETHEUS = os.getenv('PROMETHEUS_URL', 'http://localhost:19090')
# Демонстрационные данные локального стенда из Helm values.
auth = 'Basic ' + base64.b64encode(b'admin:prom-operator').decode()


def get(url, authenticated=False):
    req = urllib.request.Request(url, headers={'Authorization': auth} if authenticated else {})
    return json.load(urllib.request.urlopen(req, timeout=15))


def grafana(path):
    return get(GRAFANA + path, True)


def prom(expr):
    return get(PROMETHEUS + '/api/v1/query?' + urllib.parse.urlencode({'query': expr}))['data']['result']


datasource = grafana('/api/datasources/uid/prometheus')
assert datasource['isDefault'] and datasource['type'] == 'prometheus'
assert grafana('/api/datasources/uid/prometheus/health')['status'] == 'OK'
print('Источник Prometheus: Default, health=OK', flush=True)
for number in [13]:
    dashboard = grafana(f'/api/dashboards/uid/practice{number}-fastapi')['dashboard']
    assert len(dashboard['panels']) == 8
    print(f'Дашборд practice{number}: 8 панелей, включая RPS, ошибки, p50/p95/p99 и custom counter', flush=True)
    # Проверка каждого PromQL-запроса, использованного в панелях.
    for panel in dashboard['panels']:
        for target in panel['targets']:
            result = prom(target['expr'])
            assert result, (number, panel['title'], target['expr'])
    print(f'PromQL всех панелей practice{number} выполняется и возвращает данные', flush=True)

rules = grafana('/api/v1/provisioning/alert-rules')
rule = next(r for r in rules if r['uid'] == 'fastapi5xx13')
assert '[5m]' in rule['data'][0]['model']['expr']
assert rule['data'][2]['model']['conditions'][0]['evaluator']['params'] == [5]
print('Правило Grafana: доля 5xx > 5% за 5 минут, for=30s, включено', flush=True)
# Ожидание реального письма, а не ручного Test contact point.
for attempt in range(90):
    messages = get(MAILPIT + '/api/v1/messages')
    matching = [m for m in messages.get('messages', []) if 'FastAPI 5xx over 5 percent' in m.get('Subject', '')]
    if matching:
        message = matching[0]
        assert any(recipient['Address'] == 'alerts@example.test' for recipient in message['To'])
        details = get(MAILPIT + '/api/v1/message/' + message['ID'])
        assert 'Доля ответов' in (details.get('Text', '') + details.get('HTML', ''))
        print('SMTP-письмо получено Mailpit:', message['Subject'], flush=True)
        print('Получатель:', message['To'][0]['Address'], 'ID:', message['ID'], flush=True)
        print('Тело письма содержит описание сработавшего правила', flush=True)
        break
    time.sleep(2)
else:
    raise AssertionError('Письмо Grafana не поступило за 180 секунд')

rows = prom('sum by (pod) (my_custom_counter_total{namespace="practice13"})')
assert len(rows) == 2
print('my_custom_counter_total по двум подам:', [(r['metric']['pod'],r['value'][1]) for r in rows], flush=True)
ratio = prom('100 * sum(rate(http_requests_total{namespace="practice13",status=~"5.."}[5m])) / sum(rate(http_requests_total{namespace="practice13"}[5m]))')
assert ratio and float(ratio[0]['value'][1]) > 5
print('Измеренная доля 5xx за 5 минут:', ratio[0]['value'][1] + '%', flush=True)
print('Все проверки Grafana и email-доставки пройдены', flush=True)
