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
"${PYTHON_BIN}" -m py_compile "${ROOT}/scripts/visual_snapshots.py" "${ROOT}/scripts/backfill_visual_context.py" "${ROOT}/scripts/fetch_firecrawl_offer_pages.py" "${ROOT}/scripts/product_profile_prompt.py" "${ROOT}/scripts/product_profile.py" "${ROOT}/scripts/build_product_profile_preflight.py" "${ROOT}/scripts/generate_product_profile.py" "${ROOT}/scripts/package_product_profile_review.py" "${ROOT}/scripts/rebuild_product_scope.py" "${ROOT}/scripts/rebuild_all_admin.py" "${ROOT}/fieldnote-api/services/benchmark_rebuild_service.py"

stage "Backend unit tests: lifecycle, quality and provenance"
"${PYTHON_BIN}" -m unittest discover -s "${ROOT}/tests" -p 'test_fieldnote_p*.py'

stage "Backend integration tests: API contract and durable research queue"
"${PYTHON_BIN}" -m unittest "${ROOT}/tests/test_fieldnote_api_contracts.py" "${ROOT}/tests/test_postgres_job_queue.py" "${ROOT}/tests/test_worker_leases.py" "${ROOT}/tests/test_job_cost_limits.py"

stage "Incremental product and benchmark rebuild fixtures"
"${PYTHON_BIN}" -m unittest "${ROOT}/tests/test_incremental_pipeline.py" "${ROOT}/tests/test_incremental_benchmark_rebuild.py"

stage "Category foundation: registry, migration and benchmark partition"
"${PYTHON_BIN}" -m unittest discover -s "${ROOT}/tests" -p 'test_category_foundation.py'

stage "Existing P0 and P1 checkers"
"${PYTHON_BIN}" "${ROOT}/scripts/check_p0_foundation.py"
"${PYTHON_BIN}" "${ROOT}/scripts/check_p1_quality_taxonomy.py"

stage "P2 provenance migration dry run"
"${PYTHON_BIN}" "${ROOT}/scripts/migrate_provenance_v1.py" --dry-run --all

stage "Fixture E2E: offline lifecycle and adapters"
"${PYTHON_BIN}" -m unittest discover -s "${ROOT}/tests" -p 'test_fieldnote_e2e.py'

stage "Manufacturer pipeline fixtures: shared cleaner and normalized document"
"${PYTHON_BIN}" -m unittest discover -s "${ROOT}/tests" -p 'test_manufacturer_pipeline.py'

stage "Manufacturer post-fetch lifecycle: source, product link and provenance"
"${PYTHON_BIN}" -m unittest discover -s "${ROOT}/tests" -p 'test_manufacturer_post_fetch.py'

stage "Manufacturer production hardening: terminal stages, cache and API artifacts"
"${PYTHON_BIN}" -m unittest discover -s "${ROOT}/tests" -p 'test_manufacturer_production_hardening.py'

stage "Visual source snapshots: shared HTML backfill, contracts and safety"
"${PYTHON_BIN}" -m unittest discover -s "${ROOT}/tests" -p 'test_visual_snapshots.py'

stage "AI Product Profile: source-backed offline contract"
"${PYTHON_BIN}" -m unittest discover -s "${ROOT}/tests" -p 'test_product_profile.py'

stage "Controlled manufacturer live runner: offline preflight"
"${PYTHON_BIN}" -m unittest discover -s "${ROOT}/tests" -p 'test_manufacturer_live_runner.py'

stage "Frontend typecheck, tests and build"
cd "${ROOT}/fieldnote-frontend"
npm run check

printf '\nFIELDNOTE offline check passed.\n'
