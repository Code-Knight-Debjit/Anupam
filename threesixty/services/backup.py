"""Backup & restore (REQ-BAK-01, REQUIREMENTS §25) — Admin only.

A backup is one JSON file with every dataset. Restore first writes a safety copy
of the CURRENT data (outside the web-served media folder: it contains password
hashes), then replaces everything in a single transaction — if anything is
wrong the database is left exactly as it was. Uploaded images are referenced by
file name only; the image files themselves are not part of the JSON. The audit log is append-only:
it is neither exported nor touched by a restore. Aadhaar / PAN stay encrypted inside the file.
"""
import json
from datetime import datetime
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import serializers
from django.core.serializers.base import DeserializationError
from django.core.management.color import no_style
from django.db import connection, transaction
from django.utils import timezone

from ..models import EmployeeProfile
from ..rules import anupam_rules as rules
from .errors import ServiceError

User = get_user_model()
FORMAT = 1
MAX_BYTES = 50 * 1024 * 1024

# dataset (spec BACKUP_KEYS name) -> models, parents before children
DATASETS = [
    ('branches', ['Branch']),
    ('docCounters', ['BranchNumbering']),
    ('employees', ['EmployeeProfile']),            # + the auth users they belong to, handled separately
    ('sources', ['LookupItem']),                    # all pick-lists (sources, industries, brands, ... languages, transport, courier)
    ('salesPersons', ['SalesPerson']),
    ('holidays', ['Holiday']),
    ('attendanceStart', ['SiteSetting']),
    ('companies', ['Customer', 'Contact', 'ContactAccess', 'Interaction']),
    ('salesDocs', ['SalesDocument', 'SalesDocumentItem', 'SupplyLogEntry', 'InvoiceLogEntry', 'DocumentCallLog']),
    ('payments', ['PaymentCollection', 'PaymentReceipt', 'PaymentContactLog']),
    ('tasks', ['Task']),
    ('callAssignments', ['CallAssignment', 'CallAttempt']),
    ('notifications', ['Notification']),
    ('approvals', ['ApprovalRequest']),
    ('attendance', ['AttendanceRecord']),
    ('leaveRequests', ['LeaveRequest']),
    ('stockProducts', ['StockProduct']),
    ('suppliers', ['Supplier']),
    ('stockBills', ['StockBill']),
    ('stockTransactions', ['StockTransaction']),
]
# Spec datasets whose data is held in the models above under another name.
ALIASES = {'jobTitles': 'sources', 'industries': 'sources', 'brands': 'sources', 'products': 'sources', 'categories': 'sources', 'units': 'sources',
           'taxRates': 'sources', 'paymentTerms': 'sources', 'languages': 'sources', 'transportList': 'sources', 'courierList': 'sources'}
USER_FIELDS = ('username', 'first_name', 'last_name', 'email', 'is_active', 'is_staff', 'password', 'last_login', 'date_joined')


def _model(name):
    return apps.get_model('threesixty', name)


def backup_dir() -> Path:
    path = Path(settings.BACKUP_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def build_backup(created_by=None) -> dict:
    datasets = {}
    for key, names in DATASETS:
        rows = []
        for name in names:
            rows += json.loads(serializers.serialize('json', _model(name).objects.all().order_by('pk')))
        datasets[key] = rows
    users = User.objects.filter(threesixty_profile__isnull=False).order_by('pk')
    user_rows = [{'pk': u.pk, **{f: getattr(u, f) for f in USER_FIELDS}} for u in users]
    for row in user_rows:                      # datetimes -> text
        for f in ('last_login', 'date_joined'):
            row[f] = row[f].isoformat() if row[f] else None
    return {'app': 'anupam360', 'format': FORMAT, 'created_at': timezone.now().isoformat(),
            'created_by': getattr(created_by, 'username', ''), 'users': user_rows, 'datasets': datasets,
            'counts': {k: len(v) for k, v in datasets.items()} | {'users': len(user_rows)}}


def dump(backup: dict) -> bytes:
    return json.dumps(backup, indent=1, ensure_ascii=False).encode('utf-8')


def write_safety_copy(created_by=None) -> Path:
    path = backup_dir() / f'safety-copy-{timezone.localtime():%Y%m%d-%H%M%S}.json'
    path.write_bytes(dump(build_backup(created_by)))
    path.chmod(0o600)
    return path


# --------------------------------------------------------------------------- reading a file
def parse(raw: bytes) -> dict:
    if len(raw) > MAX_BYTES:
        raise ServiceError(400, 'That backup file is too large.')
    try:
        data = json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, ValueError):
        raise ServiceError(400, 'That file is not a valid backup (not JSON).')
    if not isinstance(data, dict) or data.get('app') != 'anupam360' or not isinstance(data.get('datasets'), dict):
        raise ServiceError(400, 'That file is not an Anupam 360 backup.')
    if data.get('format') != FORMAT:
        raise ServiceError(400, f'Unsupported backup format {data.get("format")!r} (this version reads format {FORMAT}).')
    return data


