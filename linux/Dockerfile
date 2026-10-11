FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# openssh-server: Stage 5/6 entry point | cron: the vulnerable scheduler
# procps/iproute2: enumeration tools (ps, ss) | vim-tiny: text editor for Stage 6
RUN apt-get update && apt-get install -y --no-install-recommends \
    openssh-server \
    cron \
    procps \
    iproute2 \
    vim-tiny \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 22

ENTRYPOINT ["/entrypoint.sh"]
