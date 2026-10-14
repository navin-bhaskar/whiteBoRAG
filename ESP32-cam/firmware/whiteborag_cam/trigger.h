#pragma once

#include <stdint.h>

// Turns the IR module's active-LOW output into hand "waves".
//
// Powered from 3.3 V, the FC-51 output chatters even with nothing in front of
// it: LOW runs of 5-10 ms at roughly 35% duty. A hand holds it LOW
// continuously. So a wave is a LOW run of at least minLowMs, and it only
// counts as new if no hand was seen for rearmMs before it. A held hand, or
// one flickering at the edge of range, is therefore a single wave.
class WaveDetector {
 public:
  WaveDetector(uint8_t pin, uint32_t minLowMs, uint32_t rearmMs);
  void begin();
  bool poll(uint32_t now);  // true when a new wave starts; call every ~1 ms
  bool handPresent(uint32_t now) const;

 private:
  uint8_t pin_;
  uint32_t minLowMs_;
  uint32_t rearmMs_;
  bool low_ = false;
  uint32_t lowSince_ = 0;
  bool seenHand_ = false;
  uint32_t lastHandAt_ = 0;
};
