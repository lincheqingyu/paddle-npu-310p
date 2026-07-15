# Agent Guide

## Development Rules

- Inspect the existing implementation before making changes and keep edits scoped to the requested behavior.
- Preserve user changes and do not use destructive Git commands unless explicitly requested.
- Do not commit credentials, private keys, local `.env` files, model outputs, caches, or generated analysis artifacts.
- Keep `fusion_result.json` ignored; it is an Ascend graph-fusion analysis artifact and is not needed by the service.
- The container image must be built with the repository `Dockerfile`, not with `docker commit`.
- The Dockerfile inherits the tested NPU/PaddleX base image and copies only runtime application modules into `/app`.
- Run focused checks for changed code. State clearly when an environment limitation prevents a build or runtime test.

## Development Progress

Keep this section current after material work is completed.

- The FastAPI OCR service exposes `/health` and OCR endpoints from `main.py`.
- The Dockerfile packages the service into `/app`, inherits OCR models and the Ascend runtime from the `dev-2` base image, and loads the Ascend environment before starting the service.
- `fusion_result.json` has been removed from version control and is ignored by Git and Docker builds.
- Image builds and registry publishing must be run from the Docker host; this repository does not assume Docker is available inside the application container.

## Response Style

- Answer users in Chinese unless they explicitly request another language.
- Lead with the outcome, then give only the details needed to act on it.
- Be direct about assumptions, risks, validation performed, and remaining limitations.
- Use concise Markdown. Prefer commands and file paths over vague descriptions.

## Documentation Synchronization

- Update `README.md` when API routes, request or response formats, environment variables, startup commands, model paths, or deployment behavior change.
- Update `.env.example` whenever configuration variables are added, removed, or their defaults change.
- Update `openapi.json` when the public API contract changes, if the repository continues to version that generated specification.
- Update this file when project workflow, release status, or agent instructions change.
