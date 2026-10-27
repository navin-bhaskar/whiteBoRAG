// WhiteBorag capture firmware (spec §4: docs/superpowers/specs/2026-10-08-capture-ingest-design.md).
// One touch on the pad, or "snap" over serial, gets a presigned URL, captures
// a UXGA JPEG with the flash, PUTs it to S3 and reports the result on the flash LED.
// A live view (no flash) is always served for aiming the camera; see liveview.h.

#include <Arduino.h>
#include <WiFi.h>

#include "api_client.h"
#include "camera.h"
#include "config.h"
#include "feedback.h"
#include "liveview.h"
#include "net.h"
#include "trigger.h"
#include "uploader.h"

static TouchDetector touch(TOUCH_PIN, TOUCH_ACTIVE_HIGH, TOUCH_MIN_MS, TOUCH_RELEASE_MS);
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

  CapturedJpeg jpeg;
  if (!cameraCapture(flashEnabled, jpeg)) {
    lastResult = "capture failed";
    return Signal::Transient;
  }

  UploadResult up = uploadJpeg(ticket, jpeg.buf, jpeg.len);
  if (up == UploadResult::Expired) {
    Serial.println("[s3] URL expired; requesting a fresh one for the same frame");
    api = requestUploadTicket(trigger, ticket);
    if (api != ApiResult::Ok) {
      lastResult = String("api ") + apiResultName(api);
      return signalFor(api);
    }
    up = uploadJpeg(ticket, jpeg.buf, jpeg.len);
  }

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
  Serial.printf("[status] flash %s, touch %s, last: %s\n", flashEnabled ? "on" : "off",
                touch.active() ? "touched" : "clear", lastResult.c_str());
}

// Wiring check: sample the touch pin every 1 ms for 5 s and report how often it
// read as touched. Run it once without touching (expect 0 runs) and once
// tapping the pad (expect one run per tap).
static void touchScan() {
  const uint32_t SCAN_MS = 5000;
  uint32_t runs = 0, run = 0, longest = 0, activeTotal = 0;
  Serial.println("[touchscan] sampling 5 s...");
  for (uint32_t i = 0; i < SCAN_MS; i++) {
    bool on = touch.active();
    if (on) {
      run++;
      activeTotal++;
    }
    if (run > 0 && (!on || i + 1 == SCAN_MS)) {
      runs++;
      if (run > longest) longest = run;
      run = 0;
    }
    delay(1);
  }
  Serial.printf("[touchscan] touched %lu%% of the time, %lu runs, longest %lu ms (a touch needs %d)\n",
                (unsigned long)(activeTotal * 100 / SCAN_MS), (unsigned long)runs, (unsigned long)longest,
                TOUCH_MIN_MS);
}

// One touch starts a capture; handleTrigger drops touches during the cooldown.
// It reports "button": the capture API accepts only button, ir and serial.
static void pollTouch() {
  if (touch.poll(millis())) handleTrigger("button");
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
  } else if (line == "touchscan") {
    touchScan();
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
    Serial.println("Commands: snap | status | touchscan | flash on|off | signals");
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
  touch.begin();
  wifiBegin();
  liveViewBegin();
  Serial.println("Commands: snap | status | touchscan | flash on|off | signals");
}

void loop() {
  wifiWatchdog();
  liveViewPoll();
  handleSerial();
  pollTouch();
  delay(1);  // 1 ms sampling for the touch debounce
}
