#!/usr/bin/env bash
# Start FIELDNOTE locally on deterministic ports without sharing the terminal
# with either long-running service.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_BIN="$ROOT/fieldnote-api/.venv/bin/uvicorn"
VITE_BIN="$ROOT/fieldnote-frontend/node_modules/.bin/vite"
SUPABASE_BIN="${SUPABASE_BIN:-$(command -v supabase || true)}"
FRONTEND_MODE="${FIELDNOTE_FRONTEND_MODE:-dist}"
API_LOG="/tmp/fieldnote-api.log"
FRONTEND_LOG="/tmp/fieldnote-frontend.log"
API_PID_FILE="/tmp/fieldnote-api.pid"
FRONTEND_PID_FILE="/tmp/fieldnote-frontend.pid"
API_URL="http://127.0.0.1:8000"
API_HEALTH_URL="$API_URL/health"
FRONTEND_URL="http://127.0.0.1:5173"
SUPABASE_URL="http://127.0.0.1:54321"
SUPABASE_HEALTH_URL="$SUPABASE_URL/auth/v1/health"
PRODUCT_URL="$FRONTEND_URL/products/cybex/orfeo/sources"
PORTS=(5173 5174 8000)
WAIT_SECONDS=30
MAX_LOG_LINES=1500

say() {
  printf '%s\n' "$*"
}

listeners_for_port() {
  local port="$1"
  lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true
}

wait_for_ports_to_close() {
  local attempt port
  for ((attempt = 1; attempt <= 10; attempt++)); do
    local busy=0
    for port in "${PORTS[@]}"; do
      if [[ -n "$(listeners_for_port "$port")" ]]; then
        busy=1
      fi
    done
    [[ "$busy" -eq 0 ]] && return 0
    sleep 1
  done
  return 1
}

stop_pid_file() {
  local pid_file="$1"
  local name="$2"
  [[ -f "$pid_file" ]] || return 0
  local pid
  pid="$(tr -cd '0-9' < "$pid_file")"
  [[ -n "$pid" ]] || { rm -f "$pid_file"; return 0; }
  if kill -0 "$pid" 2>/dev/null && owns_fieldnote_process "$pid"; then
    say "Zatrzymuję $name (PID $pid)…"
    kill "$pid" 2>/dev/null || true
  elif kill -0 "$pid" 2>/dev/null; then
    say "Nie zatrzymuję PID $pid: nie należy do FIELDNOTE."
  fi
  rm -f "$pid_file"
}

owns_fieldnote_process() {
  local pid="$1"
  local command cwd
  command="$(ps -p "$pid" -o command= 2>/dev/null || true)"
  cwd="$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -1 || true)"
  [[ "$command" == *"fieldnote-api"* || "$command" == *"fieldnote-frontend"* || "$command" == *"vite"* || "$command" == *"http.server"* || "$cwd" == *"fieldnote-api"* ]] && \
    [[ -z "$cwd" || "$cwd" == "$ROOT" || "$cwd" == "$ROOT/fieldnote-api" || "$cwd" == "$ROOT/fieldnote-frontend" ]]
}

ensure_ports_available() {
  local port pid
  for port in "${PORTS[@]}"; do
    local pids
    pids="$(listeners_for_port "$port")"
    for pid in $pids; do
      if owns_fieldnote_process "$pid"; then
        say "Zatrzymuję własny proces FIELDNOTE na porcie $port (PID $pid)…"
        kill "$pid" 2>/dev/null || true
      else
        say "Port $port jest zajęty przez obcy proces (PID $pid). Nie został zatrzymany." >&2
        return 1
      fi
    done
  done
  wait_for_ports_to_close
}

