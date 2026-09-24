FROM python:3.12-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.8.22 /uv /uvx /bin/

# uv needs the git CLI to fetch the dscim git dependency.
RUN apt-get -qq update \
    && apt-get -qq install --yes --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

ARG APP_HOME="/opt/dscim-cil"

# Run without root permissions.
USER 9876:9876

WORKDIR ${APP_HOME}
COPY . .

# Install with the run extra so dscim and its stack are available.
RUN uv sync --frozen --no-cache --no-dev --extra run --compile-bytecode

ENV PATH="${APP_HOME}/.venv/bin:$PATH"

# Mount configs and data as volumes, e.g.
#   docker run --rm -v ./conf:/mnt/conf:ro -v ./data:/mnt/data \
#       dscim-cil run /mnt/conf/config.yml
ENTRYPOINT ["dscim-cil"]
