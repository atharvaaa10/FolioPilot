# Development-oriented Dockerfile for FolioPilot Web (Next.js)

FROM node:20-alpine

WORKDIR /app

# Install dependencies based on package.json
COPY package.json package-lock.json* ./

RUN npm install

# Copy application source
COPY . .

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME=0.0.0.0
ENV NODE_ENV=development

CMD ["npm", "run", "dev"]

