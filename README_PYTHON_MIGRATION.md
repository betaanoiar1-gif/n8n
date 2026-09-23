# YouTube Autonomous Growth OS — Python Runtime

This is a runtime migration, not a redesign. The original n8n workflow remains the source of truth in `workflow_source.json`.

The external services, PostgreSQL SQL, workflow graph, prompts, contracts, governor logic, QA/repair logic, publishing gates, checkpoints and learning logic are preserved. All exported n8n Code-node JavaScript is executed verbatim through the Node bridge so the migration does not silently rewrite those 70 code nodes.

Python replaces the n8n orchestration layer: graph traversal, scheduling, HTTP transport, PostgreSQL calls, webhook hosting and process lifecycle.

## Local Windows run

1. Install Python 3.12 and Node.js 22.
2. Run `python -m pip install -r requirements.txt`.
3. Start with `python -m python_growth_os.app`.
4. Open `http://127.0.0.1:8443/ui/`.
5. Enter PostgreSQL and service credentials in the web interface and save.
6. Use **Run cycle now** for a controlled manual test.
7. The integrated scheduler runs every 15 minutes when enabled.

The web interface writes credentials to the local `.env` file. It is intended for localhost use; do not expose port 8443 to the public internet. Secrets are never stored in the workflow JSON.

## CLI

- One manual cycle: `python -m python_growth_os.app --run`
- API/UI server: `python -m python_growth_os.app`
- Scheduler-only mode: `python -m python_growth_os.app --schedule`

## Runtime compatibility

- Original Code-node JavaScript is executed by Node.js through a compatibility bridge.
- Previous-node `$().item/.first/.all/.allData` access is supported for the workflow's observed usage.
- Workflow HTTP headers/query/body/binary response behavior is preserved.
- YouTube OAuth supports an access token or client ID + client secret + refresh token.
- The single workflow Wait node is a bounded AI repair backoff of at most 30 seconds.
- Unsupported node types and condition operators fail closed instead of guessing.

Credential secrets are not present in an n8n workflow export; only credential references are exported. Therefore the migration does not copy secrets from GitHub.

The local UI is a configuration/control surface only. It does not replace or alter the original workflow logic.
