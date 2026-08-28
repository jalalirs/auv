# syntax=docker/dockerfile:1.17
FROM node:24.20.0-alpine3.23@sha256:0388af2af070cd4736a1567cfed02469ba117848845b4165d87a333edb53d2ca AS build

WORKDIR /src
RUN npm config set fetch-retries 5 \
    && npm config set fetch-retry-mintimeout 2000 \
    && npm config set fetch-retry-maxtimeout 20000 \
    && npm install --global --ignore-scripts pnpm@11.24.0

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json ./apps/web/package.json
COPY packages/client-ts/package.json ./packages/client-ts/package.json
RUN pnpm install --frozen-lockfile --filter @coral-city/web...

# The client's types are generated from the contract and checked in, so the
# build reads them rather than running a generator.
COPY packages/client-ts ./packages/client-ts
COPY apps/web ./apps/web
RUN pnpm --filter @coral-city/web build

FROM nginx:alpine@sha256:db35bfc6b2951e7f8a72db5db120288c127ffaeeb4a6d4b95a26fead017d5913

COPY apps/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/apps/web/dist /usr/share/nginx/html

EXPOSE 8080

HEALTHCHECK --interval=5s --timeout=2s --start-period=2s --retries=10 \
  CMD wget -q -O /dev/null http://127.0.0.1:8080/ || exit 1
