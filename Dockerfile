FROM python:3.13-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.8.22 /uv /uvx /bin/

# Use the image's interpreter. Without this, uv downloads a managed
# Python matching .python-version into the user's data directory, which
# fails for the non-root user (no writable HOME) and would duplicate
# the interpreter this base image provides. The base image version must
# match .python-version; a mismatch fails the build with a version
# error.
ENV UV_PYTHON_DOWNLOADS=never

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
