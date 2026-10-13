// WhiteBorag capture firmware (spec §4: docs/superpowers/specs/2026-10-08-capture-ingest-design.md).
// "snap" over serial gets a presigned URL, captures a UXGA JPEG with the
// flash, PUTs it to S3 and reports the result on the flash LED.

#include <Arduino.h>
#include <WiFi.h>

#include "api_client.h"
#include "camera.h"
#include "config.h"
#include "feedback.h"
#include "net.h"
#include "uploader.h"

static bool flashEnabled = FLASH_DEFAULT_ON;
static uint32_t cooldownUntil = 0;
static String lastResult = "none";

static bool inCooldown() { return (int32_t)(millis() - cooldownUntil) < 0; }

static Signal signalFor(ApiResult r) {
  return r == ApiResult::ConfigError ? Signal::ConfigError : Signal::Transient;
}

static Signal signalFor(UploadResult r) {
  switch (r) {
    case UploadResult::Ok:       return Signal::UploadOk;
    case UploadResult::Rejected: return Signal::ConfigError;
    default:                     return Signal::Transient;
  }
}

// The spec's state machine, one blocking step per state:
// ENSURE_WIFI -> REQUEST_URL -> CAPTURE -> UPLOAD. The URL comes first so
// network and auth failures surface before the flash fires.
static Signal runCapture(const char *trigger) {
  if (!wifiEnsure()) {
    lastResult = "wifi down";
    return Signal::Transient;
  }

  UploadTicket ticket;
  ApiResult api = requestUploadTicket(trigger, ticket);
  if (api != ApiResult::Ok) {
    lastResult = String("api ") + apiResultName(api);
    return signalFor(api);
  }

  camera_fb_t *fb = cameraCapture(flashEnabled);
  if (!fb) {
    lastResult = "capture failed";
    return Signal::Transient;
  }

  UploadResult up = uploadJpeg(ticket, fb->buf, fb->len);
  if (up == UploadResult::Expired) {
    Serial.println("[s3] URL expired; requesting a fresh one for the same frame");
    api = requestUploadTicket(trigger, ticket);
    if (api != ApiResult::Ok) {
      esp_camera_fb_return(fb);
      lastResult = String("api ") + apiResultName(api);
      return signalFor(api);
    }
    up = uploadJpeg(ticket, fb->buf, fb->len);
  }
  esp_camera_fb_return(fb);

  lastResult = up == UploadResult::Ok ? "ok " + ticket.key : String("upload ") + uploadResultName(up);
  return signalFor(up);
}

static void handleTrigger(const char *trigger) {
  if (inCooldown()) {
    Serial.printf("[run] %s trigger ignored (cooldown)\n", trigger);
    return;
  }
  uint32_t t0 = millis();
  Serial.printf("[run] trigger %s\n", trigger);
  feedbackShow(Signal::Accepted);
  Signal result = runCapture(trigger);
  feedbackShow(result);
  Serial.printf("[run] %s (%lu ms)\n", lastResult.c_str(), (unsigned long)(millis() - t0));
  cooldownUntil = millis() + COOLDOWN_MS;  // after every attempt, success or failure
}

static void printStatus() {
  bool up = WiFi.status() == WL_CONNECTED;
  Serial.printf("[status] wifi %s, RSSI %d dBm, IP %s\n", up ? "up" : "down",
                up ? WiFi.RSSI() : 0, WiFi.localIP().toString().c_str());
  Serial.printf("[status] heap %lu free, PSRAM %lu free\n", (unsigned long)ESP.getFreeHeap(),
                (unsigned long)ESP.getFreePsram());
  Serial.printf("[status] flash %s, last: %s\n", flashEnabled ? "on" : "off", lastResult.c_str());
}

static void handleSerial() {
  if (!Serial.available()) return;
  String line = Serial.readStringUntil('\n');
  line.trim();
  if (line.length() == 0) return;

  if (line == "snap") {
    handleTrigger("serial");
  } else if (line == "status") {
    printStatus();
  } else if (line == "flash on" || line == "flash off") {
    flashEnabled = (line == "flash on");
    Serial.printf("[cam] flash %s\n", flashEnabled ? "on" : "off");
  } else if (line == "signals") {
    // Bench check of every feedback pattern, in table order.
    const Signal all[] = {Signal::Accepted, Signal::UploadOk, Signal::Transient, Signal::ConfigError};
    for (Signal s : all) {
      feedbackShow(s);
      delay(1000);
    }
  } else {
    Serial.println("Commands: snap | status | flash on|off | signals");
  }
}

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.printf("\n=== WhiteBorag cam %s ===\n", DEVICE_ID);

  if (!cameraBegin()) {
    Serial.println("camera init failed, restarting in 5 s");
    delay(5000);
    ESP.restart();
  }
  feedbackBegin();
  wifiBegin();
  Serial.println("Commands: snap | status | flash on|off | signals");
}

void loop() {
  wifiWatchdog();
  handleSerial();
  delay(5);
}
