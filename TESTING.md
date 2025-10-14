# Testing Documentation

This project uses Pytest along with the `pytest-asyncio`, `pytest-cov` and `pytest-mock` plugins. In depth testing guidance for `textual` apps can be found in the package [documentation](https://textual.textualize.io/guide/testing/).

## Prerequisites

- Python 3.10+
- [pytest](https://docs.pytest.org/en/stable/)
- [pytest-cov](https://pytest-cov.readthedocs.io/en/latest/) (for coverage reports)
- [rich](https://github.com/Textualize/rich) (for improved output, optional)
- All project dependencies installed (see `pyproject.toml`)

You can install the required testing tools with `uv` or `just`:

```sh
uv sync
```

```sh
just sync
```

To run the tests and generate a coverage report in the terminal:

```sh
uv run pytest --cov=picolynx --cov-report=term
```

```sh
just test
```