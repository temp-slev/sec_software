# MinIO Community и mc собираются из официальных исходников с закреплённым коммитом.
FROM golang:1.24.3-alpine AS builder
RUN apk add --no-cache git ca-certificates
ARG COMPONENT=minio
ARG VERSION=RELEASE.2025-04-22T22-12-26Z
ARG COMMIT=0d7408fc9969caf07de6a8c3a84f9fbb10a6739e
ENV CGO_ENABLED=0 GOMAXPROCS=2 GOFLAGS=-p=2
WORKDIR /src
RUN git clone --depth 1 --branch "$VERSION" "https://github.com/minio/$COMPONENT.git" . \
    && test "$(git rev-parse HEAD)" = "$COMMIT" \
    && go build -trimpath -ldflags '-s -w' -o /out/service .
FROM python:3.12-slim
RUN useradd --uid 10001 --create-home storageuser \
    && mkdir /data && chown storageuser:storageuser /data
COPY --from=builder /out/service /usr/local/bin/service
COPY --from=builder /src/LICENSE /usr/share/licenses/storage/LICENSE
USER storageuser
ENTRYPOINT ["service"]
