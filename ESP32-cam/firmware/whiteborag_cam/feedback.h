#pragma once

// Flash-LED signals. The red LED on GPIO 33 is on the back of the board, so
// feedback reuses the flash LED at low brightness.
enum class Signal {
  Accepted,     // 1 dim pulse
  UploadOk,     // 2 short dim blinks
  Transient,    // 3 slow dim blinks: network, 5xx, 429
  ConfigError,  // 6 fast dim blinks: 400/403, rejected upload
};

void feedbackBegin();
void flashSet(bool on);       // full brightness, for captures
void feedbackShow(Signal s);  // blocks until the pattern has finished
