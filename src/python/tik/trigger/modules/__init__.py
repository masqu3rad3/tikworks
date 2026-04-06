"""The initialization file for trigger modules.

This goes through all child directories and imports all module classes that inherit from ModuleCore.
"""
from pathlib import Path
import importlib
import inspect

from tik.trigger.core.module_core import ModuleCore

classes = []
_modules_base = Path(__file__).parent

for _file in _modules_base.rglob("*.py"):
    if _file.name.startswith("_"):
        continue

    _module_name = f"{_file.parent.name}.{_file.stem}"
    _module = importlib.import_module(f"{__name__}.{_module_name}")

    for _, _obj in inspect.getmembers(_module, inspect.isclass):
        if issubclass(_obj, ModuleCore) and _obj is not ModuleCore and _obj not in classes:
            classes.append(_obj)