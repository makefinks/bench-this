FROM node:22-bookworm

# Preserve the selected harness installation when adapting this image for the
# project. The runner executes as a non-root UID with a temporary HOME, so every
# CLI must resolve from a system path rather than /root or a shell profile.
ARG COPILOT_CLI_VERSION=1.0.73
ARG OPENCODE_VERSION=1.17.18

RUN apt-get update \
    && apt-get install -y --no-install-recommends git python3 python3-venv ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && npm install --global "@github/copilot@${COPILOT_CLI_VERSION}" "opencode-ai@${OPENCODE_VERSION}"

WORKDIR /workspace
