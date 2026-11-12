# CloudTrain portal image (Node 24, see docs/decisions/0003-node-24.md).

# 1. Install libraries and build the site.
FROM node:24-alpine AS build
WORKDIR /portal
COPY package.json package-lock.json ./
RUN npm ci
COPY next.config.mjs ./
COPY app ./app
RUN npm run build

# 2. Run only the built server (much smaller image).
FROM node:24-alpine
WORKDIR /portal
ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0
COPY --from=build /portal/.next/standalone ./
COPY --from=build /portal/.next/static ./.next/static
# Run as the image's normal "node" user, not root.
USER node
# 3000 is the portal's port in the contract (contracts/ports.md).
EXPOSE 3000
CMD ["node", "server.js"]
