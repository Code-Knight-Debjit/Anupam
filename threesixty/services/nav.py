"""Server-side menu visibility per role (REQ-ROLE-03/04, REQ-RPT-01).

The SPA only *renders* what this returns; the endpoints behind each menu
enforce the same rule independently (Admin-only resources use `_require_admin`).
"""
from ..models import EmployeeProfile
from ..permissions import RoleRules
from ..rules import anupam_rules as rules

ROLE_NAMES = dict(EmployeeProfile.ROLE_CHOICES)


def spec_user(user, *, pk=None):
    """The dict shape `rules/anupam_rules.py` expects for a user."""
    role = RoleRules.role(user)
    return {'id': str(pk if pk is not None else user.pk), 'name': user.get_full_name() or user.username,
            'role': ROLE_NAMES.get(role, '')}


def visible_nav(user):
    return rules.nav_visible(spec_user(user))


def visible_report_tabs(user):
    return rules.report_tabs_visible(spec_user(user))
