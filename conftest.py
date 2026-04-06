"""Root conftest.py — loaded by pytest before any other module.

Injects mock stubs for Ableton-specific C-extensions (``Live``,
``_Framework``) so that the repository root ``__init__.py``
(the Ableton Remote Script Control Surface) can be imported without a live
Ableton connection.  This must be a plain conftest.py with no imports beyond
the standard library.
"""
import sys
import types

# ---------------------------------------------------------------------------
# Stub out Ableton-specific C modules that are unavailable in CI / unit tests
# ---------------------------------------------------------------------------

def _make_mock_module(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod

if "Live" not in sys.modules:
    _make_mock_module("Live")

if "_Framework" not in sys.modules:
    _fw = _make_mock_module("_Framework")
    _cs_mod = _make_mock_module("_Framework.ControlSurface")

    class ControlSurface:  # noqa: D101 — stub
        def __init__(self, *args, **kwargs):
            pass

        def song(self):  # noqa: D102
            return None

    _cs_mod.ControlSurface = ControlSurface
    _fw.ControlSurface = _cs_mod