service_running() {
  local pid_file="$1"
  [[ -f "$pid_file" ]] || return 1
  local pid
  pid="$(tr -cd '0-9' < "$pid_file")"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

pid_from_file() {
  local pid_file="$1"
  [[ -f "$pid_file" ]] && tr -cd '0-9' < "$pid_file" || true
}

http_ok() {
  local url="$1"
  curl -fsS --max-time 2 "$url" >/dev/null 2>&1
}

load_supabase_environment() {
  local env_output key value
  [[ -n "$SUPABASE_BIN" ]] || {
    say "Brakuje Supabase CLI. Zainstaluj CLI albo uruchom lokalny Supabase przed startem." >&2
    return 1
  }
  env_output="$(SUPABASE_TELEMETRY_DISABLED=1 "$SUPABASE_BIN" status -o env 2>/dev/null)" || {
    say "Nie udało się odczytać konfiguracji lokalnego Supabase." >&2
    return 1
  }
  while IFS='=' read -r key value; do
    value="${value%\"}"
    value="${value#\"}"
    case "$key" in
      API_URL) export SUPABASE_URL="$value" ;;
      ANON_KEY) export SUPABASE_ANON_KEY="$value" ;;
      SERVICE_ROLE_KEY) export SUPABASE_SERVICE_ROLE_KEY="$value" ;;
    esac
  done <<< "$env_output"
  [[ -n "${SUPABASE_URL:-}" && -n "${SUPABASE_ANON_KEY:-}" && -n "${SUPABASE_SERVICE_ROLE_KEY:-}" ]] || {
    say "Lokalny Supabase nie zwrócił wymaganych kluczy API." >&2
    return 1
  }
  SUPABASE_HEALTH_URL="${SUPABASE_URL%/}/auth/v1/health"
}

ensure_supabase() {
  if ! http_ok "$SUPABASE_HEALTH_URL"; then
    say "Uruchamiam lokalny Supabase…"
    SUPABASE_TELEMETRY_DISABLED=1 "$SUPABASE_BIN" start > /tmp/fieldnote-supabase.log 2>&1 || {
      say "Nie udało się uruchomić lokalnego Supabase." >&2
      tail -n 50 /tmp/fieldnote-supabase.log >&2 || true
      return 1
    }
  fi
  load_supabase_environment
  http_ok "$SUPABASE_HEALTH_URL" || {
    say "Supabase nie odpowiedział na health-check: $SUPABASE_HEALTH_URL" >&2
    return 1
  }
}

print_log_tail() {
  local label="$1"
  local path="$2"
  say ""
  say "--- Ostatnie 50 linii: $label ---"
  if [[ -f "$path" ]]; then
    tail -n 50 "$path" || true
  else
    say "Brak pliku logu: $path"
  fi
}

start_detached() {
  local pid_file="$1"
  local log_file="$2"
  local working_directory="$3"
  shift 3
  # start_new_session detaches the service from this shell and its terminal.
  # This avoids both terminal-input suspension and automatic port fallback.
  python3 - "$pid_file" "$log_file" "$working_directory" "$@" <<'PY'
import os
import subprocess
import sys

pid_file, log_file, working_directory, *command = sys.argv[1:]
with open(log_file, "ab", buffering=0) as log:
    process = subprocess.Popen(
        command,
        cwd=working_directory,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        close_fds=True,
    )
with open(pid_file, "w", encoding="utf-8") as handle:
    handle.write(f"{process.pid}\n")
PY
}

rotate_log() {
  local path="$1"
  [[ -f "$path" ]] || return 0
  local lines
  lines="$(wc -l < "$path" | tr -d ' ')"
  if [[ "$lines" -gt "$MAX_LOG_LINES" ]]; then
    tail -n "$MAX_LOG_LINES" "$path" > "${path}.next"
    mv "${path}.next" "$path"
  fi
}

stop_services() {
  stop_pid_file "$API_PID_FILE" "backend FIELDNOTE"
  stop_pid_file "$FRONTEND_PID_FILE" "frontend FIELDNOTE"
  if wait_for_ports_to_close; then
    say "FIELDNOTE zatrzymany."
  else
    say "FIELDNOTE zatrzymany; jeden z portów pozostaje zajęty przez obcy proces."
  fi
}

status_services() {
  local api_pid frontend_pid
  api_pid="$(pid_from_file "$API_PID_FILE")"
  frontend_pid="$(pid_from_file "$FRONTEND_PID_FILE")"
  if service_running "$API_PID_FILE"; then
    say "backend: running"
  else
    say "backend: stopped"
  fi
  say "backend PID: ${api_pid:-—}"
  say "backend port: 8000"
  if http_ok "$API_HEALTH_URL"; then
    say "backend healthcheck: ok"
  else
    say "backend healthcheck: failed"
  fi

  if http_ok "$SUPABASE_HEALTH_URL"; then
    say "supabase healthcheck: ok"
  else
    say "supabase healthcheck: failed"
  fi

  if service_running "$FRONTEND_PID_FILE"; then
    say "frontend: running"
  else
    say "frontend: stopped"
  fi
  say "frontend PID: ${frontend_pid:-—}"
  say "frontend port: 5173"
  if http_ok "$FRONTEND_URL"; then
    say "frontend healthcheck: ok"
  else
    say "frontend healthcheck: failed"
  fi
}

