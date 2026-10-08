# WhiteBorag Part 1: Capture & Ingest — Design

- **Date:** 2026-10-08
- **Status:** approved in conversation; awaiting written-spec review
- **Scope:** Part 1 of 2. Part 2 (extraction: OCR, diagram understanding, notes, search) gets its own spec.

## 1. Goal

An ESP32-CAM is mounted facing a whiteboard. A hand wave in front of an IR proximity sensor, or a push-button press, takes a full-resolution photo. The photo is stored in S3 under a predictable key with per-capture metadata.

The long-term aim, delivered in Part 2, is a **searchable archive** of whiteboard sessions with **notes/summaries**. Whiteboards may contain architecture diagrams. Part 1 must therefore keep:

- full-resolution images
- a stable capture ID
- a UTC timestamp
- device and trigger metadata

so that Part 2 can index captures and link them back to their images.

### Success criteria

1. A hand wave or button press produces exactly one capture: flash, upload, then confirmation blinks. The full cycle takes no more than about 5 seconds on a healthy network.
2. Each image lands at `captures/{device_id}/{YYYY}/{MM}/{DD}/{YYYYMMDDTHHMMSSZ}_{capture_id}.jpg` with metadata `device-id` and `trigger`.
3. Requests without a valid API key are rejected by API Gateway.
4. A key for one device cannot upload as another device.
5. All AWS resources are defined in Terraform, and `terraform plan` is clean after apply.
6. TLS is verified by the production firmware for both API Gateway and S3.

### Non-goals (Part 1)

- OCR, extraction or search (Part 2).
- Offline buffering of failed captures. A failure is signalled on the LED and the user re-triggers.
- Battery or deep-sleep operation. The device runs on USB/wall power.
- Over-the-air firmware updates.
- A web UI.

## 2. Architecture & data flow

```
[Button GPIO13]──┐
[IR prox GPIO14]─┴─> ESP32-CAM ──(1) POST /v1/captures  x-api-key ──> API Gateway (REST, usage plan)
                        │                                                  │ Lambda proxy
                        │        <──(2) {capture_id, upload_url, ────── Lambda presign (Python 3.13)
                        │               headers, expires_in}
                        ├──(3) capture JPEG (flash)
                        └──(4) PUT upload_url + returned headers ──> S3 esp32-cam-whiteborag
                                                                      └─ Part 2: ObjectCreated on captures/
```

The device requests the URL **before** capturing, so network and auth failures are caught before the flash fires.

There is no "upload complete" callback. The S3 `ObjectCreated` event under `captures/` is the source of truth for Part 2.

## 3. API contract

### Request

```
POST {API_BASE_URL}/captures
x-api-key: <per-device key>
Content-Type: application/json

{ "device_id": "wb-cam-01", "trigger": "button" }
```

- `device_id`: must match `^[a-z0-9-]{1,32}$`.
- `trigger`: one of `button`, `ir`, `serial`.

### Response 200

```json
{
  "capture_id": "01JA2B3C4D5E6F7G8H9J0K1M2N",
  "key": "captures/wb-cam-01/2026/10/08/20261008T133454Z_01JA2B3C4D5E6F7G8H9J0K1M2N.jpg",
  "upload_url": "https://esp32-cam-whiteborag.s3.ap-south-1.amazonaws.com/...",
  "headers": {
    "Content-Type": "image/jpeg",
    "x-amz-meta-device-id": "wb-cam-01",
    "x-amz-meta-trigger": "button"
  },
  "expires_in": 300
}
```

The device must send **exactly** the returned `headers` on the PUT, because they are part of the signature.

### Errors

| Status | When | Device behaviour |
|---|---|---|
| 400 | Body is not JSON, or `device_id`/`trigger` is invalid | Error blink, no retry |
| 403 | Missing or invalid API key (API Gateway) | "Config error" blink, no retry |
| 403 | Key does not belong to `device_id` (Lambda) | "Config error" blink, no retry |
| 429 | Usage plan throttle or quota exceeded | Error blink, no retry (cooldown covers it) |
| 5xx / network | Transient | Retry up to 2 times with backoff (0.5 s, 1.5 s) |

Error bodies are `{"error": "<message>"}`.

## 4. Firmware

**Location:** `ESP32-cam/firmware/whiteborag_cam/`. This is an Arduino sketch built with the arduino-cli bundled in the Arduino IDE.

- **FQBN:** `esp32:esp32:esp32cam`
- **ESP32 core:** 3.3.12
- **Partition scheme:** Huge APP (the default)
- **Library:** ArduinoJson (installed via `arduino-cli lib install ArduinoJson`)

