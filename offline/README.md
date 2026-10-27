# WhiteBoRAG offline

The same whiteboard RAG as the AWS version, running entirely on a laptop. Nothing leaves your LAN.

```
Capture   ESP32-CAM ──HTTP POST (device key)──► offline server ──► data/uploads/ + job queue

Ingest    job queue ──► worker ──► LM Studio: Qwen3-VL-8B (photo check, transcribe, normalize)
                          │    ──► LM Studio: nomic-embed-text (embeddings) ──► Qdrant (local)
                          └──────► SQLite (boards, projects, todos)

Query     chat page ──► offline server /query ──► Qwen3-VL-8B (intent, answer)
                                             ├──► Qdrant (search)
                                             └──► SQLite, data/uploads/ (boards, photos)
```

The ingest and query logic is the AWS code in `aws/backend/`, unchanged. This folder only swaps what it talks to:

| AWS | Offline |
|---|---|
| API Gateway + presign Lambda + S3 upload | `POST /captures` on the laptop |
| S3 → SQS → ingest Lambda | `data/uploads/` + a SQLite job queue + one worker thread |
| Bedrock Nova Pro, Nova 2 Lite | Qwen3-VL-8B in LM Studio |
| Titan Text Embeddings V2 | nomic-embed-text v1.5 in LM Studio |
| S3 Vectors | Qdrant in local mode (`data/vectors/`) |
| DynamoDB | SQLite (`data/whiteborag.db`) |
| Chat page on S3 + query Lambda | The same chat page, served by the offline server |

## Models

One vision model handles everything, so only one large model needs to be in memory. It fits in 8 GB of VRAM.

| Role | LM Studio id | File |
|---|---|---|
| Photo check, transcribe, normalize, chat | `qwen3-vl-8b-instruct` | `lmstudio-community/Qwen3-VL-8B-Instruct-GGUF`, Q4_K_M + F16 mmproj |
| Embeddings | `text-embedding-nomic-embed-text-v1.5` | The copy bundled with LM Studio (768 dimensions) |

Qwen3-VL won the OCR bake-off against olmOCR-2, GLM-OCR, PaddleOCR-VL and DeepSeek-OCR. On the 13 eval photos it also beat the AWS model, Nova 2 Lite, on word F1 and diagram edges. See [`eval/RESULTS.md`](eval/RESULTS.md).

The plan used Llama 3.1 8B for the text steps. The LM Studio GGUF answered the normalize and restructure prompts with made-up tool-call JSON, so Qwen3-VL does those too.

## Setup

You need [uv](https://docs.astral.sh/uv/), Python 3.13 and [LM Studio](https://lmstudio.ai/).

1. **Models:** in LM Studio, download `lmstudio-community/Qwen3-VL-8B-Instruct-GGUF` (Q4_K_M). The nomic embedding model comes with LM Studio.
2. **Model server:** in LM Studio's Developer tab, start the server on port 1234. Models load on first use.
3. **Config:** copy `config.example.toml` to `config.toml` (git-ignored). Under `[devices]`, replace `change-me-device-key` with a long random key, for example from `python -c "import secrets; print(secrets.token_urlsafe(24))"`. Each key maps to a device id such as `cam-01`.
4. **Check the model server:**
   ```
   uv run --directory offline python -m whiteborag_offline.smoke
   ```
   It lists the models LM Studio offers and asks the text model one question. The ids in `config.toml` must match that list.

## Running

```
uv run --directory offline python -m whiteborag_offline.server
```

The server listens on `0.0.0.0:8080`, so the camera can reach it over the LAN.

- **Chat:** open http://localhost:8080/.
- **Recent ingest jobs:** http://localhost:8080/jobs.
- **Health:** http://localhost:8080/health.

Each capture takes about a minute to ingest. Windows asks whether Python may accept connections the first time the server starts; allow it, or the camera can't reach the laptop.

Model calls are heavy. If memory runs short, unload models in LM Studio that aren't in `config.toml`.

## The camera

Flash the [offline firmware](firmware/README.md). It POSTs photos straight to this server. A capacitive touch pad triggers a capture: one touch, one photo.

## Writing boards

- **Projects:** the first board of a project names it in the title with a colon. Everything before the colon is the project name. `# WhiteBoRAG local: goals` creates the project "WhiteBoRAG local".
  - Later boards don't need the colon. A title that contains the project name, even misspelled, joins it: `# whiteborag local questions`.
  - A board whose title has no colon and doesn't name a known project gets no project. It's still stored and searchable, but its todos aren't tracked.
  - Unlike the AWS version, the model never picks the project. Qwen3-VL got that wrong too often.
- **Todos:** write them as checkboxes, `- [ ] write README` and `- [x] flash firmware`. A numbered or plain list is notes, not todos.

## Known limits

- **Misreads stay in.** The spelling pass rarely fixes a misread word ("gd rant" for "qdrant"), so the wrong word can appear in answers and miss in search. Write clearly, with good light.
- **A misread project name makes a new project.** If the first board's title is misread ("WhileBORAG"), so is the project name. Fix it by correcting the title in `data/derived/transcripts/.../<capture>.md` and `.normalized.md` and ingesting the capture again.
- **"What are the goals?" is read as a todo question.** Questions about a project's goals or plans go to the todo list. Ask about the board instead: "what does the goals board say?"

## Where the data lives

Everything is under `offline/data/` (git-ignored):

| Path | What's in it |
|---|---|
| `uploads/<device>/<yyyy>/<mm>/<dd>/` | The photos |
| `rejected/` | Photos the check model judged unusable (moved here, not deleted) |
| `derived/transcripts/` | Each capture's transcript (`.md`) and its normalized version (`.normalized.md`) |
| `whiteborag.db` | SQLite: captures, projects, todos and the job queue |
| `vectors/` | Qdrant's local store |

To start over, stop the server and delete `data/`.

## The OCR bake-off

The bake-off runs local models through the AWS eval harness (`aws/eval/harness/`), using the same 13 photos and ground truth that picked Nova 2 Lite. Candidates and their LM Studio ids are in `eval/candidates.toml`. From `offline/`:

```
uv run python -m whiteborag_offline.eval.bakeoff ocr --candidate olmocr
uv run python -m whiteborag_offline.eval.bakeoff run --run eval/runs/bakeoff --engines local:qwen3-vl-8b,local-hv:olmocr
uv run python -m whiteborag_offline.eval.bakeoff score --run eval/runs/bakeoff
```

- `ocr` fills the plain-OCR cache for a dedicated OCR model.
- `run` transcribes and scores. Engines are `local:<id>` (the model reads the photo), `local-hv:<id>` (OCR text plus the photo go to Qwen3-VL) and `local-ht:<id>` (OCR text only).
- `score` re-scores a finished run.

## Tests

```
uv run --directory offline pytest -q
```
