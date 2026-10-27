"""Pre-launch check: do concurrent requests ever get the same document number?

Fires many threads at `allocate_next_number` (each thread has its own DB
connection, like separate Gunicorn workers) and verifies every number issued
is unique and the sequence has no gaps. Only meaningful on a database with
real row locking (Postgres) — on SQLite writers are serialised anyway, so it
refuses to run there unless --allow-sqlite is given.

Usage (staging stack):
    docker compose -p staging run --rm web python manage.py check_360_numbering_concurrency

Uses a throwaway branch and deletes it (and its counters) afterwards.
"""
import threading
from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, connections

from threesixty.models import Branch, BranchNumbering
from threesixty.services.numbering import allocate_next_number, bump_counter_to

DOC_TYPE = BranchNumbering.DOC_TYPES[1][0]  # quotation
BRANCH_NAME = '__numbering_concurrency_check__'


class Command(BaseCommand):
    help = 'Verify doc-number allocation is race-free under concurrent workers.'

    def add_arguments(self, parser):
        parser.add_argument('--threads', type=int, default=20)
        parser.add_argument('--per-thread', type=int, default=25)
        parser.add_argument('--allow-sqlite', action='store_true')

    def handle(self, *args, **options):
        if connection.vendor == 'sqlite' and not options['allow_sqlite']:
            raise CommandError('Running on SQLite proves nothing about locking; point DB_* at Postgres.')
        if Branch.objects.filter(name=BRANCH_NAME).exists():
            raise CommandError(f'Branch {BRANCH_NAME!r} already exists (leftover from a crashed run?). Delete it first.')

        threads_n, per_thread = options['threads'], options['per_thread']
        branch = Branch.objects.create(name=BRANCH_NAME)
        self.stdout.write(f'{connection.vendor}: {threads_n} threads x {per_thread} allocations on branch {branch.pk}')
        try:
            numbers, errors = self._run(branch, threads_n, per_thread)
            self._report(numbers, errors, threads_n * per_thread)
            self._check_manual_bump(branch)
        finally:
            BranchNumbering.objects.filter(branch=branch).delete()
            branch.delete()

    def _run(self, branch, threads_n, per_thread):
        numbers, errors = [], []
        lock = threading.Lock()
        start = threading.Barrier(threads_n)

        def worker():
            try:
                start.wait()  # release all threads together to maximise contention
                for _ in range(per_thread):
                    number = allocate_next_number(branch, DOC_TYPE)
                    with lock:
                        numbers.append(number)
            except Exception as exc:  # noqa: BLE001 - reported, not swallowed
                with lock:
                    errors.append(repr(exc))
            finally:
                connections.close_all()

        threads = [threading.Thread(target=worker) for _ in range(threads_n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        return numbers, errors

    def _report(self, numbers, errors, expected):
        duplicates = {n: c for n, c in Counter(numbers).items() if c > 1}
        if errors:
            raise CommandError(f'{len(errors)} worker(s) crashed, e.g. {errors[0]}')
        if duplicates:
            sample = dict(list(duplicates.items())[:5])
            raise CommandError(f'FAIL: {len(duplicates)} duplicate number(s) issued, e.g. {sample}')
        if len(numbers) != expected:
            raise CommandError(f'FAIL: expected {expected} numbers, got {len(numbers)}')
        seqs = sorted(int(''.join(ch for ch in n if ch.isdigit())) for n in numbers)
        if seqs != list(range(seqs[0], seqs[0] + expected)):
            raise CommandError('FAIL: sequence has gaps.')
        self.stdout.write(self.style.SUCCESS(
            f'OK: {expected} unique, gap-free numbers ({numbers[0]} … range {seqs[0]}-{seqs[-1]}).'))

    def _check_manual_bump(self, branch):
        """A hand-typed higher number must push the counter forward."""
        bump_counter_to(branch, DOC_TYPE, 'QUO-5000')
        following = allocate_next_number(branch, DOC_TYPE)
        if '5001' not in following:
            raise CommandError(f'FAIL: after a manual QUO-5000 the next number was {following!r}, expected …5001.')
        self.stdout.write(self.style.SUCCESS(f'OK: manual number bumps the counter (next was {following}).'))
