# syntax=docker/dockerfile:1.17
FROM golang:1.27.0-alpine3.23@sha256:3747dcba41c8b0db3211fda4db61638b980e17ac5bb3c94460a975a9cfe19395 AS build

WORKDIR /src
COPY services/control-plane/go.mod services/control-plane/go.sum ./
RUN go mod download

COPY services/control-plane/cmd ./cmd
COPY services/control-plane/internal ./internal
COPY services/control-plane/migrations ./migrations

ARG VERSION=development
ARG COMMIT=unknown
ARG BUILT_AT=unknown

# Both binaries come from one build, so the schema a deployment applies is the
# schema the service serving it was compiled against.
RUN CGO_ENABLED=0 go build \
    -trimpath \
    -ldflags="-s -w -X main.version=${VERSION} -X main.commit=${COMMIT} -X main.builtAt=${BUILT_AT}" \
    -o /out/control-plane ./cmd/control-plane \
 && CGO_ENABLED=0 go build \
    -trimpath -ldflags="-s -w" \
    -o /out/migrate ./cmd/migrate

FROM alpine:latest@sha256:28bd5fe8b56d1bd048e5babf5b10710ebe0bae67db86916198a6eec434943f8b

RUN addgroup -S coralcity && adduser -S -G coralcity coralcity \
 && mkdir -p /credentials && chown coralcity:coralcity /credentials

COPY --from=build /out/control-plane /usr/local/bin/control-plane
COPY --from=build /out/migrate /usr/local/bin/migrate

USER coralcity
EXPOSE 8080

HEALTHCHECK --interval=5s --timeout=3s --start-period=5s --retries=12 \
  CMD wget -q -O /dev/null http://127.0.0.1:8080/health/ready || exit 1

ENTRYPOINT ["/usr/local/bin/control-plane"]
