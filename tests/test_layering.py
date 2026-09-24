"""Layering rules: import boundaries between modules.

config.py and options.py must be importable with only the standard
library plus PyYAML; only cli.py may import click, call
logging.basicConfig, or call sys.exit.
"""

import pathlib
import subprocess
import sys

PACKAGE = pathlib.Path(__file__).parent.parent / "src" / "dscim_cil"


def test_core_modules_do_not_pull_in_click_xarray_or_dscim():
    code = (
        "import sys\n"
        "import dscim_cil.options\n"
        "import dscim_cil.config\n"
        "forbidden = {'click', 'rich', 'xarray', 'dscim'} & set(sys.modules)\n"
        "assert not forbidden, forbidden\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


def test_only_cli_uses_click_logging_config_and_exit():
    for path in PACKAGE.glob("*.py"):
        if path.name == "cli.py":
            continue
        source = path.read_text()
        assert "import click" not in source, path.name
        assert "import rich" not in source, path.name
        assert "from rich" not in source, path.name
        assert "logging.basicConfig" not in source, path.name
        assert "sys.exit(" not in source, path.name


def test_cli_is_the_only_module_with_an_entry_point_surface():
    source = (PACKAGE / "cli.py").read_text()
    assert "import click" in source
    assert "logging.basicConfig" in source
