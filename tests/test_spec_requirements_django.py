"""Runs the unchanged spec tests (anupam360_spec/tests/test_requirements.py)
against the Django adapter (threesixty/rules/adapter.py) instead of the pure
rules, so each REQ-ID is checked against the code the app actually uses.

The spec file is executed verbatim; only its `rules.anupam_rules` import is
redirected. The pure-rules run of the same file stays in anupam360_spec/tests.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

from threesixty.rules import adapter

SPEC_FILE = Path(__file__).resolve().parent.parent / 'anupam360_spec' / 'tests' / 'test_requirements.py'

pytestmark = pytest.mark.django_db


def _load_spec_module():
    saved = {k: sys.modules.get(k) for k in ('rules', 'rules.anupam_rules')}
    sys.modules['rules'] = type(sys)('rules')
    sys.modules['rules.anupam_rules'] = adapter
    sys.modules['rules'].anupam_rules = adapter
    try:
        spec = importlib.util.spec_from_file_location('spec_requirements_on_django', SPEC_FILE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        for key, mod in saved.items():
            if mod is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = mod
    return module


_spec = _load_spec_module()

# Re-export the spec's tests into this module so pytest collects them here.
for _name, _obj in vars(_spec).items():
    if _name.startswith('test_') and callable(_obj):
        globals()[_name] = _obj
