#!/bin/sh
set -eu
cd "$(dirname "$0")"
test "$(kubectl config current-context)" = docker-desktop
docker build -t practice12-fastapi:v1 .
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm upgrade --install prometheus-stack prometheus-community/kube-prometheus-stack --version 92.11.0 -n monitoring --create-namespace -f monitoring/values.yaml
kubectl apply -f k8s/app.yaml -f grafana/dashboard-configmap.yaml
kubectl rollout status -n practice12 deploy/fastapi-app --timeout=180s
