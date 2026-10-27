#include "trigger.h"

#include <Arduino.h>

TouchDetector::TouchDetector(uint8_t pin, bool activeHigh, uint32_t minActiveMs, uint32_t releaseMs)
    : pin_(pin), activeHigh_(activeHigh), minActiveMs_(minActiveMs), releaseMs_(releaseMs) {}

void TouchDetector::begin() {
  // Pull towards the idle level, so an unplugged sensor never reads as a touch.
  pinMode(pin_, activeHigh_ ? INPUT_PULLDOWN : INPUT_PULLUP);
}

bool TouchDetector::active() const {
  return (digitalRead(pin_) == HIGH) == activeHigh_;
}

bool TouchDetector::poll(uint32_t now) {
  bool level = active();
  if (level != level_) {
    level_ = level;
    levelSince_ = now;
  }
  uint32_t steady = now - levelSince_;
  if (!level_) {
    if (held_ && steady >= releaseMs_) held_ = false;  // released long enough: re-armed
    return false;
  }
  if (held_ || steady < minActiveMs_) return false;
  held_ = true;
  return true;
}
