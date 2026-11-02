# Parity harness (Anupam 360 vs `contact_management.html`)

Dev-only tooling; not part of the pytest suite and not needed in production. See `docs/360/PARITY_PLAN.md`.

```bash
export PARITY_DIR=/tmp/anupam-parity && mkdir -p $PARITY_DIR
python -m venv $PARITY_DIR/pw && $PARITY_DIR/pw/bin/pip install playwright   # uses the system Chrome

# 1. reference app (static file) on :8020
(cd /path/to/dir/with/html && python -m http.server 8020 --bind 127.0.0.1 &)
# 2. 360 on a THROW-AWAY database on :8010 (never db.sqlite3)
export DEBUG=True DB_NAME=$PARITY_DIR/test360.sqlite3 SECURE_SSL_REDIRECT=False SESSION_COOKIE_SECURE=False CSRF_COOKIE_SECURE=False
python manage.py migrate && python manage.py seed_threesixty
# 3. one dataset into both apps
#    (first create the reference admin once in the page: admin / secret1, then save base_backup.json = buildBackupObject())
$PARITY_DIR/pw/bin/python tests/parity/mkseed.py          # writes seed.json
$PARITY_DIR/pw/bin/python tests/parity/seed_reference.py  # into the reference's storage
python manage.py import_360_backup $PARITY_DIR/seed.json  # into 360; then set the users' passwords to harness.PW
python manage.py runserver 127.0.0.1:8010 --noreload &
# 4. snapshot + diff
$PARITY_DIR/pw/bin/python tests/parity/snapshot.py ref
$PARITY_DIR/pw/bin/python tests/parity/snapshot.py app
$PARITY_DIR/pw/bin/python tests/parity/diff_outline.py -v
```
