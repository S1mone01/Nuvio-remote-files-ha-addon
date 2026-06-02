ARG BUILD_FROM=ghcr.io/home-assistant/aarch64-base:latest
FROM $BUILD_FROM

# Set shell
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install dependencies
RUN apk add --no-cache \
    python3 \
    py3-pip \
    curl \
    bash \
    ffmpeg

# Set up workdir
WORKDIR /app

# Copy requirements and install
COPY app/requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt --break-system-packages

# Copy app code
COPY app /app

# Copy run script
COPY run.sh /run.sh
RUN chmod a+x /run.sh

ENTRYPOINT [ "/run.sh" ]
