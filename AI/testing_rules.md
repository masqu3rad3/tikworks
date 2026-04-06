# Testing Rules — TikWorks

## Overview
Testing in TikWorks follows strict conventions to ensure Maya compatibility and real behavior verification.

---

## Core Rules

### Test Framework
- **pytest** is the only permitted test framework
- All tests must run under Maya standalone (`mayapy`)

### Test Location
- Unit tests: `tests/unit/test_<module>.py`
- Integration tests: `tests/integration/`
- Test files must follow `test_*.py` naming
- For tik.trigger core: use `test_<module>_trigger.py` naming (e.g., `test_exceptions_trigger.py`)

### Test Execution
```powershell
# With PYTHONPATH set correctly (critical for tik package imports)
$env:PYTHONPATH="src/python"; mayapy -m pytest tests/unit/<testfile> --cov=<module> --cov-report=term-missing

# For tik.trigger core tests specifically
$env:PYTHONPATH="src/python"; mayapy -m pytest tests/unit/test_*_trigger.py -v
```

---

## Maya Standalone Setup

### conftest.py
All tests use the fixture in `tests/conftest.py` for Maya standalone initialization.

```python
# tests/conftest.py provides:
# - maya_standalone fixture for headless Maya
# - Unique name helpers
# - Scene cleanup helpers
```

### Fixture Usage
```python
def test_create_joint(maya_standalone):
    # maya_standalone ensures clean Maya environment
    from tik.maya import Joint
    joint = Joint.create(name="test_joint")
    assert joint.exists()
```

---

## Test Design Principles

### Real Maya Behavior
- **Prefer real Maya operations** over mocking
- Mock only when absolutely necessary and justify in comments

### Naming Conventions
- Classes: `Test<ModuleName>`
- Functions: `test_<description>`
- Use descriptive names that explain what is tested

### Deterministic Tests
- Tests must be idempotent
- Clean up Maya scene state between tests
- Use unique names to avoid namespace collisions

---

## Test Categories

### Unit Tests
- Focus on single module behavior
- Independent setup/teardown
- Fast execution

### Integration Tests
- Broader system flows
- Maya DG evaluation
- Multi-node interactions

### Example Unit Test
```python
# tests/unit/test_joint.py
import pytest

class TestJoint:
    """Test tik.maya Joint type."""

    def test_create_joint(self, maya_standalone):
        """Joint creation returns valid joint."""
        from tik.maya import Joint
        joint = Joint.create(name="test_joint")
        assert joint.exists()
        assert joint.node_type == "joint"

    def test_joint_position(self, maya_standalone):
        """Joint position can be set and queried."""
        from tik.maya import Joint
        joint = Joint.create(name="test_joint")
        joint.set_position((1.0, 2.0, 3.0))
        pos = joint.get_position()
        assert pos == pytest.approx((1.0, 2.0, 3.0))
```

---

## Per-Test Coverage

### Running Per-Test Coverage
```powershell
# Quick estimate
.\per_test_coverage_helper.ps1 -Mode sample

# Full coverage (requires YES confirmation)
.\per_test_coverage_helper.ps1 -Mode full
```

### Coverage Rules
- Full per-test coverage **requires explicit user confirmation**
- Sample/batch modes are faster for triage
- Never run full mode autonomously

### Coverage Goals
- Aim for high coverage on targeted modules
- Break into small test files if needed

---

## Test Deduplication Policy

### When to Consider Changes
- Redundant tests (TestA covers all of TestB)
- Multiple tests with duplicate setup
- Slow tests with little unique coverage

### Safe Procedure
1. Produce coverage comparison report
2. Create proposal with rationale
3. Get approval from code owner
4. Archive to `tests/_archived/` instead of deleting
5. Validate: run full suite, verify coverage

---

## Edge Cases to Handle

### Scene State Leakage
- Always tear down created nodes
- Reset namespace if testing namespace operations

### Non-Deterministic Naming
- Use unique name helpers or UUIDs
- Avoid hardcoded names that may conflict

### Maya Version Differences
- Guard version-specific behavior
- Document version requirements

### Large Data
- Use minimal geometry for tests
- Avoid large mesh data unless specifically testing mesh operations

---

## Test Maintenance

### Archival (Instead of Deletion)
```bash
# Move removed tests to archive
tests/_archived/<timestamp>_<author>/
```

### PR Documentation
- Note why tests were changed
- Include before/after coverage numbers
- Link to archived tests

---

## tik.trigger Testing Specifics

### PYTHONPATH is Critical
When testing tik.trigger core files, the `PYTHONPATH` must include `src/python`:
```powershell
$env:PYTHONPATH="src/python"
```

This is required because:
1. The `tik` package is located at `src/python/tik/`
2. Without correct PYTHONPATH, imports like `from tik.trigger.core import ActionCore` fail
3. Running via `mayapy` alone is not sufficient if PYTHONPATH is wrong

### Import Isolation for DCC-Agnostic Code
The tik.trigger `core/` package is designed to be DCC-agnostic (no Maya imports). However:
- Importing `tik.trigger.core` may still trigger `tik/__init__.py` which imports Maya
- If a module in `core/` doesn't actually import Maya-dependent code, it can be tested with regular Python
- Tests that import tik.trigger via the full package path require `mayapy`

### Test Isolation with Registries
When testing registry decorators, use `setup_method`/`teardown_method` to call `clear_registries()`:
```python
def setup_method(self):
    from tik.trigger.core.registry import clear_registries
    clear_registries()

def teardown_method(self):
    from tik.trigger.core.registry import clear_registries
    clear_registries()
```

This ensures test order independence for registry-based code.

### Abstract Class Testing
Test abstract class enforcement by verifying `TypeError` is raised:
```python
def test_cannot_instantiate_directly(self):
    with pytest.raises(TypeError) as exc_info:
        ActionCore()
    assert "abstract" in str(exc_info.value).lower()
```

---

## Related Files
- `AGENTS.md` — tikworks_tester agent definition
- `AI/coding_rules.md` — General coding standards
- `tests/conftest.py` — Maya standalone fixture
