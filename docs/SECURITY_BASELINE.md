# Security baseline

## What belongs in Git

Commit source code, documentation, deterministic fixtures, empty `.gitkeep`
placeholders, and `.env.example` files with blank values only. Local research
inputs, outputs, snapshots, run state, databases, virtual environments, build
artifacts and real environment files are ignored.

The offline repository hygiene test inspects the Git index. It rejects tracked
environment files, local pipeline artifacts, common database/build files and
recognisable OpenAI, Firecrawl or Bearer token values. It is part of
`scripts/check_fieldnote.sh` and CI.

## Credentials

Use process environment variables or ignored local files such as
`fieldnote-api/.env`. Never put credentials in browser variables, frontend
build output, fixtures, issue comments, logs or GitHub Actions configuration.
The current local runtime recognises `FIRECRAWL_API_KEY` and `OPENAI_API_KEY`.

If a real credential has ever been committed, included in an archive, pasted
into a ticket or exposed in a log, revoke and rotate it at the provider before
the next push. Removing the text from Git is not sufficient.

## CI

CI installs dependencies, executes the full offline gate and runs dependency
audits. It intentionally receives no live-provider secrets. Live research
remains a separately approved, controlled operation.

## Before the first push

1. Run `bash scripts/check_fieldnote.sh` locally.
2. Review `git status --short` and `git diff --cached --name-only`.
3. Confirm that the GitHub repository is private.
4. Rotate any credential that may have left the local machine.
