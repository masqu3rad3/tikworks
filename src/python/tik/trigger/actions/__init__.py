"""The initialization file for trigger actions.

This goes through all child directories and imports all action classes, making them available for use in the trigger system. It uses dynamic importing to find and load all action classes that inherit from the ActionCore class, ensuring that any new actions added to the system are automatically recognized and can be used without needing to modify this initialization file.
"""
from pathlib import Path
import importlib
import inspect

from tik.trigger.core.action_core import ActionCore

classes = []
_actions_base = Path(__file__).parent

for _file in _actions_base.rglob("*.py"):
    if _file.name.startswith("_"):
        continue

    _module_name = f"{_file.parent.name}.{_file.stem}"
    _module = importlib.import_module(f"{__name__}.{_module_name}")

    for _, _obj in inspect.getmembers(_module, inspect.isclass):
        if issubclass(_obj, ActionCore) and _obj is not ActionCore and _obj not in classes:
            classes.append(_obj)
