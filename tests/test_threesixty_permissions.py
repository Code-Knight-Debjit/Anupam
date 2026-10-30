"""Phase 1 — permission tests for threesixty.RoleRules and the
staff_360_required/role_360_required decorators.

Verifies the exact rules found in contact_management.html (~L4252-4280,
~L10176) — see docs/360/AUDIT.md §3. Any change to these assertions must be
justified by re-reading the original source, not by "it seems reasonable".
"""
import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from threesixty.models import Branch, EmployeeProfile, SalesDocument, Customer
from threesixty.permissions import RoleRules

pytestmark = pytest.mark.django_db


def make_employee(username, role, branches=()):
    user = User.objects.create_user(username=username, password='x', is_staff=True)
    profile = EmployeeProfile.objects.create(user=user, role=role)
    if branches:
        profile.branches.set(branches)
    return user


@pytest.fixture
def chennai():
    return Branch.objects.create(name='Chennai')


@pytest.fixture
def bengaluru():
    return Branch.objects.create(name='Bengaluru')


class TestRoleRules:
    def test_admin_role_flags(self, chennai):
        user = make_employee('admin1', EmployeeProfile.ADMIN, [chennai])
        assert RoleRules.is_admin(user)
        assert not RoleRules.is_branch_manager(user)
        assert RoleRules.can_see_dashboard(user)
        assert not RoleRules.uses_personal_dashboard(user)
        assert RoleRules.can_direct_edit_delete(user)
        assert RoleRules.can_edit_customer_direct(user)
        assert RoleRules.can_delete_customer_direct(user)
        assert RoleRules.can_direct_edit_delete_sales_doc(user)

    def test_branch_manager_role_flags(self, chennai):
        user = make_employee('bm1', EmployeeProfile.BRANCH_MANAGER, [chennai])
        assert RoleRules.is_branch_manager(user)
        assert RoleRules.uses_personal_dashboard(user)
        assert RoleRules.can_direct_edit_delete(user)
        assert RoleRules.can_delete_customer_direct(user)

    def test_branch_staff_cannot_delete_customer_directly(self, chennai):
        """§3 footnote: canDeleteCustomerDirect = isAdmin() || isBranchManager()
        only — Branch Staff can edit but NOT delete a customer directly."""
        user = make_employee('staff1', EmployeeProfile.BRANCH_STAFF, [chennai])
        assert RoleRules.can_edit_customer_direct(user)
        assert not RoleRules.can_delete_customer_direct(user)
        # but Branch Staff CAN edit/delete sales docs directly (canDirectEditDeleteSalesDoc)
        assert RoleRules.can_direct_edit_delete_sales_doc(user)

    def test_sales_manager_cannot_edit_delete_customers_or_sales_docs_directly(self, chennai):
        user = make_employee('sm1', EmployeeProfile.SALES_MANAGER, [chennai])
        assert not RoleRules.can_edit_customer_direct(user)
        assert not RoleRules.can_delete_customer_direct(user)
        assert not RoleRules.can_direct_edit_delete_sales_doc(user)
        assert RoleRules.uses_personal_dashboard(user)

    def test_REQ_ROLE_02_sales_manager_quotation_edits_go_through_approval_like_enquiries(self, chennai):
        """REQUIREMENTS §1 / REQ-ROLE-02 (the spec pack wins over the older audit
        note about ~L10176): a Sales Manager's edit or delete of ANY sales
        document, quotations included, queues an approval request."""
        user = make_employee('sm2', EmployeeProfile.SALES_MANAGER, [chennai])
        assert RoleRules.needs_approval(user, 'salesdoc.edit') and RoleRules.needs_approval(user, 'salesdoc.delete')

    def test_manager_scope_includes_only_overlapping_branch_staff(self, chennai, bengaluru):
        manager = make_employee('bm2', EmployeeProfile.BRANCH_MANAGER, [chennai])
        same_branch_staff = make_employee('staff2', EmployeeProfile.BRANCH_STAFF, [chennai])
        other_branch_staff = make_employee('staff3', EmployeeProfile.BRANCH_STAFF, [bengaluru])

        scope = RoleRules.user_ids_in_manager_scope(manager)
        assert manager.pk in scope
        assert same_branch_staff.pk in scope
        assert other_branch_staff.pk not in scope


class TestStaff360Decorator:
    def test_unauthenticated_redirects_to_login(self, client):
        resp = client.get(reverse('threesixty:index'))
        assert resp.status_code == 302
        assert '/360/login/' in resp.url

    def test_non_staff_user_redirects_to_login(self, client):
        User.objects.create_user(username='nonstaff', password='x', is_staff=False)
        client.login(username='nonstaff', password='x')
        resp = client.get(reverse('threesixty:index'))
        assert resp.status_code == 302
        assert '/360/login/' in resp.url

    def test_staff_without_employee_profile_gets_403(self, client):
        User.objects.create_user(username='staffnoprofile', password='x', is_staff=True)
        client.login(username='staffnoprofile', password='x')
        resp = client.get(reverse('threesixty:index'))
        assert resp.status_code == 403

    def test_staff_with_employee_profile_gets_200(self, client, chennai):
        make_employee('staffwithprofile', EmployeeProfile.BRANCH_STAFF, [chennai])
        client.login(username='staffwithprofile', password='x')
        resp = client.get(reverse('threesixty:index'))
        assert resp.status_code == 200
