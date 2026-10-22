# WhiteBoRAG

Ask questions about your whiteboard.

An ESP32-CAM points at a whiteboard. Wave a hand in front of its IR sensor and it photographs the board. Each photo is transcribed, filed under its project and indexed. Later you can ask things like "what's left to do on WhiteBoRAG?" or "where did we write about the vector store?" and get an answer, with dates and links back to the photos.

Everything runs on AWS and is defined in Terraform. It is a demo project, built as a capstone for the Production track of Ed Donner's Udemy course.

## How it works

```
Capture   ESP32-CAM ──► API Gateway (device API key) ──► presign λ ──► pre-signed URL
          ESP32-CAM ──► S3 (photo upload)

Ingest    S3 ──object created──► SQS ──batch──► ingest λ ──► DynamoDB (boards, todos)
                                  │                 │   ──► S3 Vectors (Titan embeddings)
                                  └─3 failures─► DLQ  └──► Bedrock: Nova Pro (photo check),
                                                                    Nova 2 Lite (transcribe, normalize)

Query     chat UI ──► API Gateway (query API key) ──► query λ ──► Nova 2 Lite (intent, answer)
                                                          ├──► S3 Vectors (search)
                                                          └──► DynamoDB, S3 (boards, photos)
```

- **Capture:** the camera asks for a pre-signed URL, then uploads the photo straight to S3. Each device has its own API key and can only upload as itself.
- **Ingest:** an S3 event goes through SQS to the ingest Lambda.
  - Nova Pro checks whether the photo is readable. Unusable snaps are deleted and logged.
  - Nova 2 Lite transcribes the board to Markdown: title, boxes and arrows, todos and notes.
  - A normalizing step fixes spelling and works out the project from the board's title.
  - Todos are tracked across boards, so the system knows when one was ticked off.
  - Each section is embedded with Titan and stored in S3 Vectors.
  - After 3 failed attempts a capture goes to a dead-letter queue, and an alarm emails you.
- **Query:** the query Lambda works out what kind of question it is: todos, latest board, latest diagram, diagram history, or search.
  - It matches project names fuzzily and asks "did you mean…?" rather than guessing.
  - It answers only from the matching boards and returns them as sources with short-lived photo links.
- **Chat UI:** a static page in `frontend/` that talks to the query API.

## Repository layout

| Path | What's in it |
|---|---|
| `ESP32-cam/firmware/` | Camera firmware (Arduino). See its [README](ESP32-cam/firmware/README.md) for wiring and flashing. |
| `backend/presign/` | Lambda that issues pre-signed upload URLs |
| `backend/ingest/` | Ingest Lambda and its prompts |
| `backend/query/` | Query Lambda and its prompts |
| `frontend/` | Chat page |
| `infra/` | Terraform for everything on AWS; `infra/bootstrap/` creates the state bucket |
| `eval/harness/` | OCR eval harness used to pick the transcription model |

## Setup

You need an AWS account with Bedrock access to Nova Pro, Nova 2 Lite and Titan Text Embeddings V2, plus Terraform, [uv](https://docs.astral.sh/uv/) and Python 3.13. Everything is deployed to `ap-south-1`.

The bucket names are fixed in the Terraform (`esp32-cam-whiteborag` and `whiteborag-tfstate-<account id>`). If you deploy your own copy, change them in `infra/s3.tf`, `infra/versions.tf` and `infra/bootstrap/main.tf` first, because S3 bucket names are global.

1. **Create the state bucket:**
   ```
   terraform -chdir=infra/bootstrap init
   terraform -chdir=infra/bootstrap apply
   ```
2. **Configure:** copy `infra/terraform.example.tfvars` to `infra/terraform.tfvars` and set `alert_email`.
3. **Build the Lambda packages:**
   ```
   uv run --directory backend/ingest python scripts/build.py
   uv run --directory backend/query python scripts/build.py
   ```
   The presign Lambda is zipped by Terraform itself.
4. **Deploy:**
   ```
   terraform -chdir=infra init
   terraform -chdir=infra apply
   ```
   Confirm the subscription email AWS sends to `alert_email`, or the DLQ alarm can't reach you.
5. **Check the capture API:**
   ```
   uv run --project backend/presign python infra/scripts/smoke.py
   ```
6. **Flash the camera:** follow [`ESP32-cam/firmware/README.md`](ESP32-cam/firmware/README.md).
7. **Run the chat page:**
   - Copy `frontend/config.example.js` to `frontend/config.js` and fill in the values from `terraform -chdir=infra output -raw api_base_url` and `terraform -chdir=infra output -raw query_api_key`. `config.js` is git-ignored.
   - Serve the page with `python -m http.server 8000 --directory frontend` and open http://localhost:8000. The API only accepts requests from that origin (`query_origin` in Terraform).

## Tests

Each Python package has its own suite:

```
uv run --directory backend/presign pytest -q
uv run --directory backend/ingest pytest -q
uv run --directory backend/query pytest -q
uv run --directory eval/harness pytest -q
```

The eval harness's dataset tests need the eval snaps, which aren't in the repository.

## Drawing boards that read well

Nova 2 Lite reads text and todos well but struggles with diagrams. These habits help:

- Write the title on the first line, on its own, starting with the project name, for example "WhiteBoRAG ingest arch". The project comes from the title, so a missing title means the board isn't filed under any project.
- Never write the title on a box's border.
- Write each box name inside its box as a plain word. Letters drawn in separate cells, like S|Q|S, get read as separate boxes.
- Run each arrow all the way to the box it means, not to a container around it, and give it a clear arrowhead.
- Put one short label next to the middle of each arrow.
- Write `TODO` on its own line above a checkbox list.
- Light the board evenly and avoid flash glare.

## Shortcomings

- **Diagrams are the weak spot.** Arrow labels land on the wrong arrow, and small or boxed lettering gets misread (DLQ became "OLQ"). In the eval, the best model recovered only about half the arrows.
- **A bigger Nova didn't help.** Nova Pro lost titles, dropped checkboxes and gave different answers on repeat runs, at 5x the cost. A sharper prompt didn't help either. Stronger vision models on Bedrock might do better, but they need extra account access, and I'm not pursuing that for now.
- **It's a demo.** The chat page runs locally with an API key and has no user accounts. The eval set is small: 13 snaps of 5 boards. Retrieval uses one vector per board section, with no finer chunking.

## Choosing the OCR model

Before building ingest, the harness in `eval/harness/` compared 9 engines on 13 real snaps for under $1 in total: Textract, Rekognition, Nova Lite, Nova Pro, Nova 2 Lite, and hybrids of OCR plus a Nova model. Nova 2 Lite on the raw photo had the best word accuracy and costs about $0.0005 per snap. Run it with:

```
uv run --directory eval/harness harness run --engines bedrock:nova-2-lite --variants raw
```

## Credits

Built for the Production track of Ed Donner's Udemy course. Two of the building blocks came straight from the course: using S3 Vectors as the vector store, and putting API Gateway in front of the Lambdas with API keys.
