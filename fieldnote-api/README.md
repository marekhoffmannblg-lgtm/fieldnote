# FIELDNOTE local API

Local FastAPI adapter for the existing Python research pipeline. It does not
reimplement the pipeline and it never exposes API keys to the browser.

## Run

```bash
./fieldnote-api/.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000 --app-dir fieldnote-api
```

The API accepts requests only from the local FIELDNOTE Vite application.

## Endpoints

- `GET /api/health`
- `POST /api/research/preview`
- `POST /api/research/run`
- `GET /api/runs/{run_id}`
- `POST /api/runs/{run_id}/retry`

Run manifests and redacted log tails are stored in `fieldnote-api/runs/`.
