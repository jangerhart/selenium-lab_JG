# AGENTS.md

This repository contains the Sandix competitor price monitoring project.

- `Sandix/` is the active Python project; avoid broad changes outside it unless the user asks for them.
- The repo root also contains older utility scripts and data; do not assume they are part of Sandix.
- Before architectural or database-related changes, read `Sandix/docs/PROJECT_CONTEXT.md` and `Sandix/docs/HANDOFF.md`.
- Database access for analysis is read-only unless explicitly approved.
- For PostgreSQL analysis, use the existing read-only role `price_scraper_ro`.
- Never commit `.env`, passwords, or database credentials.
- After every meaningful completed task, update `Sandix/docs/HANDOFF.md`.
- `Sandix/docs/HANDOFF.md` must cover: current state, files changed, database objects inspected or changed, tests executed, results, unresolved issues, and the recommended next step.
- Do not delete previous important architectural decisions from `Sandix/docs/PROJECT_CONTEXT.md`.
- Sandix entrypoints: `python -m sandix` or installed CLI `sandix` from `Sandix/pyproject.toml`.
- Sandix tests: `python -m unittest discover -s tests` from `Sandix/`.
- Profibagr scraper lives in `Sandix/profibagr-scraper/profibagr_scraper.py`.
- Scraper batch mode reads PostgreSQL queue data via `.env` values loaded by `python-dotenv`; copy `Sandix/profibagr-scraper/.env.example` to `.env` and use the read-only user shown there.
- Scraper manual mode is `python3 profibagr_scraper.py --part-number "..."`; `--part-number` can be repeated.
- Scraper output is written under `Sandix/profibagr-scraper/data/raw/profibagr/` and logs under `Sandix/profibagr-scraper/logs/`; both are ignored by the scraper-local `.gitignore`.
- The scraper-local `.gitignore` does not cover `.venv/`; keep virtualenvs out of commits.
