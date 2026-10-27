#pragma once

#include <stdint.h>

// Turns a TTP223-type capacitive touch module's output into touches.
//
// The module drives its output to the active level while a finger is on the
// pad (HIGH with jumper A open, the default). The output is clean, so a touch
// is the active level held for at least minActiveMs, which rejects a stray
// glitch. A touch only counts as new if the pad was released for releaseMs
// before it, so a held finger is a single touch.
class TouchDetector {
 public:
  TouchDetector(uint8_t pin, bool activeHigh, uint32_t minActiveMs, uint32_t releaseMs);
  void begin();
  bool poll(uint32_t now);  // true when a new touch starts; call every ~1 ms
  bool touched() const { return held_; }
  bool active() const;      // raw pin reading, for touchscan

 private:
  uint8_t pin_;
  bool activeHigh_;
  uint32_t minActiveMs_;
  uint32_t releaseMs_;
  bool level_ = false;      // last raw reading (true = active)
  uint32_t levelSince_ = 0;
  bool held_ = false;       // a touch has fired and the pad isn't released yet
};
