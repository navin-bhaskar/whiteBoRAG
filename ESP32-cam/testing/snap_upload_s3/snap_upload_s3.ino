// ESP32-CAM test firmware: take a snapshot and upload it to an S3 pre-signed URL.
//
// Usage (serial monitor @ 115200, line ending = Newline):
//   - Paste a pre-signed PUT URL and press Enter -> capture + upload
//   - Type "snap" -> capture only, print the JPEG size
//   - Type "flash on" / "flash off" -> enable/disable the on-board flash LED
//   - If S3_PRESIGNED_URL is set in config.h, one upload is attempted at boot.

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include "esp_camera.h"
#include "config.h"

// ---- AI-Thinker ESP32-CAM pin map ----
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

#define FLASH_LED_PIN      4

#ifndef FLASH_DEFAULT_ON
#define FLASH_DEFAULT_ON    1
#endif
#ifndef FLASH_PRE_MS
#define FLASH_PRE_MS      100
#endif
#ifndef FLASH_SETTLE_FRAMES
#define FLASH_SETTLE_FRAMES 3
#endif

static bool flashEnabled = FLASH_DEFAULT_ON;

static bool initCamera() {
  camera_config_t config = {};
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk     = XCLK_GPIO_NUM;
  config.pin_pclk     = PCLK_GPIO_NUM;
  config.pin_vsync    = VSYNC_GPIO_NUM;
  config.pin_href     = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn     = PWDN_GPIO_NUM;
  config.pin_reset    = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  // Single buffer + GRAB_LATEST so a capture is always a fresh frame.
  config.fb_count  = 1;
  config.grab_mode = CAMERA_GRAB_LATEST;

  if (psramFound()) {
    config.frame_size   = FRAMESIZE_UXGA;  // 1600x1200
    config.jpeg_quality = 10;              // 0-63, lower = better
    config.fb_location  = CAMERA_FB_IN_PSRAM;
  } else {
    Serial.println("[cam] WARNING: no PSRAM, falling back to SVGA");
    config.frame_size   = FRAMESIZE_SVGA;
    config.jpeg_quality = 12;
    config.fb_location  = CAMERA_FB_IN_DRAM;
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("[cam] init failed: 0x%x\n", err);
    return false;
  }
  Serial.println("[cam] initialised");
  return true;
}

// Returns a frame buffer that the caller must release with esp_camera_fb_return().
static camera_fb_t *captureJpeg() {
  if (flashEnabled) {
    digitalWrite(FLASH_LED_PIN, HIGH);
    delay(FLASH_PRE_MS);
  }
  // Discard a few frames so auto-exposure/white-balance adapt to the current
  // lighting (including the flash) before the frame we keep.
  int discard = flashEnabled ? FLASH_SETTLE_FRAMES : 1;
  for (int i = 0; i < discard; i++) {
    camera_fb_t *stale = esp_camera_fb_get();
    if (stale) esp_camera_fb_return(stale);
  }
  camera_fb_t *fb = esp_camera_fb_get();
  digitalWrite(FLASH_LED_PIN, LOW);

  if (!fb) {
    Serial.println("[cam] capture failed");
    return nullptr;
  }
  if (fb->format != PIXFORMAT_JPEG) {
    Serial.println("[cam] frame is not JPEG");
    esp_camera_fb_return(fb);
    return nullptr;
  }
  Serial.printf("[cam] captured %ux%u, %u bytes\n", fb->width, fb->height, fb->len);
  return fb;
}

static bool connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) return true;

  Serial.printf("[wifi] connecting to %s", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 20000) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[wifi] connection failed");
    return false;
  }
  Serial.printf("[wifi] connected, IP %s, RSSI %d dBm\n",
                WiFi.localIP().toString().c_str(), WiFi.RSSI());
  return true;
}

// HTTP PUT the JPEG to a pre-signed S3 URL. S3 returns 200 on success.
static bool uploadToS3(const String &url, const uint8_t *data, size_t len) {
  if (!url.startsWith("https://")) {
    Serial.println("[s3] URL must start with https://");
    return false;
  }

  WiFiClientSecure client;
#ifdef S3_ROOT_CA
  client.setCACert(S3_ROOT_CA);
#else
  client.setInsecure();  // test only: skips server certificate verification
#endif

  HTTPClient http;
  http.setTimeout(30000);
  if (!http.begin(client, url)) {
    Serial.println("[s3] http.begin failed (bad URL?)");
    return false;
  }
  http.addHeader("Content-Type", UPLOAD_CONTENT_TYPE);

  Serial.printf("[s3] uploading %u bytes...\n", len);
  uint32_t t0 = millis();
  int code = http.sendRequest("PUT", const_cast<uint8_t *>(data), len);
  uint32_t dt = millis() - t0;

  bool ok = (code == 200);
  if (code > 0) {
    Serial.printf("[s3] HTTP %d in %lu ms\n", code, (unsigned long)dt);
    if (!ok) {
      // S3 explains failures in an XML body (SignatureDoesNotMatch, AccessDenied, ...).
      Serial.println(http.getString());
    }
  } else {
    Serial.printf("[s3] request failed: %s\n", http.errorToString(code).c_str());
  }
  http.end();
  return ok;
}

static void snapAndUpload(const String &url) {
  if (!connectWiFi()) return;

  camera_fb_t *fb = captureJpeg();
  if (!fb) return;

  bool ok = uploadToS3(url, fb->buf, fb->len);
  esp_camera_fb_return(fb);
  Serial.println(ok ? "[s3] UPLOAD OK" : "[s3] UPLOAD FAILED");
}

void setup() {
  // Pre-signed URLs are often >1 KB; make sure a pasted URL fits in the RX buffer.
  Serial.setRxBufferSize(4096);
  Serial.begin(115200);
  delay(500);
  Serial.println("\n=== ESP32-CAM snap -> S3 pre-signed URL test ===");

  pinMode(FLASH_LED_PIN, OUTPUT);
  digitalWrite(FLASH_LED_PIN, LOW);

  if (!initCamera()) {
    Serial.println("Camera init failed, restarting in 5 s");
    delay(5000);
    ESP.restart();
  }

  connectWiFi();

  String bootUrl = S3_PRESIGNED_URL;
  if (bootUrl.length() > 0) {
    snapAndUpload(bootUrl);
  }

  Serial.println("Paste a pre-signed PUT URL and press Enter, type 'snap', or 'flash on|off'.");
}

void loop() {
  if (!Serial.available()) {
    delay(10);
    return;
  }

  String line = Serial.readStringUntil('\n');
  line.trim();
  if (line.length() == 0) return;

  if (line == "snap") {
    camera_fb_t *fb = captureJpeg();
    if (fb) esp_camera_fb_return(fb);
  } else if (line == "flash on" || line == "flash off") {
    flashEnabled = (line == "flash on");
    Serial.printf("[cam] flash %s\n", flashEnabled ? "ON" : "OFF");
  } else if (line.startsWith("http")) {
    snapAndUpload(line);
  } else {
    Serial.println("Unknown input. Paste an https:// pre-signed URL, type 'snap', or 'flash on|off'.");
  }
  Serial.println("Ready.");
}
