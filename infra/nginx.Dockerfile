FROM node:20-alpine AS webapp_build
WORKDIR /src/webapp
COPY webapp/package*.json ./
RUN npm ci
COPY webapp/ ./
RUN npm run build

FROM node:20-alpine AS admin_build
WORKDIR /src/admin
COPY admin/package*.json ./
RUN npm ci
COPY admin/ ./
RUN npm run build

FROM nginx:alpine
COPY infra/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=webapp_build /src/webapp/dist /usr/share/nginx/html
COPY --from=admin_build /src/admin/dist /usr/share/nginx/admin