`ESP32-cam/testing/` remains for experiments.

### Files

| File | Responsibility |
|---|---|
| `whiteborag_cam.ino` | `setup()`/`loop()`, the capture state machine, serial commands |
| `camera.{h,cpp}` | Camera init and `capture()` with flash/settle frames (ported from `testing/snap_upload_s3`) |
| `trigger.{h,cpp}` | Button and IR inputs, debounce, edge detection, cooldown |
| `api_client.{h,cpp}` | `POST /captures`, parses the response into a struct (URL, key, headers) |
| `uploader.{h,cpp}` | HTTPS PUT of the JPEG with the signed headers |
| `feedback.{h,cpp}` | Dimmed flash-LED signal patterns |
| `config.h` | Non-secret settings: pins, `DEVICE_ID`, timings |
| `secrets.h` (git-ignored) | `WIFI_SSID`, `WIFI_PASSWORD`, `API_BASE_URL`, `API_KEY` |
| `secrets.example.h` | Committed template for `secrets.h` |

### Triggers

**Button.** On GPIO 13, wired to GND, with `INPUT_PULLUP`. The signal must be stable for 50 ms.

**IR proximity sensor** (FC-51/TCRT5000 type). On GPIO 14, using the module's own push-pull output, active LOW. The signal must be stable LOW for 150 ms, which rejects flicker.

**Firing and cooldown:**
- Each input fires on the falling edge only. Holding a hand in front of the sensor gives one capture.
- A cooldown of 5 s starts after each capture attempt, whether it succeeded or failed.
- Triggers that arrive while busy or in cooldown are ignored.

**Pins:**
- GPIO 13 and 14 are free because the SD card is unused.
- GPIO 12, 2 and 15 are not used, because they are boot-strapping pins.
- GPIO 16 is used by PSRAM.

### Capture state machine

```
IDLE → (trigger) → ENSURE_WIFI → REQUEST_URL → CAPTURE → UPLOAD → FEEDBACK → COOLDOWN → IDLE
```

**REQUEST_URL:**
- Retries 5xx and network errors up to 2 times.
- On 400, 403 or 429 it fails immediately.

**UPLOAD:**
- Retries once on a network error.
- If S3 returns 403 with `AccessDenied` and an "expired" message, it requests a fresh URL once and re-uploads the same frame.

**On any failure:**
- the frame is released
- the error pattern is shown
- the state goes to COOLDOWN

### Feedback (flash LED, GPIO 4)

The red LED on GPIO 33 is on the back of the board and cannot be seen from the whiteboard, so feedback uses the flash LED at low duty.

| Event | Pattern |
|---|---|
| Trigger accepted | 1 dim pulse (~80 ms) |
| Capture | Full flash (existing behaviour: 100 ms pre-light, 3 settle frames) |
| Upload OK | 2 short dim blinks |
| Transient or network failure | 3 slow dim blinks |
| Config error (400/403) | 6 fast dim blinks |

**Dimming.** LEDC PWM is used on an explicitly chosen channel and timer that differ from the camera's XCLK (`LEDC_CHANNEL_0`/`LEDC_TIMER_0`). If PWM conflicts with the camera clock during implementation, fall back to short on/off blinks at full brightness.

### Wi-Fi, TLS, robustness

**Wi-Fi:**
- Station mode, sleep disabled, auto-reconnect.
- If disconnected for more than 5 minutes, call `ESP.restart()`.

**TLS:**
- `WiFiClientSecure` with an embedded CA set: Amazon Root CA 1, plus a backup root.
- These cover both the API Gateway (`*.execute-api.ap-south-1.amazonaws.com`) and S3 certificate chains.
- The CA PEMs are fetched from amazontrust.com at implementation time and verified against both endpoints.
- `setInsecure()` is not used in production firmware.

**Serial commands (115200 baud):**
- `snap`: run the full flow with trigger `serial`
- `status`: Wi-Fi state, RSSI, heap/PSRAM, last result
- `flash on|off`

**Camera:** UXGA 1600x1200, JPEG quality 10, frame buffer in PSRAM, grab-latest mode. These settings are carried over from the test firmware, where they are verified.

## 5. Backend

### Repo layout

```
WhiteBorag/
├── ESP32-cam/{firmware,testing}/
├── backend/presign/        uv project: handler.py, ulid.py, tests/
├── infra/                  Terraform root module
│   └── bootstrap/          one-time: remote-state bucket
└── docs/superpowers/specs/
```

