"""Per-branch, per-document-type doc numbering — atomic port of the
original `nextDocNumber`/`bumpDocCounter`/`formatDocNumber`
(contact_management.html ~L8598-8639).

The original is a pure read-then-write with no locking (fine for a single
browser tab; fatal under concurrent Gunicorn workers — see
docs/360/AUDIT.md §5.4). `allocate_next_number()` fuses "peek" and "reserve"
into one `select_for_update()`-guarded transaction instead of the original's
two separate steps (peek at save time, confirm after save), which is the
only behavioural change — a manually-typed higher doc number still needs to
push the counter forward, so `bump_counter_to()` ports that half verbatim.
"""
from django.db import transaction

from ..models import Branch, BranchNumbering

DEFAULT_PREFIX = {
    BranchNumbering.DOC_TYPES[0][0]: 'ENQ',   # enquiry
    BranchNumbering.DOC_TYPES[1][0]: 'QUO',   # quotation
    BranchNumbering.DOC_TYPES[2][0]: 'PO',    # po
    BranchNumbering.DOC_TYPES[3][0]: 'DC',    # dc
    BranchNumbering.DOC_TYPES[4][0]: 'PI',    # proforma
}


def _get_or_create_config(branch: Branch, doc_type: str) -> BranchNumbering:
    config, _ = BranchNumbering.objects.get_or_create(
        branch=branch, doc_type=doc_type,
        defaults={'prefix': DEFAULT_PREFIX.get(doc_type, '')},
    )
    return config


@transaction.atomic
def allocate_next_number(branch: Branch, doc_type: str) -> str:
    """Locks the (branch, doc_type) counter row, advances it by one, and
    returns the formatted doc number. Safe under concurrent requests."""
    config = _get_or_create_config(branch, doc_type)
    config = BranchNumbering.objects.select_for_update().get(pk=config.pk)
    next_seq = config.last_issued + 1 if config.last_issued else config.start_at
    config.last_issued = next_seq
    config.save(update_fields=['last_issued'])
    return config.format_number(next_seq)


def doc_number_seq(doc_number: str) -> int:
    """Extract the numeric sequence out of a formatted/hand-typed doc
    number — mirrors the original `docNumberSeq()`."""
    import re
    if not doc_number:
        return 0
    match = re.search(r'(\d+)', str(doc_number))
    return int(match.group(1)) if match else 0


@transaction.atomic
def bump_counter_to(branch: Branch, doc_type: str, doc_number: str) -> None:
    """If a hand-typed/edited doc number's sequence is higher than what's on
    record, advance the counter to match — numbers only ever move forward,
    deleting a document never frees one up (original `bumpDocCounter`)."""
    config = _get_or_create_config(branch, doc_type)
    config = BranchNumbering.objects.select_for_update().get(pk=config.pk)
    seq = doc_number_seq(doc_number)
    if seq > config.last_issued:
        config.last_issued = seq
        config.save(update_fields=['last_issued'])
