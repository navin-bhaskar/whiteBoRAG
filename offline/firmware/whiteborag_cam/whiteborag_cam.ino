// WhiteBorag offline capture firmware: a copy of aws/ESP32-cam/firmware that posts to the laptop.
// One touch on the pad, or "snap" over serial, captures a UXGA JPEG with the flash, POSTs it to the
// offline server on the LAN and reports the result on the flash LED.
// A live view (no flash) is always served for aiming the camera; see liveview.h.

#include <Arduino.h>
#include <WiFi.h>

#include "camera.h"
#include "config.h"
#include "feedback.h"
#include "liveview.h"
#include "local_uploader.h"
#include "net.h"
#include "trigger.h"

static TouchDetector touch(TOUCH_PIN, TOUCH_ACTIVE_HIGH, TOUCH_MIN_MS, TOUCH_RELEASE_MS);
static bool flashEnabled = FLASH_DEFAULT_ON;
static uint32_t cooldownUntil = 0;
static String lastResult = "none";

static bool inCooldown() { return (int32_t)(millis() - cooldownUntil) < 0; }

static Signal signalFor(PostResult r) {
  switch (r) {
    case PostResult::Ok:          return Signal::UploadOk;
    case PostResult::ConfigError: return Signal::ConfigError;
    default:                      return Signal::Transient;
  }
}

// ENSURE_WIFI -> CAPTURE -> POST. With no presigned URL to fetch, the photo goes up in one request.
static Signal runCapture(const char *trigger) {
  if (!wifiEnsure()) {
    lastResult = "wifi down";
    return Signal::Transient;
  }

  CapturedJpeg jpeg;
  if (!cameraCapture(flashEnabled, jpeg)) {
    lastResult = "capture failed";
    return Signal::Transient;
  }

  String key;
  PostResult r = postCapture(trigger, jpeg.buf, jpeg.len, key);
  lastResult = r == PostResult::Ok ? "ok " + key : String("post ") + postResultName(r);
  return signalFor(r);
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
static void pollTouch() {
  if (touch.poll(millis())) handleTrigger("touch");
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
