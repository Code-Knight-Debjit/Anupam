"""Shared helpers for the Anupam 360 tests."""
import json

from django.contrib.auth.models import User
from django.test import Client

from threesixty.models import Branch, Contact, Customer, EmployeeProfile
from threesixty.services.accounts import limit_stock_access

PASSWORD = 'secret-pw-1'
ADMIN, BM, BS, SM = (EmployeeProfile.ADMIN, EmployeeProfile.BRANCH_MANAGER,
                     EmployeeProfile.BRANCH_STAFF, EmployeeProfile.SALES_MANAGER)


def make_employee(username, role, branches=(), full_name='', **profile_kwargs):
    user = User.objects.create_user(username=username, password=PASSWORD, is_staff=True, first_name=full_name or username.title())
    limit_stock_access(user)
    profile = EmployeeProfile.objects.create(user=user, role=role, **profile_kwargs)
    if branches:
        profile.branches.set(branches)
    return user


def client_for(user_or_name):
    username = getattr(user_or_name, 'username', user_or_name)
    c = Client()
    assert c.login(username=username, password=PASSWORD)
    return c


def call(client, method, url, data=None):
    kwargs = {'content_type': 'application/json'}
    if data is not None or method in ('post', 'patch', 'put'):
        kwargs['data'] = json.dumps(data or {})
    return getattr(client, method)(url, **kwargs)


def make_customer(name='Sun Steels', creator=None, contacts=('Ravi', 'Meena', 'Joe', 'Anu'), **kwargs):
    c = Customer.objects.create(name=name, created_by=creator, **kwargs)
    made = [Contact.objects.create(customer=c, name=n, phone=f'98400{i:05d}', email=f'{n.lower()}@x.com')
            for i, n in enumerate(contacts)]
    return c, made
