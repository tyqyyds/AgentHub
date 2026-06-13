FROM node:20-alpine AS build

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

# ---- Final stage ----
FROM nginx:alpine

# Create non-root user for nginx
RUN addgroup -S appgroup && adduser -S appuser -G appgroup

# Copy built assets and nginx config with proper ownership
COPY --from=build --chown=appuser:appgroup /app/dist /usr/share/nginx/html
COPY --chown=appuser:appgroup nginx.conf /etc/nginx/conf.d/default.conf

# Ensure nginx pid and log dirs are writable by appuser
RUN chown -R appuser:appgroup /var/cache/nginx && \
    chown -R appuser:appgroup /var/log/nginx && \
    touch /var/run/nginx.pid && \
    chown appuser:appgroup /var/run/nginx.pid

# Switch to non-root user
USER appuser

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://localhost/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
