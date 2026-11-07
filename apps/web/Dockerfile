# Multi-stage Dockerfile for FolioPilot Web (Next.js)

# --- Development stage ---
FROM node:20-alpine AS development

WORKDIR /app

COPY package.json package-lock.json* ./

RUN npm install && sha256sum package-lock.json | cut -d' ' -f1 > /app/node_modules/.lock-hash

COPY . .
RUN chmod +x /app/entrypoint.sh

EXPOSE 3000

ENV PORT=3000 \
    HOSTNAME=0.0.0.0 \
    NODE_ENV=development

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["npm", "run", "dev"]

# --- Builder stage for production ---
FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .
ENV NODE_ENV=production
RUN npm run build

# --- Production stage (non-root, no dev entrypoint guard) ---
FROM node:20-alpine AS production

WORKDIR /app

ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0

COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public

USER node

EXPOSE 3000

CMD ["npm", "run", "start"]
