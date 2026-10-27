"""Record-level optimistic concurrency for the `version` field present on
Customer, SalesDocument, PaymentCollection and Task — the mutable records
multiple staff can edit at once. The original has no per-record concurrency
control at all (whole-array overwrite, see AUDIT.md §4 — "two users editing
at once silently overwrite each other"); this is the Django API's own
safety net, not a ported behaviour.
"""
from .http import ApiError


def check_version(data, instance):
    """Raises 400 if the client didn't send a version, or 409 (with the
    server's current version attached) if it's stale."""
    client_version = data.get('version')
    if client_version is None:
        raise ApiError(400, 'version is required for update.')
    try:
        client_version = int(client_version)
    except (TypeError, ValueError):
        raise ApiError(400, 'version must be an integer.')
    if client_version != instance.version:
        raise ApiError(
            409, 'This record was changed by someone else. Reload and retry.',
            current_version=instance.version,
        )