def describe(data: dict) -> dict:
    """What the file contains, and which datasets an older backup lacks."""
    present = {k: len(v) for k, v in data['datasets'].items()}
    known = [k for k, _ in DATASETS]
    missing_from_file = [k for k in known if k not in data['datasets']]
    spec_keys = [k for k in rules.BACKUP_KEYS if k not in ALIASES]
    return {'created_at': data.get('created_at'), 'created_by': data.get('created_by'), 'users': len(data.get('users', [])),
            'contains': present, 'missing': missing_from_file,
            'unknown': [k for k in data['datasets'] if k not in known],
            'note': 'Datasets listed under "missing" are not in this backup: restoring leaves them empty.',
            'spec_datasets': spec_keys}


# --------------------------------------------------------------------------- restoring
def _check_users(data, actor):
    rows = data.get('users') or []
    if not any(r['username'] == actor.username for r in rows):
        raise ServiceError(400, 'Your own account is not in this backup. Restoring it would lock you out, so it was refused.')
    profile_rows = data['datasets'].get('employees', [])
    admin_pks = {p['fields'].get('user') for p in profile_rows if p['fields'].get('role') == EmployeeProfile.ADMIN}
    by_name = {r['username']: r['pk'] for r in rows}
    if by_name[actor.username] not in admin_pks:
        raise ServiceError(400, 'In this backup your account is not an Admin. Restoring it would lock you out, so it was refused.')
    for r in rows:
        clash = User.objects.filter(pk=r['pk']).exclude(username=r['username']).first()
        if clash:
            raise ServiceError(400, f'User id {r["pk"]} in the backup belongs to "{r["username"]}" but here it is "{clash.username}". '
                                    'Restore into the database the backup came from.')


def _sequences(models):
    with connection.cursor() as cursor:
        for sql in connection.ops.sequence_reset_sql(no_style(), models):
            cursor.execute(sql)


@transaction.atomic
def restore(data: dict, actor) -> dict:
    """Replace all 360 data with the backup's. Returns the counts restored.
    The caller must have written the safety copy first."""
    _check_users(data, actor)
    for key, names in reversed(DATASETS):
        for name in reversed(names):
            _model(name).objects.all().delete()
    # users: update in place by username (never delete a login row; history keeps its author)
    for row in data.get('users') or []:
        fields = {f: row[f] for f in USER_FIELDS if f in row}
        for f in ('last_login', 'date_joined'):
            fields[f] = datetime.fromisoformat(fields[f]) if fields.get(f) else None
        fields.setdefault('date_joined', timezone.now())
        if fields['date_joined'] is None:
            fields['date_joined'] = timezone.now()
        User.objects.update_or_create(pk=row['pk'], defaults=fields)
    restored = {}
    touched = []
    for key, names in DATASETS:
        rows = data['datasets'].get(key) or []
        if not rows:
            continue
        try:
            for obj in serializers.deserialize('json', json.dumps(rows), ignorenonexistent=True):
                obj.save()
        except (DeserializationError, KeyError, TypeError, ValueError) as exc:
            # raising inside @transaction.atomic rolls the whole restore back
            raise ServiceError(400, f'The backup file is damaged in "{key}" ({exc.__class__.__name__}); nothing was changed.')
        restored[key] = len(rows)
        touched += [_model(n) for n in names]
    if touched:
        _sequences(touched + [User])
    return restored
