# The console is static assets served by nginx, which proxies the API on the
# same origin.
#
# Same origin is the point: the session is a cookie, so the browser sends it
# without any script reading it, and no token is ever handed to JavaScript that
# a cross-site script could take.

FROM node:24.20.0-alpine AS build
WORKDIR /src

RUN corepack enable && corepack prepare pnpm@11.24.0 --activate

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/console/package.json apps/console/
RUN pnpm install --frozen-lockfile

COPY packages/contracts packages/contracts
COPY apps/console apps/console
RUN pnpm --filter @coral-city/console run build

FROM nginx:1.27-alpine
COPY apps/console/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/apps/console/dist /usr/share/nginx/html
