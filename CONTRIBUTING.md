# Contributing to Slysh!

Thank you for your interest in contributing to Slysh! We welcome bug reports, feature suggestions, documentation improvements, and code contributions.

---

## 🏛️ Architecture Constraints (Must Follow)

Slysh relies on strict process isolation to ensure high desktop responsiveness:

1. **Zero PyTorch in UI Process**:
   - The UI process (FastAPI + pywebview) runs with minimal memory footprint and **must NEVER import `torch` or `gigaam`**.
   - Heavy neural inference runs exclusively in a spawned background engine subprocess (`slysh.engine_server`).
   - We verify this architectural boundary with automated tests:
     ```powershell
     .\.venv\Scripts\python.exe -m pytest tests/test_ui_imports.py
     ```
2. **Environment & Dependencies**:
   - We use [`uv`](https://docs.astral.sh/uv/) for Python packaging and dependency management.
   - Do NOT run `uv sync` if `.venv` already exists with extras, as this may overwrite PyTorch CUDA wheels.
3. **Frontend Changes**:
   - Frontend is vanilla ES Modules without heavy bundlers.
   - Edit Tailwind styles in `web/styles/input.css` and compile using `npm run build:css`.
   - Always increment the cache-busting query parameter `?v=` in `web/index.html` after modifying JS or CSS files.

---

## 🧪 Testing

Before submitting a Pull Request, verify that all automated unit and integration tests pass:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

---

## 📝 Pull Request Guidelines

1. Fork the repository and create a descriptive branch: `git checkout -b feature/my-cool-feature`.
2. Follow Python PEP 8 style standards and type annotations.
3. Update relevant documentation in `docs/` or `README.md` / `README.ru.md` if your change affects user-facing behavior.
4. Fill out the Pull Request checklist provided in the template.
