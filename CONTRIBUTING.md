# Contributing to Apothecary

Thank you for your interest in contributing! This guide will help you get started.

## Philosophy

Apothecary values:
- **Minimal surface area** – Small, focused modules over sprawling abstractions
- **Thin wrappers** – Parts expose metadata, not business logic
- **Composition over inheritance** – Build scenes by combining primitives
- **No deprecated shims** – Clean breaks over compatibility layers

## Development Setup

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- Git
- Node.js (optional, for JSCAD viewer)

### Quick Setup

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/apothecary.git
cd apothecary

# Install all dependencies (including dev tools)
uv sync

# Verify setup
uv run apothecary system
uv run pytest -q
```

### Editor Setup

We recommend VS Code with these extensions:
- Python (ms-python.python)
- Ruff (charliermarsh.ruff)
- Black Formatter (ms-python.black-formatter)

## Code Style

We use **Ruff** for linting and **Black** for formatting:

```bash
# Format code
uv run black apothecary tests

# Lint
uv run ruff check apothecary tests

# Fix auto-fixable issues
uv run ruff check --fix apothecary tests
```

Configuration is in `pyproject.toml`. Key settings:
- Line length: 100 characters
- Target: Python 3.11

## Testing

### Unit Tests

```bash
# Run all unit tests
uv run pytest -q

# Run with coverage
uv run pytest --cov=apothecary --cov-report=term-missing

# Run specific test file
uv run pytest tests/test_api.py -v

# Run tests matching a pattern
uv run pytest -k "test_parts" -v
```

### End-to-End Tests

E2E tests use Playwright and require the server to be running:

```bash
# Terminal 1: Start server
uv run apothecary serve --port 8765

# Terminal 2: Run E2E tests
uv run apothecary test run-e2e

# With visible browser (debugging)
uv run apothecary test run-e2e --headed --slowmo 500
```

First-time E2E setup:
```bash
uv run apothecary test setup-e2e
uv run apothecary test validate-e2e
```

### All Tests

```bash
# Full test suite with aggregate summary (recommended)
uv run apothecary test all

# With coverage
uv run apothecary test all --coverage

# Stop on first failure
uv run apothecary test all --fail-fast
```

The `test all` command automatically:
1. Runs unit tests
2. Starts a test server
3. Runs E2E tests
4. Produces an aggregate summary for velocity review

## Making Changes

### Branch Naming

Use descriptive branch names:
- `feature/add-polygon-primitive`
- `fix/jscad-import-syntax`
- `docs/improve-quickstart`

### Commit Messages

Follow conventional commits:
```
feat: add polygon primitive support
fix: correct JSCAD import syntax
docs: add examples to quickstart
test: add coverage for parts API
refactor: extract viewer to separate module
```

### Pull Request Process

1. **Fork and branch** from `main`
2. **Make focused changes** – One feature or fix per PR
3. **Add tests** for new functionality
4. **Update docs** if adding features
5. **Run the full test suite** before pushing
6. **Open a PR** with a clear description

#### PR Checklist

- [ ] Tests pass (`uv run pytest -q`)
- [ ] Code is formatted (`uv run black .`)
- [ ] Linter is happy (`uv run ruff check .`)
- [ ] Documentation updated (if applicable)
- [ ] No unnecessary files included

## Adding a New Part

1. Create the SCAD file in `parts/`:
   ```
   parts/my-cool-part.scad
   ```

2. Create the wrapper in `apothecary/projects/parts/`:
   ```python
   # apothecary/projects/parts/my_cool_part.py
   from pathlib import Path
   from pydantic import BaseModel, Field
   from .base import BasePart
   from .skeleton import ROOT

   class Params(BaseModel):
       size: float = Field(10.0, gt=0)

   def create(root: Path) -> BasePart:
       return BasePart(
           name="my_cool_part",
           source_file=root / "parts" / "my-cool-part.scad",
           params_model=Params,
           category="demo",
           tags=["example"],
           description="A cool parametric part",
       )

   DEFAULT = create(ROOT)
   ```

3. Test your part:
   ```bash
   uv run apothecary parts list
   uv run apothecary parts info my_cool_part
   uv run apothecary parts render my_cool_part -o test.scad
   ```

4. Add a test in `tests/test_parts_wrappers.py`

See [docs/parts-authoring.md](docs/parts-authoring.md) for detailed guidance.

## Adding a New Primitive

1. Add the Pydantic model in `apothecary/primitives.py`
2. Add rendering logic in the model's `render()` method
3. Export from `apothecary/__init__.py`
4. Add tests in `tests/test_primitives_transforms.py`
5. Update `docs/scene-json.md` with the JSON format

## Project Structure

```
apothecary/
├── apothecary/           # Main package
│   ├── __init__.py       # Public API exports
│   ├── api.py            # FastAPI endpoints
│   ├── cli.py            # Click CLI
│   ├── primitives.py     # Cube, Sphere, Cylinder, etc.
│   ├── booleans.py       # Union, Difference, Intersection
│   ├── transforms.py     # Translate, Rotate, Scale
│   ├── scene.py          # Scene model
│   ├── viewer.py         # Web viewer rendering
│   ├── jscad.py          # JSCAD export
│   └── projects/         # Parts registry
│       └── parts/        # Part wrappers
├── parts/                # Raw .scad files
├── templates/            # Jinja2 templates
├── tests/                # Test suite
│   ├── e2e/              # Playwright E2E tests
│   └── *.py              # Unit tests
├── docs/                 # Documentation
├── examples/             # Example files
├── QUICKSTART.md         # Getting started guide
├── CONTRIBUTING.md       # This file
└── pyproject.toml        # Project configuration
```

## Getting Help

- **Questions?** Open a GitHub issue with the `question` label
- **Bugs?** Open an issue with reproduction steps
- **Ideas?** Open a discussion or issue with the `enhancement` label

## Code of Conduct

Be respectful, constructive, and inclusive. We're all here to build cool things.

---

Thank you for contributing! 🧪
