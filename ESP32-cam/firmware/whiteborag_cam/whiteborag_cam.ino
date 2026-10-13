// WhiteBorag capture firmware (spec §4: docs/superpowers/specs/2026-10-08-capture-ingest-design.md).
// Stage 1: camera + flash-LED feedback only. Network and IR arrive in later tasks.

#include <Arduino.h>

#include "camera.h"
#include "config.h"
#include "feedback.h"

static bool flashEnabled = FLASH_DEFAULT_ON;

static void handleSerial() {
  if (!Serial.available()) return;
  String line = Serial.readStringUntil('\n');
  line.trim();
  if (line.length() == 0) return;

  if (line == "snap") {
    camera_fb_t *fb = cameraCapture(flashEnabled);
    if (fb) esp_camera_fb_return(fb);
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
    Serial.println("Commands: snap | flash on|off | signals");
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
  Serial.println("Commands: snap | flash on|off | signals");
}

void loop() {
  handleSerial();
  delay(5);
}
