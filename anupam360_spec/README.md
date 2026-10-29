# Anupam 360 – requirements pack

| File | What it is |
|---|---|
| `REQUIREMENTS.md` | Everything asked in the conversation, grouped by module, with REQ-IDs |
| `rules/anupam_rules.py` | The business rules as plain Python (no Django) — copy into your services layer |
| `tests/test_requirements.py` | 90 pytest checks, one or more per REQ-ID |
| `e2e/check_reference_app.py` | Runs the key rules against the original HTML app in a real browser (60 checks, including parity checks that the Python rules match the app) |

## Run
    pip install pytest playwright && playwright install chromium
    pytest -v tests                                   # rules vs requirements
    python e2e/check_reference_app.py contact_management.html   # reference app vs requirements

## Test YOUR Django build
The tests call functions in `rules/anupam_rules.py` with plain dicts. Two ways:
1. **Port the module**: keep `rules/anupam_rules.py` in your project and call it from views/serializers — the tests then guard it.
2. **Point the tests at your code**: in `tests/test_requirements.py` replace `import rules.anupam_rules as R` with a thin adapter module exposing the same function names that converts your ORM objects to the dict shapes (see REQUIREMENTS.md §3). Failing test name = broken REQ-ID.
