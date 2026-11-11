# Proxy de sortie à liste blanche (Squid). Seul conteneur relié au réseau extérieur.
FROM alpine:3.20

RUN apk add --no-cache squid

COPY squid.conf /etc/squid/squid.conf

USER squid
EXPOSE 3128
CMD ["squid", "-N", "-f", "/etc/squid/squid.conf"]
