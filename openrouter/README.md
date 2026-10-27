# WhiteBoRAG on OpenRouter

The [offline](../offline/README.md) server, with the models on [OpenRouter](https://openrouter.ai/) instead of LM Studio. Photos, the job queue, SQLite, Qdrant and the chat page all stay on the laptop. Only the model calls (photo check, transcription, spelling pass, chat answers and embeddings) go out to OpenRouter, which bills them per call.

This folder holds only its config and data. The code is `offline/`'s, run with this folder's `config.toml`.

## Models

| Step | Model |
|---|---|
| Photo check | `amazon/nova-pro-v1`, as on AWS |
| Transcription | `amazon/nova-2-lite-v1` for now; the bake-off picks the final one |
| Spelling pass and chat | `amazon/nova-2-lite-v1` for now |
| Embeddings | `amazon/titan-embed-text-v2`, as on AWS |

## Setup

You need [uv](https://docs.astral.sh/uv/), Python 3.13 and an OpenRouter API key.

1. **Key:** put the key in a `.env` file at the repo root (git-ignored), as one line: `OPENROUTER_API_KEY=<your key>`. An environment variable of the same name works too, and wins over `.env`.
2. **Config:** copy `config.example.toml` to `config.toml` (git-ignored). Under `[devices]`, replace `change-me-device-key` with a long random key, for example from `python -c "import secrets; print(secrets.token_urlsafe(24))"`. Each key maps to a device id such as `cam-01`.
3. **Check OpenRouter:**
   ```
   uv run --directory openrouter python -m whiteborag_openrouter.smoke
   ```
   It checks that OpenRouter offers every model in `config.toml` and asks the text model one question. The call costs a fraction of a cent.

## Running

```
uv run --directory openrouter python -m whiteborag_openrouter.server
```

The server listens on `0.0.0.0:8080`, so the camera can reach it over the LAN. It uses the same port as the offline server, so run only one of them at a time. The [offline firmware](../offline/firmware/README.md) works with either.

- **Chat:** open http://localhost:8080/.
- **Recent ingest jobs:** http://localhost:8080/jobs.
- **Health:** http://localhost:8080/health.

**Retrying and re-ingesting.** If OpenRouter was unreachable, jobs fail and stay failed. Once it's back, from `offline/`:

```
uv run python -m whiteborag_offline.requeue --config ../openrouter/config.toml --failed
uv run python -m whiteborag_offline.requeue --config ../openrouter/config.toml captures/cam-01/2026/10/27/<stamp>_<id>.jpg
```

## Writing boards

- **Projects:** as on AWS, the model picks the project from the board and the projects it already knows, fixing a misread name on the way.
  - A title with a colon overrides the model: everything before the colon is the project name. `# WhiteBoRAG: goals` puts the board in "WhiteBoRAG", creating the project if it's new.
- **Todos:** write them as checkboxes, `- [ ] write README` and `- [x] flash firmware`. A numbered or plain list is notes, not todos.

## Where the data lives

Everything is under `openrouter/data/` (git-ignored), laid out as in `offline/data/`:

| Path | What's in it |
|---|---|
| `uploads/<device>/<yyyy>/<mm>/<dd>/` | The photos |
| `rejected/` | Photos the check model judged unusable (moved here, not deleted) |
| `derived/transcripts/` | Each capture's transcript (`.md`) and its normalized version (`.normalized.md`) |
| `whiteborag.db` | SQLite: captures, projects, todos and the job queue |
| `vectors/` | Qdrant's local store |

To start over, stop the server and delete `data/`.

## The model bake-off

Results go here once the bake-off has run.

## Tests

```
uv run --directory openrouter pytest -q
```

The tests never call OpenRouter.