### Lambda `backend/presign/handler.py`

- **Runtime:** Python 3.13, arm64, 128 MB, 5 s timeout. There are no dependencies beyond boto3, which the runtime provides.
- **Environment variables:**
  - `BUCKET`
  - `PREFIX` (`captures/`)
  - `URL_TTL` (`300`)
  - `DEVICE_KEYS`: a JSON map of API key ID → device ID

**Steps:**
1. Parse the JSON body, then validate `device_id` and `trigger`. Failure returns 400.
2. Look up `requestContext.identity.apiKeyId` in `DEVICE_KEYS`. If the key is unknown or maps to a different device, return 403.
3. Generate the ULID (in `ulid.py`, standard library only) and the UTC timestamp, then build the key.
4. Call `s3.generate_presigned_url("put_object", Params={Bucket, Key, ContentType: "image/jpeg", Metadata: {"device-id", "trigger"}}, ExpiresIn=URL_TTL)`. The client is created with SigV4 and virtual-hosted addressing in the bucket's region.
5. Return 200 with the response body from §3.
6. Log one JSON line: `capture_id`, `device_id`, `trigger`, `key`.

**URL length.** URLs signed with Lambda role credentials include `X-Amz-Security-Token`, so the URL is about 1.5 KB. The firmware must not assume short URLs.

### Terraform `infra/`

- **Provider and backend:**
  - AWS provider, region `ap-south-1`.
  - The S3 backend uses `use_lockfile = true` for native locking, so no DynamoDB table is needed.
  - The state bucket is created by `infra/bootstrap/`, which uses local state and is applied once.
  - The state bucket is private, encrypted and versioned. State contains the API key values.
- **Capture bucket `esp32-cam-whiteborag`:**
  - adopted with an `import {}` block
  - public access block on all four settings
  - SSE-S3 default encryption
  - versioning enabled
  - lifecycle: abort incomplete multipart uploads after 7 days, expire noncurrent versions after 30 days
  - no expiry of current objects
  - existing `esp32cam/` test objects are left untouched
- **Lambda:**
  - packaged with the `archive_file` data source from `backend/presign/`
  - log group with 30-day retention
  - IAM role allowing `s3:PutObject` on `arn:aws:s3:::esp32-cam-whiteborag/captures/*`, plus basic logging
- **API Gateway:**
  - REST API with resource `/captures`, method `POST`, `api_key_required = true`, `AWS_PROXY` integration
  - stage `v1`
  - usage plan: rate 1 rps, burst 5, quota 500/day
- **Devices:**
  - variable `devices` (list of strings, default `["wb-cam-01"]`)
  - one `aws_api_gateway_api_key` per device, attached to the usage plan
  - the key IDs feed `DEVICE_KEYS`
- **Outputs:**
  - `api_base_url`
  - `api_keys`: a sensitive map of device → key value

## 6. Testing

**Lambda unit tests** run with pytest via `uv run pytest`. They cover:
- validation (400 cases)
- the key-to-device check (403)
- key layout and timestamp format
- ULID format and ordering
- the presigned URL: it contains the bucket host, the signed headers include `content-type` and the `x-amz-meta-*` headers, and the expiry is correct

Presigning runs offline with dummy credentials.

**Infra checks:**
- `terraform fmt -check`, `terraform validate` and `terraform plan` succeed
- after apply, `plan` shows no changes

**End-to-end with curl:**
- `POST /captures` with the key returns 200 and a URL
- `PUT` with the returned headers returns 200
- the object exists at the expected key with the expected metadata
- a request without a key returns 403
- a request with the wrong `device_id` returns 403

**Firmware:**
- the sketch compiles with arduino-cli
- on the device: the `snap` serial command works, then a button press, then an IR hand wave
- cooldown suppresses a double trigger
- unplugging Wi-Fi gives the error pattern followed by recovery

## 7. Risks & open points

- **LED dimming vs camera XCLK.** PWM on the flash LED could disturb the camera clock. Mitigation: use an explicit separate channel and timer, with a fallback to on/off blinks.
- **IR sensor tuning.** FC-51-type modules have a sensitivity potentiometer. Glare reflecting off the whiteboard may need adjustment or a shroud. The 150 ms stable-LOW requirement reduces false triggers.
- **CA rotation.** Amazon root CAs are long-lived (until 2038). Embedding two roots covers a chain change.
- **Clock-free device.** The device needs no NTP, because all timestamps are set server-side.
