# Petstore importer

Imports available pets whose names start with `M` into PostgreSQL. Requires Docker Compose and internet access.

## Run with Docker

```sh
docker compose up --build
docker compose logs importer
docker compose run --rm importer   # import again
docker compose exec db psql -U petstore -d petstore -c "SELECT * FROM pets ORDER BY id;"
docker compose down                # stop, data is retained
```

The `SELECT` command uses the default database and user; adjust them if configured differently. The importer runs once and exits, PostgreSQL stays running. Logs are appended to `logs/importer.log`, `logs/api-tests.log` and `logs/postgresql.log`; test results remain after the test container is removed. `docker compose down -v` deletes the database. `scripts/` is mounted for edits; rebuild the image when dependencies change.

## Run API tests

In a separate terminal, run:

```sh
docker compose run --rm api-tests
```

Results and failures are printed and appended to `logs/api-tests.log`, with UTC start/end times, duration, and exit code (`0` means success). These are logs; a monitoring system needs a log collector or exporter to ingest them.

## Run locally (Windows PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r scripts/requirements.txt -r scripts/requirements-test.txt
docker compose up -d db
python scripts/app.py
python -m unittest discover -s scripts -p test_api.py -v
deactivate
```

Select `.venv\Scripts\python.exe` as your editor's Python interpreter. PostgreSQL is exposed only on `127.0.0.1:5432`. Locally run Python commands log to the terminal.

## Configuration

Set environment variables or use a Compose `.env` file. Defaults:

| Variable | Default | Purpose |
| --- | --- | --- |
| `PET_NAME_PREFIX` | `M` | Case-sensitive prefix; empty uses `M` |
| `PETSTORE_URL` | `https://petstore.swagger.io/v2` | API URL |
| `POSTGRES_HOST` | `localhost` locally, `db` in Compose | Database host |
| `POSTGRES_PORT` | `5432` | Database connection port |
| `POSTGRES_HOST_PORT` | `5432` | Port exposed by Compose on localhost |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | `petstore` | Database settings |

If `POSTGRES_HOST_PORT` changes, set `POSTGRES_PORT` to the same value **only for the local Python process**. PostgreSQL credentials are initialized when the volume is created; changing them later requires a database change or a new volume. Defaults are for development only.

## Behaviour

Python fetches the public API and upserts matching pets by their 64-bit ID, so repeat imports do not duplicate records. Existing records that no longer match are retained. Names are case-sensitive; length counts Unicode code points. Missing category names become `unknown`; malformed matching records are skipped.

Compose waits for PostgreSQL to be ready. API and connection failures are retried with timeouts and logged; failure exits non-zero. The database transaction is rolled back if writing fails.

The live API tests cover all `/pet` operations, response schemas, invalid requests and negative cases. They create and clean up a unique pet on the shared public service. Search tests validate the response array and our pet, rather than unrelated records other users may have malformed. The invalid-ID test accepts `400` from the specification or the `404` observed on the public server.
