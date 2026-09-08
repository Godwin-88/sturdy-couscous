FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY tsconfig.json ./
COPY src ./src

RUN npx tsc -p tsconfig.json

# Remove dev dependencies now that the build is done (slimmer runtime image)
RUN npm prune --omit=dev

EXPOSE 8080

CMD ["node", "dist/index.js"]