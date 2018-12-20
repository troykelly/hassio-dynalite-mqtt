ARG BUILD_FROM=hassioaddons/base:2.2.0
# hadolint ignore=DL3006
FROM ${BUILD_FROM}

# Copy root filesystem
COPY rootfs /

# Setup base
RUN apk add --no-cache \
    coreutils=8.29-r2 \
    wget=1.19.5-r0

# Scrip to run after startup
CMD ["/usr/bin/run.sh"]

# Build arugments
ARG BUILD_ARCH
ARG BUILD_DATE
ARG BUILD_REF
ARG BUILD_VERSION

# Labels
LABEL \
    io.hass.name="Dynalite" \
    io.hass.description="Dynalite to MQTT for Hassio" \
    io.hass.arch="${BUILD_ARCH}" \
    io.hass.type="addon" \
    io.hass.version=${BUILD_VERSION} \
    maintainer="Troy Kelly <troy@troykelly.com>" \
    org.label-schema.description="Dynalite to MQTT for Hassio" \
    org.label-schema.build-date=${BUILD_DATE} \
    org.label-schema.name="Dynalite" \
    org.label-schema.schema-version="1.0" \
    org.label-schema.url="https://troykelly.com" \
    org.label-schema.usage="https://github.com/troykelly/hassio-dynalite-mqtt/tree/master/README.md" \
    org.label-schema.vcs-ref=${BUILD_REF} \
    org.label-schema.vcs-url="https://github.com/troykelly/hassio-dynalite-mqtt" \
    org.label-schema.vendor="Troy Kelly"
