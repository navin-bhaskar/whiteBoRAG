# WhiteBoRAG on OpenRouter

The [offline](../offline/README.md) server, with the models on [OpenRouter](https://openrouter.ai/) instead of LM Studio. Photos, the job queue, SQLite, Qdrant and the chat page all stay on the laptop. Only the model calls (photo check, transcription, spelling pass, chat answers and embeddings) go out to OpenRouter, which bills them per call.

This folder holds only its config and data. The code is `offline/`'s, run with this folder's `config.toml`.

## Models

| Step | Model |
|---|---|
| Photo check | `amazon/nova-pro-v1`, as on AWS |
| Transcription | `anthropic/claude-sonnet-5.5`, the bake-off's best reader |
| Spelling pass, project pick and chat | `anthropic/claude-haiku-5.5` |
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

Six vision models read the 13 AWS eval photos, and each one's project pick was checked; full results are in [`eval/RESULTS.md`](eval/RESULTS.md). Claude Sonnet 5.5 read best (word F1 0.982 against AWS Nova 2 Lite's 0.847). Claude Haiku 5.5 picks projects nearly as well as Sonnet at a tenth of the price, and like Sonnet it turns the misread "WhileBORAG local: goals" into "WhiteBoRAG local". Together they cost about 0.9 ¢ per photo.

To rerun it, from `offline/` (all six models plus the project check cost about $0.35; the two below cost less):

```
uv run python -m whiteborag_offline.eval.bakeoff --candidates ../openrouter/eval/candidates.toml run --run ../openrouter/eval/runs/<name> --engines local:nova-2-lite,local:claude-sonnet-5.5
```

then, from `openrouter/`, `uv run python -m whiteborag_openrouter.eval.project_check --run eval/runs/<name>`.

## End-to-end check (2026-10-28)

- **The offline photos, read again:** the 5 photos from `offline/data/uploads/` were requeued on fresh data, and all 5 were ingested. 4 of the 5 got a project, against 1 of 5 offline: WhiteBoRAG ×2, RAG revision and whiteBORAG local. The fifth, the video board, has no title, so it has no project.
- **Chat:** three questions, about the vector store, the video upload and the goals board. The first run missed two: the video board wasn't found, and the goals board was cited while the answer said there was none. Both misses were in the query code shared with AWS, and both are fixed (commit `2ffd595`): the answer model now sees each board's title, and the section search also tops up from all sections. After the fix, all three answers cite the right boards.
- **A live capture:** the camera, on the mDNS firmware, found the laptop by its `.local` name and uploaded a new board, "WhiteBoRAG local : ingest arch". It was ingested in 14 s into the existing whiteBORAG local project, and its transcript matched the board, all 6 boxes and 8 links.

## Known limits

- **AWS doesn't have the chat fix yet.** Commit `2ffd595` changed `aws/backend/query`, but the AWS query Lambda hasn't been redeployed, so the AWS chat still has both misses.
- **No internet, no ingest.** Every model call goes to OpenRouter. While it's unreachable, jobs fail and stay failed until you requeue them (see Running).
- **A board without a title gets no project.** It is still transcribed and searchable.
- **A project keeps the spelling it was first seen with.** Its display name comes from the first board's spelling ("whiteBORAG local"), even when a later board writes "WhiteBoRAG local".
- **One server at a time:** the offline and OpenRouter servers both use port 8080.

## Tests

```
uv run --directory openrouter pytest -q
```

The tests never call OpenRouter.
