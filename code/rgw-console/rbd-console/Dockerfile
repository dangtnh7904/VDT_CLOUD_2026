FROM node:22-bookworm-slim

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev
COPY src ./src
RUN mkdir -p /var/lib/rbd-executor && chown node:node /var/lib/rbd-executor

ENV NODE_ENV=production PORT=3001
USER node
EXPOSE 3001
CMD ["node", "src/server.js"]
