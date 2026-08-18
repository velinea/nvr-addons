ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:latest
FROM ${BUILD_FROM}

ARG GO2RTC_VERSION=1.9.14

RUN apk add --no-cache python3 py3-pip curl patch ffmpeg \
    gcc musl-dev python3-dev rtmpdump-dev

COPY requirements.txt /tmp/
RUN CFLAGS="-Wno-error=incompatible-pointer-types" \
    pip3 install --no-cache-dir --break-system-packages -r /tmp/requirements.txt

COPY patches/ /tmp/patches/
RUN PKG=$(python3 -c "import librtmp, os; print(os.path.dirname(librtmp.__file__))") && \
    patch -d "$PKG" -p1 < /tmp/patches/librtmp_result_handler.patch

COPY connect.py /app/connect.py

RUN ARCH=$(uname -m) && \
    if [ "$ARCH" = "x86_64" ]; then ARCH="amd64"; fi && \
    if [ "$ARCH" = "aarch64" ]; then ARCH="arm64"; fi && \
    curl -sL "https://github.com/AlexxIT/go2rtc/releases/download/v${GO2RTC_VERSION}/go2rtc_linux_${ARCH}" \
      -o /usr/local/bin/go2rtc && \
    chmod +x /usr/local/bin/go2rtc

COPY run.sh /
RUN chmod +x /run.sh

CMD ["/run.sh"]
