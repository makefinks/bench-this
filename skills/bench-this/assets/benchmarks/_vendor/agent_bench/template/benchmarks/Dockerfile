FROM node:22-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends git python3 python3-venv ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# The runner replaces this block at build time with only the configured harness installers.
# Every CLI must resolve from a system path because runs use a non-root UID and temporary HOME.
# BEGIN GENERATED HARNESS INSTALLS
# END GENERATED HARNESS INSTALLS

WORKDIR /workspace
