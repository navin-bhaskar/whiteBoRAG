# OpenRouter model bake-off — results

Run: `openrouter/eval/runs/bakeoff` (2026-10-27). The same 13 photos, ground truth and scoring as the AWS run that picked Nova 2 Lite (`aws/eval/runs/20261016T122626Z`) and the offline bake-off. Every model ran raw: the photo plus the shared board-Markdown prompt, one call per photo. All 78 calls succeeded. Two Qwen calls hit OpenRouter upstream rate limits (HTTP 429) and were retried; the client now retries those itself.

Spend: $0.16 for the transcription run and $0.18 for the project checks, $0.34 in all.

## Transcription

| model | word F1 | CER | hallucination | edge P | edge R | checkbox | latency s | $/photo |
|---|---|---|---|---|---|---|---|---|
| `anthropic/claude-sonnet-5.5` | **0.982** | **0.005** | 0.021 | 0.904 | 0.963 | **1.000** | 4.2 | 0.0074 |
| `google/gemini-3.5-flash-lite` | 0.977 | 0.008 | **0.020** | 0.815 | 0.815 | **1.000** | **2.0** | 0.0006 |
| `anthropic/claude-haiku-5.5` | 0.963 | 0.008 | 0.033 | 0.941 | 0.963 | **1.000** | 6.2 | 0.0007 |
| `qwen/qwen3-vl-235b-a22b-instruct` | 0.954 | 0.013 | 0.057 | **0.972** | **0.972** | 0.833 | 6.3 | 0.0006 |
| `amazon/nova-2-lite-v1` | 0.855 | 0.069 | 0.143 | 0.491 | 0.481 | **1.000** | 2.9 | **0.0004** |
| `openai/gpt-5.4-mini` | 0.766 | 0.184 | 0.191 | 0.494 | 0.500 | 0.333 | 3.7 | 0.0024 |
| *bedrock:nova-2-lite (AWS baseline)* | *0.847* | *0.084* | *0.143* | *0.491* | *0.481* | *1.000* | *2.1* | |
| *local:qwen3-vl-8b (offline pick)* | *0.868* | *0.203* | *0.075* | *0.833* | *0.815* | *0.667* | *12.0* | *$0* |

Nova 2 Lite on OpenRouter matches its AWS score, so the setup is a fair comparison with the AWS baseline.

## Project pick

Each model normalized its own 13 transcripts twice, once with no projects known and once with WhiteBoRAG known, and the project `decide()` settled on (colon rule included) was scored. The goals board is the real capture "whiteBoRAG local: goals": the model transcribes it, then picks its project as the first board of that project. It passes only if the project comes out as "whiteBoRAG local" in any capitalization.

| model | no projects known | WhiteBoRAG known | goals board | goals project read as | check cost $ |
|---|---|---|---|---|---|
| `anthropic/claude-sonnet-5.5` | **13/13** | **13/13** | pass | WhiteBoRAG local | 0.092 |
| `anthropic/claude-haiku-5.5` | 12/13 | **13/13** | pass | WhiteBoRAG local | 0.008 |
| `google/gemini-3.5-flash-lite` | 11/13 | **13/13** | pass | WhiteBoRAG Local | 0.010 |
| `qwen/qwen3-vl-235b-a22b-instruct` | 11/13 | **13/13** | pass | WhiteBorag local | 0.006 |
| `amazon/nova-2-lite-v1` | 12/13 | **13/13** | FAIL | whiteBoR16 local | 0.009 |
| `openai/gpt-5.4-mini` | 10/13 | 9/13 | FAIL | attribute RAG local | 0.022 |
| *offline: title match / Qwen3-VL-8B's own pick* | | *12/13 / 7/13* | *FAIL (WhileBORAG)* | | |

Haiku scored 11/13 with no projects known on a first, interrupted run and 12/13 on the full rerun, so one point of difference between the cheaper models is within run-to-run noise.

## Findings

- **Four models clearly beat AWS.** Sonnet, Gemini Flash Lite, Haiku and Qwen3-VL-235B all reach a word F1 of 0.95–0.98 against Nova 2 Lite's 0.85, with a tenth of its character errors and a third or less of its hallucination. They also read the diagrams far better: edge recall 0.82–0.97 against 0.48.
- **Only Sonnet got every project right.** It is the only model at 13/13 in both conditions. Haiku, Gemini and Qwen all fix the misread goals title, which is the failure that sank `offline/`.
- **Nova 2 Lite, the AWS model, fails the goals board.** It read the title as "whiteBoR16 local", and the colon rule turned that into a project.
- **GPT-5.4 mini misreads handwriting** letter by letter: "uhi spex" for Whisper, "vector stane" for Vector store. That drags down every score, including the project pick.
- **Gemini Flash Lite is the fastest** at 2 s per photo, with Sonnet-level words but weaker diagram edges (0.815).

## Cost per photo in production

A capture costs a photo check (Nova Pro), one transcription, one normalize call and an embedding. From the measured costs, transcription plus normalize comes to about 1.1 ¢ for Sonnet and about 0.1 ¢ for Haiku, Gemini or Qwen. Chat answers are billed per question on the text model.

## Recommendation

**Claude Sonnet 5.5 for both transcription and text (normalize and chat).** It's the best reader by every measure except diagram edges, where it's close to the best, and the only model with a perfect project pick, which was the main goal. At about 1.1 ¢ per photo it's well inside the budget of a few cents.

**The budget choice is Claude Haiku 5.5.** It's a tenth of the price, has the best diagram edges after Qwen, and its project picks were near-perfect (12–13/13, goals board passed).

## Decision (2026-10-27)

Sonnet reads, Haiku writes: `transcribe = "anthropic/claude-sonnet-5.5"` (raw) and `text = "anthropic/claude-haiku-5.5"`. The text model does the normalize step, so the project pick is Haiku's (12–13/13 with no projects known, 13/13 with WhiteBoRAG known, goals board passed), and it also writes the chat answers. Cost per photo: about 0.74 ¢ to read plus about 0.03 ¢ to normalize, under 1 ¢ in all with the photo check and embedding.
