# Developer Commands — TikWorks

## Overview
This file documents the command patterns and templates used in TikWorks development.

**Note:** The tik package is at `src/python/tik/`. PYTHONPATH should include `src/python` not just `src`.

---

## Testing Commands

### Run Unit Tests (Maya Standalone)
```powershell
$env:PYTHONPATH="src/python"; mayapy -m pytest tests/unit/<testfile> --cov=<module> --cov-report=term-missing
```

### Run All Tests
```powershell
$env:PYTHONPATH="src/python"; mayapy -m pytest tests/ --cov=src --cov-report=term-missing
```

### Per-Test Coverage (requires confirmation)
```powershell
# Use the helper script
.\per_test_coverage_helper.ps1 -Mode sample  # Quick estimate
.\per_test_coverage_helper.ps1 -Mode full    # Full run (requires YES confirmation)
```

### Run Specific Test
```powershell
$env:PYTHONPATH="src/python"; mayapy -m pytest tests/unit/test_<module>.py::TestClass::test_name -v
```

### Run tik.trigger Core Tests
```powershell
$env:PYTHONPATH="src/python"; mayapy -m pytest tests/unit/test_*_trigger.py -v
```

---

## Linting Commands

### Black Formatting
```bash
black src/python/
```

### Flake8 Linting
```bash
flake8 src/python/ --max-line-length=88
```

### Auto-fix Imports
```bash
isort src/python/
```

### Full Style Check
```bash
black --check src/python/ && flake8 src/python/ && isort --check src/python/
```

---

## Maya Python (mayapy)

If `mayapy` is not on PATH:
```powershell
# Add Maya's mayapy to PATH (adjust path to your Maya installation)
$env:PATH = "C:\Program Files\Autodesk\Maya2024\bin;$env:PATH"
```

Or run directly:
```powershell
"C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe" -m pytest tests/unit/test_module.py
```

---

## Git Commands

### Create Feature Branch
```bash
git checkout -b feature/tik-trigger-setup
```

### Check Status
```bash
git status
```

### Stage Files
```bash
git add path/to/file.py
```

### Commit
```bash
git commit -m " Descriptive commit message"
```

---

## Documentation

### Build Docs
```bash
cd docs && make html
```

### Watch Mode (Sphinx)
```bash
cd docs && sphinx-autobuild source build/html
```

---

## Environment Variables

| Variable | Value | Purpose |
|----------|-------|---------|
| `PYTHONPATH` | `src/python` | For importing `tik` package |
| `MAYA_APP_DIR` | varies | Maya preference directory |

---

## Common Workflows

### Implement New Action in tik.trigger
1. Create folder: `src/python/tik/trigger/actions/my_action/`
2. Create `my_action.py` with class inheriting from `ActionCore`
3. Apply `@register_action("my_action")` decorator
4. Create `ui_definition.json` (optional)
5. Create `defaults.json` (optional)
6. Write tests under `tests/unit/test_action_<name>.py`

### Implement New Module in tik.trigger
1. Create folder: `src/python/tik/trigger/modules/my_module/`
2. Create `my_module.py` with `MyModuleGuide(GuidesCore)` and `MyModule(ModuleCore)`
3. Apply `@register_module("my_module")` decorator
4. Create `data.json` with module-specific data
5. Create `ui_definition.json` (optional)
6. Write tests under `tests/unit/test_module_<name>.py`

### Implement New tik.trigger Core Module
1. Create `src/python/tik/trigger/core/<module_name>.py`
2. Implement module with full type hints and docstrings
3. Export symbols in `src/python/tik/trigger/core/__init__.py`
4. Write tests: `tests/unit/test_<module_name>_trigger.py`
5. Verify: `mayapy -m pytest tests/unit/test_<module_name>_trigger.py -v`

### Propose New tik.maya API
1. Create a proposal file
2. Invoke `tikmaya_api_agent` via Skill tool
3. Wait for proposal review
4. Implement after approval
