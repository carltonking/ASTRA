# Contributing

## Setup

```bash
git clone <repo>
cd astra
uv sync --dev
cp .env.example .env
# Fill in API keys (at minimum: ANTHROPIC_API_KEY or OPENAI_API_KEY)
```

## Running Tests

```bash
uv run pytest tests/        # 697+ tests
uv run pytest tests/ -x     # stop on first failure
uv run ruff check src/      # lint
uv run pyright src/          # type-check
```

## Code Style

- Python: formatted with `ruff format`, linted with `ruff check`
- JavaScript/JSX: formatted with Prettier
- Type hints required for all Python functions
- No `from astra.*` imports in exported strategy templates
- All API keys from environment variables only

## Pre-commit

Install pre-commit hooks before your first commit:

```bash
pre-commit install
```

This runs ruff, pyright, and prettier automatically on every commit.

## Pull Request Process

1. Ensure all tests pass and lint is clean
2. Add tests for any new functionality
3. Update docs if public API changes
4. Open PR against `main` with a clear title and description

## Commit Messages

Use conventional commits: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`
