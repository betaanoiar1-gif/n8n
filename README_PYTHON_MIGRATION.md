# YouTube Autonomous Growth OS — Python Runtime

This is a runtime migration, not a redesign. The original n8n workflow remains the source of truth in workflow_source.json.

The external services, PostgreSQL SQL, workflow graph, prompts, contracts, governor logic, QA/repair logic, publishing gates, checkpoints and learning logic are preserved. All exported n8n Code-node JavaScript is executed verbatim through a small Node bridge so the migration does not silently change those 70 code nodes.

Python replaces the n8n orchestration layer: graph traversal, scheduling, HTTP transport, PostgreSQL calls, webhook hosting and process lifecycle.

## Run

1. Copy .env.example to .env.
2. Put the same credentials used by the n8n credentials into the matching variables.
3. Install dependencies with: python -m pip install -r requirements.txt
4. Ensure Node.js is available on PATH.
5. Test one cycle with: python -m python_growth_os.app --run
6. Start the control API with: python -m python_growth_os.app
7. Start the original one-minute scheduler with: python -m python_growth_os.app --schedule

Credential secrets are not present in an n8n workflow export; only credential references are exported. Therefore the migration does not copy secrets from GitHub.

The runtime fails closed on an unsupported node type or condition operator instead of guessing.
