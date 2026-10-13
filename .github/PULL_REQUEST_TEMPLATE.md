## Description
<!-- Briefly describe the problem solved or feature added by this PR -->

## Type of Change
- [ ] 🐛 Bug fix (non-breaking change which fixes an issue)
- [ ] ✨ New feature (non-breaking change which adds functionality)
- [ ] ⚡ Performance improvement
- [ ] 📝 Documentation update
- [ ] 🎨 UI / Frontend styling improvement

## 🏛️ Architecture & Quality Checklist
- [ ] **Process Isolation**: The UI process (FastAPI / pywebview) does **NOT** import `torch`, `gigaam`, or `torchaudio`.
- [ ] **Tests**: Verified that `.\.venv\Scripts\python.exe -m pytest tests/test_ui_imports.py` and unit tests pass.
- [ ] **Frontend**: If modifying CSS/JS, rebuilt with `npm run build:css` and bumped query parameter `?v=` in `web/index.html`.
- [ ] **Tested on Windows**: Verified behavior on Windows 10 or 11.
