FROM node:22.23.3-bookworm-slim@sha256:43ac6c60b8f89723f746e8a92ce91abd5017e627ce1ddfe4238355d3a30b772c AS build
WORKDIR /app
ADD --checksum=sha256:f5924adde5b1c2237a70b150fc4e043d7969f23c45aacac18f57e041d2b564fe https://codeload.github.com/emdash-cms/emdash/tar.gz/913cb1bb9b7f08c3ff0d258b4420e53835b6a58e /source.tar.gz
RUN mkdir /source && tar -xzf /source.tar.gz -C /source --strip-components=1 && cp -a /source/templates/blog/. /app/ && cp /source/LICENSE /app/LICENSE.upstream
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY overlay.mjs /overlay.mjs
RUN node /overlay.mjs
ENV NODE_OPTIONS=--max-old-space-size=2048
RUN npm run build

FROM node:22.23.3-bookworm-slim@sha256:43ac6c60b8f89723f746e8a92ce91abd5017e627ce1ddfe4238355d3a30b772c
LABEL org.opencontainers.image.source="https://github.com/neobuilds/emdash-container" \
      org.opencontainers.image.url="https://github.com/emdash-cms/emdash" \
      org.opencontainers.image.title="EmDash Blog" \
      org.opencontainers.image.version="1.1.0-xcloud.3" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.description="EmDash upstream Blog with Node workerd sandbox; independent deployment packaging"
WORKDIR /app
COPY --from=build /app /app
COPY start.mjs /app/start.mjs
RUN mkdir -p /app/data /app/uploads /app/.astro && chown -R node:node /app/data /app/uploads /app/.astro
USER node
ENV HOST=0.0.0.0 PORT=4321 NODE_ENV=production
EXPOSE 4321
CMD ["node", "start.mjs"]
