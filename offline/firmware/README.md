# Offline camera firmware

A copy of the [AWS firmware](../../aws/ESP32-cam/firmware/README.md) with one change: instead of asking API Gateway for a presigned URL and uploading to S3 over TLS, it POSTs the JPEG straight to the offline server on your laptop over plain HTTP on the LAN. Wiring, the IR trigger, the live view, the LED signals and the serial commands are the same, so the AWS README covers those.

## Setup

1. Start the offline server (see [`offline/README.md`](../README.md)) and note your laptop's LAN IP (`ipconfig`).
2. Copy `whiteborag_cam/secrets.example.h` to `whiteborag_cam/secrets.h` (git-ignored) and fill in:
   - `WIFI_SSID` and `WIFI_PASSWORD`
   - `SERVER_URL`, e.g. `http://192.168.1.50:8080`, with no trailing slash
   - `DEVICE_KEY`, which must be one of the keys under `[devices]` in `offline/config.toml`
3. Allow inbound connections on the server port in Windows Firewall, or the camera can't reach the laptop.

## Build and flash

From `whiteborag_cam/`, with the arduino-cli bundled in the Arduino IDE:

```
arduino-cli compile --fqbn esp32:esp32:esp32cam --output-dir build .
arduino-cli upload  --fqbn esp32:esp32:esp32cam -p COMx --input-dir build .
```

Put the board in flash mode (IO0 to GND) before uploading, and press RST afterwards.

## What the server answers

| Response | LED signal | Meaning |
|---|---|---|
| 201 | upload ok | Saved to `offline/data/uploads/` and queued for ingest |
| 400 / 403 | config error | Not a JPEG, or the device key isn't in `config.toml` |
| 5xx or no answer | transient | Retried once; check that the server is running and reachable |
