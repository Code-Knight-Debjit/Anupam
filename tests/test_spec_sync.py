"""The rules copy used by the app must stay identical to the spec pack."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_rules_copy_matches_spec_pack():
    spec = (ROOT / 'anupam360_spec' / 'rules' / 'anupam_rules.py').read_bytes()
    app = (ROOT / 'threesixty' / 'rules' / 'anupam_rules.py').read_bytes()
    assert spec == app, 'threesixty/rules/anupam_rules.py drifted from anupam360_spec/rules — re-copy it.'
