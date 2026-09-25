# Installation

The catalogue, validation, and planning commands need only click,
PyYAML, and rich:

```shell
uv pip install .
```

Real runs need dscim and its stack. The `run` extra pins the dscim
`main` commit the test suite runs against:

```shell
uv pip install ".[run]"
```

To use a different dscim, skip the extra and install your version
instead. `runner` warns at import when the installed dscim commit is
not the tested one, and every run records the dscim version and commit
in its `*_run_metadata.yaml`.

## Container

Published to ghcr on every push to master (`edge`) and on version
tags:

```shell
docker pull ghcr.io/climateimpactlab/dscim-cil:edge
docker run --rm -v ./conf:/mnt/conf:ro -v ./data:/mnt/data \
    ghcr.io/climateimpactlab/dscim-cil:edge run /mnt/conf/config.yml
```

Or build locally:

```shell
docker build -t dscim-cil:dev .
```

The image has the `run` extra installed, so it runs the full pipeline.
Mount configs and data as volumes; paths in the config must be the
paths as the container sees them.
