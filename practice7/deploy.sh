#!/bin/sh
set -eu
cd "$(dirname "$0")"
test "$(kubectl config current-context)" = docker-desktop
docker build -t practice7-fastapi:v1 .
helm repo add traefik https://traefik.github.io/charts
helm upgrade --install traefik traefik/traefik --version 42.2.0 -n ingress-system --create-namespace -f k8s/traefik-values.yaml
helm repo add metrics-server https://kubernetes-sigs.github.io/metrics-server/
helm upgrade --install metrics-server metrics-server/metrics-server --version 3.14.0 -n kube-system -f k8s/metrics-server-values.yaml
kubectl apply -f k8s/namespace.yaml -f k8s/config.yaml -f k8s/postgres.yaml
kubectl rollout status -n practice7 deploy/postgres --timeout=180s
kubectl apply -f k8s/deployment.yaml -f k8s/service.yaml
kubectl rollout status -n practice7 deploy/fastapi-deployment --timeout=180s
