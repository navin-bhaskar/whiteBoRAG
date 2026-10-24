#include "trigger.h"

#include <Arduino.h>

WaveDetector::WaveDetector(uint8_t pin, uint32_t minLowMs, uint32_t rearmMs)
    : pin_(pin), minLowMs_(minLowMs), rearmMs_(rearmMs) {}

void WaveDetector::begin() {
  pinMode(pin_, INPUT_PULLUP);  // an unplugged sensor reads HIGH and never fires
}

bool WaveDetector::poll(uint32_t now) {
  bool low = digitalRead(pin_) == LOW;
  if (low != low_) {
    low_ = low;
    lowSince_ = now;
  }
  if (!low_ || now - lowSince_ < minLowMs_) return false;  // idle chatter stops here

  // A hand is in front. While it stays, lastHandAt_ keeps moving, so it
  // never re-fires; it must be gone for rearmMs before the next wave counts.
  bool newWave = !seenHand_ || now - lastHandAt_ >= rearmMs_;
  seenHand_ = true;
  lastHandAt_ = now;
  return newWave;
}

bool WaveDetector::handPresent(uint32_t now) const {
  return seenHand_ && now - lastHandAt_ < rearmMs_;
}
