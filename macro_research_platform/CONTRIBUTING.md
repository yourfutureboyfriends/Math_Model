# Contributing to MACRO OS v8.0

Thank you for contributing! This document outlines our development workflow,
coding standards, and testing practices.

***

## Development Setup

### Prerequisites

- Python 3.11+
- Node.js 20+
- PostgreSQL 15+ (if using database features)

### Backend Setup

```bash
cd api
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your configuration
python main.py
```

Backend runs on http://localhost:8000

### Frontend Setup

```bash
cd frontend
npm install
cp .env.example .env.local
# Edit .env.local if needed
npm run dev
```

Frontend runs on http://localhost:3002

***

## Coding Standards

### Python (Backend)

**Style:**
- PEP 8 compliance
- Black formatting (line length: 100)
- isort for import sorting
- Type hints required for public functions
- Docstrings required (Google style)

**Naming:**
- Functions: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Private functions: `_leading_underscore`

**Error Handling:**
- Use specific exception types (ValueError, KeyError, etc.)
- Never use bare `except:` clauses
- Log errors with context: `logger.error(f"Context: {e}", exc_info=True)`
- Validate inputs at API boundary

**Best Practices:**
- Keep functions under 50 lines where possible
- Extract complex logic into helper functions
- Use dependency injection over global state
- Write tests for new features
- Use `safe_execute()` wrapper for fallback behavior

### TypeScript/React (Frontend)

**Style:**
- ESLint + Prettier
- Functional components with hooks
- TypeScript strict mode
- Explicit return types for exported functions

**Naming:**
- Components: `PascalCase`
- Hooks: `useCamelCase`
- Utilities: `camelCase`
- Constants: `UPPER_SNAKE_CASE`
- Types/Interfaces: `PascalCase`

**Best Practices:**
- Use `useApiData` hook for API calls (no direct fetch in components)
- Apply FORMAT_* constants for number formatting
- Organize components by feature domain
- One component per file
- Avoid prop drilling (use Context or store)
- Memoize expensive computations

***

## Project Structure

### Backend

```
api/
├── main.py                 # App startup (routing only, ~150 LOC)
├── routers/                # Endpoint definitions
│   ├── dashboard.py
│   ├── market.py
│   ├── signals.py
│   ├── risk.py
│   └── business.py
├── handlers/               # Business logic
├── schemas/                # Pydantic models
├── services/               # Shared services (validation, logging, etc.)
├── utils/                  # Utilities (cache, errors, helpers, formatting)
├── signalling/             # Signal generation
├── models/                 # Database models
└── tests/                  # Unit and integration tests
```

### Frontend

```
frontend/src/
├── App.tsx                 # Router (~50 LOC)
├── pages/                  # Page components
├── components/
│   ├── sections/           # Organized by domain (macro, equity, rates, risk)
│   ├── ui/                 # Reusable UI components
│   └── layout/             # Layout components
├── hooks/                  # Custom hooks
├── types/                  # TypeScript types (organized by domain)
├── lib/                    # Constants and utilities
└── store/                  # State management
```

***

## Pull Request Process

1. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**
   - Follow coding standards
   - Add/update tests
   - Update documentation

3. **Run quality checks**
   ```bash
   # Backend
   cd api
   black .
   isort .
   flake8 .
   pytest

   # Frontend
   cd frontend
   npm run lint
   npm run build
   ```

4. **Commit with clear messages**
   ```bash
   git commit -m "feat: add recession probability visualization"
   ```

5. **Push and create PR**
   ```bash
   git push origin feature/your-feature-name
   ```

***

## Testing

### Running the tests

Run everything from the project root (`macro_research_platform/`). **Never `cd api` first** —
`api/tests/conftest.py` asserts in `pytest_collection_finish` that `api/` is not on `sys.path`,
because a stale gitignored `api/database/` copy otherwise shadows the real `database/` package
and failures start depending on test order. Invoking pytest from inside `api/` dies with an
`INTERNALERROR` during collection, before a single test runs.

```bash
make test          # the offline gate: backend + torch group + frontend
make test-live     # integration checks against a backend on :8000 (start it first)
```

Or individually:

```bash
make test-backend  # pytest api/tests, excluding integration and the torch group
make test-torch    # the api/ml/institutional tests
make test-frontend # cd frontend && npx vitest run
```

The backend runs as two processes on purpose. torch ships `libiomp5.dylib` and LightGBM resolves
Homebrew's `libomp.dylib`; both export the same OpenMP symbols and dyld binds them by flat lookup,
so fitting a LightGBM model after torch is loaded segfaults the interpreter — at a test that looks
unrelated to the cause and moves between runs. `api/tests/conftest.py` fails the run with an
explanation rather than letting it crash if one process ever collects both groups. If you add a
test that imports torch, add its file to `TORCH_TESTS` in the Makefile.

Use `npx vitest run`, not `npm test`: the latter is bare `vitest`, which starts watch mode and
never exits.

### Coverage

Coverage is **not** currently enforced or measured in CI, and there is no coverage config.
`pytest-cov` and `coverage` are installed, so you can measure a slice with
`pytest api/tests/test_governance.py --cov=api.governance --cov-report=term`.

This section previously stated that coverage "should remain above 80%". That was never measured,
and it is not close: `api/` is ~86k statements, and six of the strongest test files reach about
15% of it. The best-covered cluster in the repo sits around 76%. Treat 80% as an aspiration to
ratchet towards, not a standing guarantee, and do not cite it as a reason to trust a change.

***

## Documentation

- Update docstrings for any modified public functions
- Update API.md if endpoints change
- Update CHANGELOG.md for user-facing changes
- Update ARCHITECTURE.md if system design changes

***

## Security

- Never commit secrets to the repository
- Use environment variables for sensitive configuration
- Run `pip-audit` before submitting PRs
- Follow OWASP guidelines for web application security

***

## Questions?

Open an issue or reach out to the maintainers.

Thank you for contributing to MACRO OS!
