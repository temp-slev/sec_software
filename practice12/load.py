"""Генерация нагрузки для проверки метрик и почтового оповещения Grafana."""
import argparse
import collections
import datetime
import time
import urllib.error
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument('--url', default='http://localhost:18012')
parser.add_argument('--duration', type=int, default=120)
parser.add_argument('--error-every', type=int, default=0)
parser.add_argument('--pause', type=float, default=0.05)
args = parser.parse_args()
print('Начало UTC:', datetime.datetime.now(datetime.timezone.utc).isoformat(), flush=True)
end = time.monotonic() + args.duration
counts = collections.Counter()
i = 0
while time.monotonic() < end:
    path = '/fail' if args.error_every and i % args.error_every == 0 else '/'
    try:
        response = urllib.request.urlopen(args.url + path, timeout=10)
        response.read()
        counts[response.status] += 1
        response.close()
    except urllib.error.HTTPError as error:
        counts[error.code] += 1
        error.close()
    i += 1
    time.sleep(args.pause)
print('Конец UTC:', datetime.datetime.now(datetime.timezone.utc).isoformat())
print('Ответы по HTTP-статусам:', dict(counts))
