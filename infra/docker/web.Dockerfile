FROM nginx:1.27-alpine

RUN apk add --no-cache curl

COPY infra/docker/web.nginx.conf /etc/nginx/conf.d/default.conf
COPY apps/web /usr/share/nginx/html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
