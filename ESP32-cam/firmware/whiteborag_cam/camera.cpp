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
  // Single buffer + GRAB_LATEST so a capture is always a fresh frame.
  config.fb_count = 1;
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

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("[cam] init failed: 0x%x\n", err);
    return false;
  }
  Serial.println("[cam] initialised");
  return true;
}

camera_fb_t *cameraCapture(bool useFlash) {
  if (useFlash) {
    flashSet(true);
    delay(FLASH_PRE_MS);
  }
  // Discard a few frames so auto-exposure/white-balance adapt to the current
  // lighting (including the flash) before the frame we keep.
  int discard = useFlash ? FLASH_SETTLE_FRAMES : 1;
  for (int i = 0; i < discard; i++) {
    camera_fb_t *stale = esp_camera_fb_get();
    if (stale) esp_camera_fb_return(stale);
  }
  camera_fb_t *fb = esp_camera_fb_get();
  flashSet(false);

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