start_services() {
  local dev_mode="$1"
  if [[ ! -x "$API_BIN" ]]; then
    say "Brakuje backendowych zależności FIELDNOTE." >&2
    exit 1
  fi
  if [[ "$FRONTEND_MODE" == "dev" && ! -x "$VITE_BIN" ]]; then
    say "Brakuje zależności frontendu FIELDNOTE." >&2
    exit 1
  fi
  if [[ "$FRONTEND_MODE" == "dist" && ! -f "$ROOT/fieldnote-frontend/dist/index.html" ]]; then
    say "Brakuje buildu frontendu FIELDNOTE: fieldnote-frontend/dist/index.html." >&2
    exit 1
  fi
  ensure_supabase || exit 1

  stop_pid_file "$API_PID_FILE" "backend FIELDNOTE"
  stop_pid_file "$FRONTEND_PID_FILE" "frontend FIELDNOTE"
  if ! ensure_ports_available; then
    say "Nie udało się zwolnić wymaganych portów: ${PORTS[*]}." >&2
    exit 1
  fi

  rotate_log "$API_LOG"
  rotate_log "$FRONTEND_LOG"

  local api_command=(env FIELDNOTE_DATA_MODE=supabase SUPABASE_URL="$SUPABASE_URL" SUPABASE_ANON_KEY="$SUPABASE_ANON_KEY" SUPABASE_SERVICE_ROLE_KEY="$SUPABASE_SERVICE_ROLE_KEY" FIELDNOTE_SKIP_STARTUP_RECOVERY=1 "$API_BIN" app:app --host 127.0.0.1 --port 8000)
  if [[ "$dev_mode" == "true" ]]; then
    api_command+=(--reload)
  fi
  start_detached "$API_PID_FILE" "$API_LOG" "$ROOT/fieldnote-api" "${api_command[@]}"
  local frontend_command
  if [[ "$FRONTEND_MODE" == "dev" ]]; then
    frontend_command=("$VITE_BIN" --host 127.0.0.1 --port 5173 --strictPort)
  else
    frontend_command=(python3 -m http.server 5173 --bind 127.0.0.1 --directory "$ROOT/fieldnote-frontend/dist")
  fi
  start_detached "$FRONTEND_PID_FILE" "$FRONTEND_LOG" "$ROOT/fieldnote-frontend" "${frontend_command[@]}"
  local api_pid frontend_pid
  api_pid="$(pid_from_file "$API_PID_FILE")"
  frontend_pid="$(pid_from_file "$FRONTEND_PID_FILE")"

  local elapsed
  for ((elapsed = 0; elapsed < WAIT_SECONDS; elapsed++)); do
    if http_ok "$SUPABASE_HEALTH_URL" && http_ok "$API_HEALTH_URL" && http_ok "$FRONTEND_URL"; then
      say "FIELDNOTE uruchomiony."
      say "backend PID: $api_pid"
      say "frontend PID: $frontend_pid"
      say "backend: $API_URL"
      say "frontend: $FRONTEND_URL"
      open "$PRODUCT_URL" >/dev/null 2>&1 || say "Nie udało się automatycznie otworzyć przeglądarki: $PRODUCT_URL"
      return 0
    fi
    sleep 1
  done

  say "START NIEUDANY: backend lub frontend nie odpowiedział w ciągu ${WAIT_SECONDS} sekund." >&2
  print_log_tail "backend" "$API_LOG" >&2
  print_log_tail "frontend" "$FRONTEND_LOG" >&2
  stop_services >/dev/null 2>&1 || true
  exit 1
}

case "${1:-start}" in
  start)
    start_services false
    ;;
  dev)
    start_services true
    ;;
  stop)
    stop_services
    ;;
  status)
    status_services
    ;;
  *)
    say "Użycie: $0 [start|dev|stop|status]" >&2
    exit 2
    ;;
esac
