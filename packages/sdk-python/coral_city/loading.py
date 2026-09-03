"""Finding the controller somebody wrote, from a file or a module."""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import pathlib
import sys

from .controller import Controller


def controller_from(spec: str) -> type[Controller]:
    """`path/to/file.py[:Class]` or `module[:Class]`."""
    where, _, wanted = spec.partition(":")
    if where.endswith(".py") or "/" in where:
        path = pathlib.Path(where).resolve()
        if not path.exists():
            raise SystemExit(f"no such file: {path}")
        name = path.stem
        loaded = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(loaded)
        sys.modules[name] = module
        loaded.loader.exec_module(module)
    else:
        module = importlib.import_module(where)

    if wanted:
        found = getattr(module, wanted, None)
        if found is None or not (inspect.isclass(found) and issubclass(found, Controller)):
            raise SystemExit(f"{where} has no controller called {wanted}")
        return found

    candidates = [
        value for value in vars(module).values()
        if inspect.isclass(value) and issubclass(value, Controller)
        and value is not Controller and value.__module__ == module.__name__
    ]
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise SystemExit(f"{where} defines no Controller subclass")
    names = ", ".join(c.__name__ for c in candidates)
    raise SystemExit(f"{where} defines several controllers ({names}); say which with {where}:Name")
