// Ported from ESP32-cam/testing/snap_upload_s3, where these settings are verified.
#include "camera.h"

#include <Arduino.h>

#include "config.h"
#include "feedback.h"

// AI-Thinker ESP32-CAM pin map
#define PWDN_GPIO_NUM  32
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM   0
#define SIOD_GPIO_NUM  26
#define SIOC_GPIO_NUM  27
#define Y9_GPIO_NUM    35
#define Y8_GPIO_NUM    34
#define Y7_GPIO_NUM    39
#define Y6_GPIO_NUM    36
#define Y5_GPIO_NUM    21
#define Y4_GPIO_NUM    19
#define Y3_GPIO_NUM    18
#define Y2_GPIO_NUM     5
#define VSYNC_GPIO_NUM 25
#define HREF_GPIO_NUM  23
#define PCLK_GPIO_NUM  22

static framesize_t captureSize = FRAMESIZE_UXGA;
static SemaphoreHandle_t camLock = nullptr;  // live view and captures take turns

static bool setFrameSize(framesize_t size) {
  sensor_t *s = esp_camera_sensor_get();
  return s && s->set_framesize(s, size) == 0;
}

static uint8_t *bufAlloc(uint8_t *old, size_t n) {
  return (uint8_t *)(psramFound() ? ps_realloc(old, n) : realloc(old, n));
}

bool cameraBegin() {
  camera_config_t config = {};
  config.ledc_channel = LEDC_CHANNEL_0;  // XCLK; feedback.cpp keeps clear of these
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  // Two buffers keep the live view moving; GRAB_LATEST plus the discarded
  // frames in cameraCapture() keep captures fresh.
  config.fb_count = 2;
  config.grab_mode = CAMERA_GRAB_LATEST;

  if (psramFound()) {
    config.frame_size = FRAMESIZE_UXGA;  // 1600x1200
    config.jpeg_quality = 10;            // 0-63, lower = better
    config.fb_location = CAMERA_FB_IN_PSRAM;
  } else {
    Serial.println("[cam] WARNING: no PSRAM, falling back to SVGA");
    config.frame_size = FRAMESIZE_SVGA;
    config.jpeg_quality = 12;
    config.fb_location = CAMERA_FB_IN_DRAM;
  }

  captureSize = config.frame_size;
  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("[cam] init failed: 0x%x\n", err);
    return false;
  }
  camLock = xSemaphoreCreateMutex();
  if (!camLock || !setFrameSize(STREAM_FRAMESIZE)) {
    Serial.println("[cam] could not switch to live-view size");
    return false;
  }
  Serial.println("[cam] initialised");
  return true;
}

// Holds camLock while it runs, so the live view pauses for about a second.
static camera_fb_t *grabCaptureFrame(bool useFlash) {
  if (!setFrameSize(captureSize)) {
    Serial.println("[cam] could not switch to capture size");
    return nullptr;
  }
  if (useFlash) {
    flashSet(true);
    delay(FLASH_PRE_MS);
  }
  // Discard frames so both buffers hold full-size frames and auto-exposure/
  // white-balance adapt to the current lighting (including the flash).
  int discard = useFlash ? FLASH_SETTLE_FRAMES : 0;
  if (discard < 2) discard = 2;
  for (int i = 0; i < discard; i++) {
    camera_fb_t *stale = esp_camera_fb_get();
    if (stale) esp_camera_fb_return(stale);
  }
  camera_fb_t *fb = esp_camera_fb_get();
  flashSet(false);
  return fb;
}

bool cameraCapture(bool useFlash, CapturedJpeg &out) {
  xSemaphoreTake(camLock, portMAX_DELAY);
  camera_fb_t *fb = grabCaptureFrame(useFlash);
  bool ok = false;
  if (!fb) {
    Serial.println("[cam] capture failed");
  } else if (fb->format != PIXFORMAT_JPEG) {
    Serial.println("[cam] frame is not JPEG");
  } else if (!(out.buf = bufAlloc(nullptr, fb->len))) {
    Serial.printf("[cam] no memory for a %u byte frame\n", fb->len);
  } else {
    memcpy(out.buf, fb->buf, fb->len);
    out.len = fb->len;
    Serial.printf("[cam] captured %ux%u, %u bytes\n", fb->width, fb->height, fb->len);
    ok = true;
  }
  if (fb) esp_camera_fb_return(fb);
  if (!setFrameSize(STREAM_FRAMESIZE)) Serial.println("[cam] could not switch back to live-view size");
  xSemaphoreGive(camLock);
  return ok;
}

bool cameraStreamFrame(uint8_t *&buf, size_t &cap, size_t &len) {
  xSemaphoreTake(camLock, portMAX_DELAY);
  camera_fb_t *fb = esp_camera_fb_get();
  bool ok = false;
  if (fb && fb->format == PIXFORMAT_JPEG) {
    if (fb->len > cap) {
      uint8_t *grown = bufAlloc(buf, fb->len);
      if (grown) {
        buf = grown;
        cap = fb->len;
      }
    }
    if (fb->len <= cap) {
      memcpy(buf, fb->buf, fb->len);
      len = fb->len;
      ok = true;
    }
  }
  if (fb) esp_camera_fb_return(fb);
  xSemaphoreGive(camLock);
  return ok;
}
