"""Phase 1 — tests for threesixty.services.numbering, a verified port of
`nextDocNumber`/`bumpDocCounter`/`formatDocNumber`
(contact_management.html ~L8598-8639) — see docs/360/AUDIT.md §5.4.

Note on concurrency: SQLite's `:memory:` test database is private per
connection, so a genuine multi-thread/multi-connection race test would just
see "no such table" on every thread but the first — it cannot exercise
`select_for_update()` meaningfully here. These tests therefore verify the
*sequential correctness* of the locking code path (formatting, monotonic
increase, per branch+type isolation, forward-only manual bump). Verifying
the lock actually prevents a race under real concurrent load requires
Postgres — exercise that against the Docker Compose stack (`docker compose
exec web pytest ...`), not this local sqlite run.
"""
import pytest

from threesixty.models import Branch, BranchNumbering
from threesixty.services.numbering import allocate_next_number, bump_counter_to, doc_number_seq

pytestmark = pytest.mark.django_db


@pytest.fixture
def chennai():
    return Branch.objects.create(name='Chennai')


@pytest.fixture
def bengaluru():
    return Branch.objects.create(name='Bengaluru')


class TestAllocateNextNumber:
    def test_first_number_uses_default_prefix_and_start(self, chennai):
        number = allocate_next_number(chennai, BranchNumbering.DOC_TYPES[1][0])  # quotation
        assert number == 'QUO-0001'

    def test_numbers_increase_monotonically_and_never_repeat(self, chennai):
        numbers = [allocate_next_number(chennai, 'enquiry') for _ in range(5)]
        assert numbers == ['ENQ-0001', 'ENQ-0002', 'ENQ-0003', 'ENQ-0004', 'ENQ-0005']
        assert len(set(numbers)) == 5

    def test_branches_and_doc_types_have_independent_counters(self, chennai, bengaluru):
        c1 = allocate_next_number(chennai, 'po')
        b1 = allocate_next_number(bengaluru, 'po')
        c2 = allocate_next_number(chennai, 'po')
        assert c1 == 'PO-0001'
        assert b1 == 'PO-0001'  # independent counter, not affected by Chennai's
        assert c2 == 'PO-0002'

    def test_custom_prefix_suffix_padding_format(self, chennai):
        config = BranchNumberingConfigHelper(chennai, 'dc', prefix='CHN-DC', suffix='26-27')
        number = allocate_next_number(chennai, 'dc')
        assert number == config.expected(1)


class BranchNumberingConfigHelper:
    """Small test helper that sets a custom prefix/suffix before the first
    allocation and predicts the formatted string for a given sequence."""
    def __init__(self, branch, doc_type, prefix, suffix):
        self.prefix = prefix
        self.suffix = suffix
        BranchNumbering.objects.update_or_create(
            branch=branch, doc_type=doc_type,
            defaults={'prefix': prefix, 'suffix': suffix},
        )

    def expected(self, seq):
        return f'{self.prefix}-{str(seq).zfill(4)}-{self.suffix}'


class TestBumpCounterTo:
    def test_hand_typed_higher_number_advances_counter(self, chennai):
        allocate_next_number(chennai, 'proforma')  # PI-0001
        bump_counter_to(chennai, 'proforma', 'PI-0099')
        next_number = allocate_next_number(chennai, 'proforma')
        assert next_number == 'PI-0100'

    def test_hand_typed_lower_number_does_not_move_counter_backwards(self, chennai):
        allocate_next_number(chennai, 'quotation')  # QUO-0001
        allocate_next_number(chennai, 'quotation')  # QUO-0002
        bump_counter_to(chennai, 'quotation', 'QUO-0001')  # lower than current — ignored
        next_number = allocate_next_number(chennai, 'quotation')
        assert next_number == 'QUO-0003'


class TestDocNumberSeq:
    def test_extracts_numeric_sequence(self):
        assert doc_number_seq('ENQ-0042') == 42
        assert doc_number_seq('0007') == 7
        assert doc_number_seq('') == 0
        assert doc_number_seq(None) == 0
