# ---------------------------------------------------------------
# EnviroMesh Dashboard — Web Frontend (static build)
# Build context: ./dashboard
# Serves the dashboard UI on port 80 (matches docker-compose expose: 80)
# ---------------------------------------------------------------
# Build stage: compile frontend assets (React/Vue/etc.) when source exists
FROM node:20-alpine AS builder

WORKDIR /app

# Copy dependency manifests first for better layer caching
COPY package*.json ./

# Install dependencies (if package.json exists)
RUN if [ -f package.json ]; then npm ci; fi

# Copy source and build (if source exists)
COPY . .
RUN if [ -f package.json ] && { [ -f vite.config.js ] || [ -f webpack.config.js ] || [ -f next.config.js ]; }; then \
        npm run build; \
    fi

# ---------------------------------------------------------------
# Runtime stage: serve static assets with nginx
# ---------------------------------------------------------------
FROM nginx:1.28-alpine

# Copy built assets from builder (if a build folder exists)
#COPY --from=builder /app/dist /usr/share/nginx/html
#COPY --from=builder /app/build /usr/share/nginx/html
#COPY --from=builder /app/.next /usr/share/nginx/html

# Copy a placeholder index.html if none was built
COPY index.html /usr/share/nginx/html/index.html

# Copy nginx config if provided
#COPY default.conf /etc/nginx/conf.d/default.config

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
