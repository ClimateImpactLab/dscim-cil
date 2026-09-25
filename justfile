# format python files
format:
	uv run --group tests ruff format src tests

# lint python files, fixing what can be fixed
lint:
	uv run --group tests ruff check --fix src tests

# check types
typecheck:
	uv run --group tests ty check

# run tests
test:
	uv run --group tests pytest --color=yes tests

# run format, linting, type, and testing checks
validate: format lint typecheck test

# build docs site (docs/options.md is generated from the catalogue)
build-docs:
	uv run --group docs python scripts/generate_options_page.py
	uv run --group docs zensical build --clean

# start local web server to serve docs site
serve-docs:
	uv run --group docs python scripts/generate_options_page.py
	uv run --group docs zensical serve
