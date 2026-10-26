# Offline OCR bake-off — results

Run: `offline/eval/runs/bakeoff` (2026-10-24 → 2026-10-26). The same 13 photos, ground truth and scoring as the AWS run that picked Nova 2 Lite (`aws/eval/runs/20261016T122626Z`). All models ran in LM Studio on an RTX 5060 Laptop GPU (8 GB). Every run succeeded (0 failures).

## Engines

- `local:<model>`: the model sees the photo and the board-Markdown prompt (raw).
- `local-hv:<ocr>`: the OCR model's plain text plus the photo go to Qwen3-VL-8B, which writes the board Markdown.
- `local-ht:<ocr>`: the OCR model's plain text only, no photo, goes to Qwen3-VL-8B in text-only mode.

## Results

| engine | word F1 | CER | hallucination | edge P | edge R | checkbox | latency s |
|---|---|---|---|---|---|---|---|
| local-ht:olmocr | **0.883** | 0.247 | **0.048** | 0.000 | 0.000 | 0.167 | 5.4 |
| local-hv:olmocr | 0.876 | 0.193 | 0.059 | 0.767 | 0.704 | 0.833 | 13.7 |
| local:qwen3-vl-8b | 0.868 | 0.203 | 0.075 | 0.833 | **0.815** | 0.667 | 12.0 |
| local-hv:paddleocr-vl | 0.837 | 0.187 | 0.137 | **0.852** | 0.398 | 0.667 | 12.3 |
| local-hv:deepseek-ocr | 0.836 | **0.166** | 0.075 | 0.778 | 0.370 | 0.667 | 11.4 |
| local:olmocr | 0.829 | 0.293 | 0.138 | 0.704 | 0.537 | 0.500 | 5.0 |
| local-hv:glm-ocr | 0.818 | 0.215 | 0.129 | 0.804 | 0.481 | 0.667 | 8.5 |
| local-ht:glm-ocr | 0.780 | 0.333 | 0.138 | 0.000 | 0.000 | 0.000 | 4.6 |
| local-ht:paddleocr-vl | 0.622 | 0.449 | 0.320 | 0.000 | 0.000 | 0.000 | 19.0 |
| local-ht:deepseek-ocr | 0.614 | 0.409 | 0.282 | 0.000 | 0.000 | 0.000 | 6.0 |
| local:glm-ocr | 0.470 | 0.618 | 0.352 | 0.000 | 0.000 | 0.000 | 0.6 |
| local:deepseek-ocr | 0.135 | 0.773 | 0.751 | 0.000 | 0.000 | 0.167 | 0.5 |
| local:paddleocr-vl | 0.085 | 5.944 | 0.843 | 0.000 | 0.000 | 0.000 | 1.1 |
| *bedrock:nova-2-lite (AWS baseline)* | *0.847* | *0.084* | *0.143* | *0.491* | *0.481* | *1.000* | *2.1* |

Latency is per image with the model already loaded. The hybrid figures don't include OCR time (cached) or model swaps.

## Findings

- **Qwen3-VL-8B alone beats Nova 2 Lite** on word F1 (0.868 vs 0.847), hallucination (0.075 vs 0.143) and edges (0.833/0.815 vs 0.491/0.481). It loses on CER and checkboxes. Its CER comes from the two night shots (080834, 081104). It leaves edge targets out of the node list, misreads "CPPP site" as "PPP side" and turns the edge label "update db" into a node. On daylight and indoor shots its CER is 0.01–0.07.
- **olmOCR text + photo → Qwen3-VL** is the best all-round hybrid: a little better on words, hallucination and checkboxes than Qwen alone, but worse on edges (recall 0.704 vs 0.815).
- **Text-only hybrids never produce edges.** OCR text has no arrows, and the prompt forbids inventing them. local-ht:olmocr has the best word score, so it suits text-only boards.
- **Dedicated OCR models (GLM-OCR, PaddleOCR-VL, DeepSeek-OCR) only work with their own short prompts.** With the board prompt they invent content (GLM-OCR wrote a checklist that isn't on the daylight RAG board) or loop (PaddleOCR-VL reached 4 KB on one image). As hybrid OCR stages they're behind olmOCR, mostly on edge recall.
- **Llama 3.1 8B could not be the text-only restructurer.** The LM Studio GGUF answered all 26 images with a made-up tool call (`{"name": "reconstruct_whiteboard", ...}`), even with a system message and an explicit "no tools" line. Qwen3-VL in text-only mode replaced it.

## Setup notes

- PaddleOCR-VL: the official repo's vision encoder is named `...-GGUF-mmproj.gguf`. LM Studio pairs a vision encoder only when the filename starts with `mmproj-`, so it was renamed to `mmproj-PaddleOCR-VL-1.6-GGUF.gguf`.
- DeepSeek-OCR: `NexaAI/DeepSeek-OCR-GGUF` is in Nexa SDK format (arch `deepseek_vl_v2`), and LM Studio's llama.cpp runtime won't load it. `ggml-org/DeepSeek-OCR-GGUF` (Q8_0 + mmproj) loads in LM Studio, with no llama-server needed.

## Recommendation

**Qwen3-VL-8B alone (raw).** It's one model and one call per capture. It has the best edge recall by a wide margin, and its word F1 is within 0.008 of the best photo-aware hybrid. The olmOCR hybrid needs two models (6.0 GB + 6.2 GB), which don't fit together in 8 GB of VRAM. Every capture would then pay for two model loads, and the 13.7 s above doesn't include them.

Pick the olmOCR → Qwen3-VL hybrid instead only if checkbox accuracy matters more than diagrams.

## Decision (2026-10-26)

Qwen3-VL-8B alone, raw (`transcribe = "qwen3-vl-8b-instruct"`, `transcribe_mode = "raw"`).

The checkbox score rests on six boxes, all on one board (photos 073208 and 074627). Qwen3-VL found every box and its text. Its only miss was reading the tick on "Test terraform code" as empty, in both photos. The olmOCR hybrid made the same miss on 074627, and Nova 2 Lite read it correctly. That looks like one faint tick, not a general weakness, and better lighting at the board should help. If boards with many checkboxes become common, rerun with more of them.
