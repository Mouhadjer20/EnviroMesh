# ---------------------------------------------------------------
# EnviroMesh Dashboard — React/Vite SPA served by Nginx
# Build context: ./raspberry_pi/dashboard
# ---------------------------------------------------------------
FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies first (layer-cached)
COPY package*.json ./
RUN npm ci

# Copy source and build
COPY . .

# VITE_API_PROXY is only used by the Vite dev-server proxy; at build time the
# SPA always fetches /api/* which Nginx strips and forwards to the backend.
# Pass any compile-time env vars here if needed via --build-arg / ARG.
RUN npm run build

# ---------------------------------------------------------------
# Runtime stage — lightweight Nginx serving the static bundle
# ---------------------------------------------------------------
FROM nginx:1.28-alpine

# Custom Nginx config: serve the SPA and handle 404 → index.html fallback
# (HashRouter works without this, but it future-proofs a switch to BrowserRouter)
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy compiled assets
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80


HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://127.0.0.1/ || exit 1