#!/bin/sh
set -eu
cd "$(dirname "$0")"
test "$(kubectl config current-context)" = docker-desktop
docker build -t practice13-fastapi:v1 .
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm upgrade --install prometheus-stack prometheus-community/kube-prometheus-stack --version 92.11.0 -n monitoring --create-namespace -f ../practice12/monitoring/values.yaml -f grafana/values.yaml
kubectl apply -f k8s/app.yaml -f k8s/mailpit.yaml -f grafana/dashboard-configmap.yaml
kubectl rollout status -n practice13 deploy/fastapi-app --timeout=180s
kubectl rollout status -n practice13 deploy/mailpit --timeout=180s
kubectl rollout status -n monitoring deploy/prometheus-stack-grafana --timeout=180s
