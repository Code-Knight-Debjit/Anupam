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
from ..rules import anupam_rules as rules

# Pending PO carries the customer's own PO number, typed by the user — the
# system never generates one (REQ-DOC-02).
NOT_GENERATED = frozenset({'po'})

# Re-exported so callers (and the spec adapter) use the one implementation.
doc_number_seq = rules.doc_number_seq


def _get_or_create_config(branch: Branch, doc_type: str) -> BranchNumbering:
    # prefix/suffix stay blank until an Admin edits them; BranchNumbering
    # applies the default prefix at format time (REQ-DOC-02: blank -> default).
    config, _ = BranchNumbering.objects.get_or_create(branch=branch, doc_type=doc_type)
    return config


def peek_next_number(branch: Branch, doc_type: str) -> str:
    """What the next number *would* be — shown pre-filled on the entry form.
    Not a reservation: the real number is taken by `allocate_next_number` at save."""
    if doc_type in NOT_GENERATED:
        return ''
    config = _get_or_create_config(branch, doc_type)
    seq = config.last_issued + 1 if config.last_issued else config.effective_config()['start']
    return config.format_number(seq)


@transaction.atomic
def allocate_next_number(branch: Branch, doc_type: str) -> str:
    """Locks the (branch, doc_type) counter row, advances it by one, and
    returns the formatted doc number. Safe under concurrent requests."""
    if doc_type in NOT_GENERATED:
        raise ValueError('Pending PO numbers are typed by the user, not generated.')
    config = _get_or_create_config(branch, doc_type)
    config = BranchNumbering.objects.select_for_update().get(pk=config.pk)
    next_seq = config.last_issued + 1 if config.last_issued else config.effective_config()['start']
    config.last_issued = next_seq
    config.save(update_fields=['last_issued'])
    return config.format_number(next_seq)


@transaction.atomic
def bump_counter_to(branch: Branch, doc_type: str, doc_number: str) -> None:
    """If a hand-typed/edited doc number's sequence is higher than what's on
    record, advance the counter to match — numbers only ever move forward,
    deleting a document never frees one up (original `bumpDocCounter`)."""
    if doc_type in NOT_GENERATED:
        return
    config = _get_or_create_config(branch, doc_type)
    config = BranchNumbering.objects.select_for_update().get(pk=config.pk)
    seq = doc_number_seq(doc_number)
    if seq > config.last_issued:
        config.last_issued = seq
        config.save(update_fields=['last_issued'])
