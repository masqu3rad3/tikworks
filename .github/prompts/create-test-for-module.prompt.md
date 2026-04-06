---
description: 'description'
---
Create the /tests/unit/test_<MODULE-NAME>.py and write unit tests for <MODULE-NAME> with 100% coverage. If you notice an obvious bug in the module, you are allowed to fix that.
- Use `pytest` for all tests.
- All tests must run in a headless Maya standalone session initialized via `tests/conftest.py`.
- Follow `pytest` naming conventions: `test_*.py`, `Test*`, `test_*`.
- Prefer exercising real Maya behavior; mocking is a last resort.
- Following template should be used for running tests: $env:PYTHONPATH="src"; mayapy -m pytest tests/unit/<testfile> --cov=<module for coverage> --cov-report=term-missing
- If mayapy is not recognized as a command, that probably means its not defined in user PATH. Warn the user to set up their environment correctly in that case.
