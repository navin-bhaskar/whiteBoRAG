#include "feedback.h"

#include <Arduino.h>

#include "config.h"
#include "driver/ledc.h"

// The camera drives XCLK from LEDC timer 0 / channel 0 and registers neither
// with Arduino's LEDC bookkeeping, so ledcAttach() could pick timer 0 and
// retune the camera clock. Use the IDF driver on a timer and channel the
// camera never touches.
static const ledc_mode_t PWM_MODE = LEDC_HIGH_SPEED_MODE;
static const ledc_timer_t PWM_TIMER = LEDC_TIMER_1;
static const ledc_channel_t PWM_CHANNEL = LEDC_CHANNEL_1;
static const uint32_t PWM_FULL = 256;  // 8-bit resolution: 256 = always on

static void ledLevel(uint32_t duty) {
#if LED_USE_PWM
  ledc_set_duty(PWM_MODE, PWM_CHANNEL, duty);
  ledc_update_duty(PWM_MODE, PWM_CHANNEL);
#else
  digitalWrite(FLASH_LED_PIN, duty ? HIGH : LOW);
#endif
}

void feedbackBegin() {
#if LED_USE_PWM
  ledc_timer_config_t timer = {};
  timer.speed_mode = PWM_MODE;
  timer.timer_num = PWM_TIMER;
  timer.duty_resolution = LEDC_TIMER_8_BIT;
  timer.freq_hz = 5000;
  timer.clk_cfg = LEDC_AUTO_CLK;

  ledc_channel_config_t channel = {};
  channel.gpio_num = FLASH_LED_PIN;
  channel.speed_mode = PWM_MODE;
  channel.channel = PWM_CHANNEL;
  channel.timer_sel = PWM_TIMER;
  channel.duty = 0;

  if (ledc_timer_config(&timer) != ESP_OK || ledc_channel_config(&channel) != ESP_OK) {
    Serial.println("[led] PWM setup failed; set LED_USE_PWM to 0 in config.h");
  }
#else
  pinMode(FLASH_LED_PIN, OUTPUT);
  digitalWrite(FLASH_LED_PIN, LOW);
#endif
}

void flashSet(bool on) { ledLevel(on ? PWM_FULL : 0); }

static void blink(int times, uint32_t onMs, uint32_t offMs) {
  for (int i = 0; i < times; i++) {
    ledLevel(LED_DIM_DUTY);
    delay(onMs);
    ledLevel(0);
    if (i + 1 < times) delay(offMs);
  }
}

void feedbackShow(Signal s) {
  switch (s) {
    case Signal::Accepted:    blink(1, 80, 0); break;
    case Signal::UploadOk:    blink(2, 120, 150); break;
    case Signal::Transient:   blink(3, 400, 400); break;
    case Signal::ConfigError: blink(6, 80, 80); break;
  }
}
