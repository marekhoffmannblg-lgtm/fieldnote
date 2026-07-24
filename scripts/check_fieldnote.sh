#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="${ROOT}/fieldnote-api/.venv/bin/python"
if [[ ! -x "${PYTHON_BIN}" ]]; then PYTHON_BIN="python3"; fi

stage() { printf '\n[FIELDNOTE CHECK] %s\n' "$1"; }

stage "Repository hygiene: tracked files contain no secrets or local artifacts"
"${PYTHON_BIN}" -m unittest discover -s "${ROOT}/tests" -p 'test_repository_hygiene.py'

stage "Python syntax and imports"
"${PYTHON_BIN}" -m py_compile "${ROOT}/fieldnote-api/app.py" "${ROOT}/fieldnote-api/contracts.py" "${ROOT}/fieldnote-api/repositories/snapshot_repository.py" "${ROOT}/fieldnote-api/services/product_service.py" "${ROOT}/fieldnote-api/routers/health.py" "${ROOT}/scripts/run_manifest.py" "${ROOT}/scripts/source_lifecycle.py" "${ROOT}/scripts/provenance_v1.py" "${ROOT}/scripts/migrate_provenance_v1.py" "${ROOT}/scripts/source_adapters.py" "${ROOT}/scripts/manufacturer_pipeline.py"

stage "Backend unit tests: lifecycle, quality and provenance"
"${PYTHON_BIN}" -m unittest discover -s "${ROOT}/tests" -p 'test_fieldnote_p*.py'

stage "Backend integration tests: versioned local API"
"${PYTHON_BIN}" -m unittest discover -s "${ROOT}/tests" -p 'test_fieldnote_api_contracts.py'

stage "Existing P0 and P1 checkers"
"${PYTHON_BIN}" "${ROOT}/scripts/check_p0_foundation.py"
"${PYTHON_BIN}" "${ROOT}/scripts/check_p1_quality_taxonomy.py"

stage "P2 provenance migration dry run"
"${PYTHON_BIN}" "${ROOT}/scripts/migrate_provenance_v1.py" --dry-run --all

stage "Fixture E2E: offline lifecycle and adapters"
"${PYTHON_BIN}" -m unittest discover -s "${ROOT}/tests" -p 'test_fieldnote_e2e.py'

stage "Manufacturer pipeline fixtures: shared cleaner and normalized document"
"${PYTHON_BIN}" -m unittest discover -s "${ROOT}/tests" -p 'test_manufacturer_pipeline.py'

stage "Controlled manufacturer live runner: offline preflight"
"${PYTHON_BIN}" -m unittest discover -s "${ROOT}/tests" -p 'test_manufacturer_live_runner.py'

stage "Frontend typecheck, tests and build"
cd "${ROOT}/fieldnote-frontend"
npm run check

printf '\nFIELDNOTE offline check passed.\n'
