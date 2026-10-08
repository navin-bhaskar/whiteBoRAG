# snap_upload_s3

This is test firmware for the AI-Thinker ESP32-CAM. It takes a JPEG snapshot and uploads it with an HTTP `PUT` to an S3 pre-signed URL.

## Setup (Arduino IDE)

1. Open `snap_upload_s3.ino` in the Arduino IDE. The Wi-Fi details are already set in `config.h`, which is git-ignored. For a fresh checkout, copy `config.example.h` to `config.h`.
2. Select the board **AI Thinker ESP32-CAM** (`esp32:esp32:esp32cam`) and keep the default partition scheme, Huge APP.
3. To get the board into flash mode, connect IO0 to GND and press reset. Upload, then remove the jumper and press reset again.
4. Open the Serial Monitor at 115200 baud with the line ending set to **Newline**.
5. Generate a pre-signed URL:
   ```
   python tools/presign.py <bucket> esp32cam/test.jpg --region <region>
   ```
6. Paste the URL into the Serial Monitor and press Enter. A successful upload prints `HTTP 200` and `UPLOAD OK`.

To build from the command line, use the arduino-cli bundled with the IDE:
```
arduino-cli compile -b esp32:esp32:esp32cam --build-path build .
arduino-cli upload  -b esp32:esp32:esp32cam -p COMx --input-dir build .
```

## Serial commands

| Input                     | Action                            |
|---------------------------|-----------------------------------|
| `https://...` (presigned) | Capture a photo and upload it     |
| `snap`                    | Capture only and print the size   |
| `flash on` / `flash off` | Turn the flash LED on or off for captures (default on) |

If `S3_PRESIGNED_URL` is set in `config.h`, the device also uploads once at boot.

## Notes

- **Content-Type:** the firmware sends `Content-Type: image/jpeg`. If the URL was signed with a different `ContentType`, S3 returns `403 SignatureDoesNotMatch`.
- **TLS:** by default the server certificate is not verified (`setInsecure`). To turn on verification, define `S3_ROOT_CA` in `config.h` and set it to Amazon Root CA 1.
- **Resolution:** with PSRAM the image is UXGA (1600x1200) at quality 10. Without PSRAM it falls back to SVGA.
- **Expiry:** pre-signed URLs expire after at most 7 days. Each URL can be reused until it expires, and every reuse overwrites the same object.
- **Power:** brownout resets during Wi-Fi TX usually mean the power supply is weak. Use a solid 5 V supply that can deliver at least 1 A.
