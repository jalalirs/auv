# syntax=docker/dockerfile:1.17
FROM golang:1.27.0-alpine3.23@sha256:3747dcba41c8b0db3211fda4db61638b980e17ac5bb3c94460a975a9cfe19395 AS build

WORKDIR /src
COPY services/worker/go.mod ./
COPY services/worker/cmd ./cmd
COPY services/worker/internal ./internal

ARG VERSION=development
ARG COMMIT=unknown
ARG BUILT_AT=unknown

RUN CGO_ENABLED=0 go build \
    -trimpath \
    -ldflags="-s -w" \
    -o /out/worker \
    ./cmd/worker

FROM alpine:latest@sha256:28bd5fe8b56d1bd048e5babf5b10710ebe0bae67db86916198a6eec434943f8b

# The worker reaches the container runtime through its socket, whose group
# differs between hosts; the compose definition supplies the right one.
RUN adduser -S -D -H coralcity

COPY --from=build /out/worker /usr/local/bin/worker

ENTRYPOINT ["/usr/local/bin/worker"]
