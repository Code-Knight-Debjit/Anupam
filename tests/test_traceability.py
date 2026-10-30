"""Every requirement ID in REQUIREMENTS.md must be referenced by at least one test
(in a test name or its docstring). A new requirement without a test fails here."""
import glob
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Browser-only behaviour of the reference HTML app (a warning banner when browser storage is blocked);
# the Django build stores everything in the database, so there is nothing to test.
NOT_APPLICABLE = {'REQ-STO-01'}


def test_every_requirement_has_a_test():
    ids = set(re.findall(r'REQ-[A-Z]+-(?:\d+[a-z]?|GAP)', (ROOT / 'anupam360_spec' / 'REQUIREMENTS.md').read_text()))
    text = ''.join(Path(f).read_text() for f in glob.glob(str(ROOT / 'tests' / 'test_*.py')) if not f.endswith('test_traceability.py'))
    text += (ROOT / 'anupam360_spec' / 'tests' / 'test_requirements.py').read_text()
    missing = sorted(i for i in ids - NOT_APPLICABLE if i not in text and i.replace('-', '_') not in text)
    assert not missing, f'No test mentions: {missing}'
