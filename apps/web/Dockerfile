# syntax=docker/dockerfile:1.17
FROM ghcr.io/pnpm/pnpm:11.24.0@sha256:f18a4dfbfd23931624a2396829ca921c7c262bf63fd4fa55af07654a7d41834e AS pnpm

FROM node:24.20.0-bookworm-slim@sha256:ba849c60be29959425b8734d57b8b4b7d56f98edd9504c9af091d5281095a71e AS build

WORKDIR /src
COPY --from=pnpm /opt/pnpm /opt/pnpm
COPY --from=pnpm /usr/lib/*/libatomic.so.1.2.0 /usr/local/lib/libatomic.so.1
ENV PATH=/opt/pnpm:${PATH}
ENV LD_LIBRARY_PATH=/usr/local/lib

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json ./apps/web/package.json
RUN pnpm install --frozen-lockfile --filter @coral-city/web...

COPY apps/web ./apps/web
RUN pnpm --filter @coral-city/web build

FROM nginx:alpine@sha256:db35bfc6b2951e7f8a72db5db120288c127ffaeeb4a6d4b95a26fead017d5913

COPY apps/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/apps/web/dist /usr/share/nginx/html

EXPOSE 8080

HEALTHCHECK --interval=5s --timeout=2s --start-period=2s --retries=10 \
  CMD wget -q -O /dev/null http://127.0.0.1:8080/health/live || exit 1
