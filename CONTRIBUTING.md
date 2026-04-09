# Contributing to JDG Ksiegowy

Thanks for your interest in contributing!

## How to contribute

1. **Fork** the repository
2. **Create a branch** (`git checkout -b feature/my-feature`)
3. **Make changes** and test them
4. **Submit a PR** with a clear description

## Areas where help is needed

- Support for *zasady ogolne* and *podatek liniowy* tax forms
- Invoice cost tracking (VAT input deduction for JPK)
- PIT-28 annual declaration generator
- Integration tests with KSeF test environment
- Web UI dashboard for invoice/tax overview
- More OpenClaw skill templates
- Documentation translations

## Code style

- Python 3.12+, type hints everywhere
- `Decimal` for all monetary values (never `float`)
- Ruff for linting (`ruff check .`)
- Tax calculations must be deterministic (in Python, not AI-generated)

## Tax knowledge

If you're contributing tax calculation logic:
- ZUS rates are defined in `src/jdg_ksiegowy/tax/zus.py` (single source of truth)
- Always cite the legal basis (e.g., "art. 12 ustawy o ryczalcie")
- Test with real-world examples from official tax calculators

## Running tests

```bash
pip install -e ".[dev]"
pytest
ruff check .
```

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
