# Builds the dashboard on the development PC. Node is never installed on the capture host.
#   docker build --target export --output type=local,dest=dist .
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY index.html vite.config.js ./
COPY public ./public
COPY src ./src
RUN npm run build

FROM scratch AS export
COPY --from=build /app/dist /
