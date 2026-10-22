#include "net.h"

#include <WiFi.h>

#include "certs.h"
#include "config.h"
#include "secrets.h"

static uint32_t offlineSince = 0;  // 0 = online

void wifiBegin() {
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
}

bool wifiEnsure() {
  if (WiFi.status() == WL_CONNECTED) return true;

  Serial.print("[wifi] waiting for connection");
  uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < WIFI_CONNECT_TIMEOUT_MS) {
    delay(250);
    Serial.print('.');
  }
  Serial.println();

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[wifi] not connected");
    return false;
  }
  Serial.printf("[wifi] connected, IP %s, RSSI %d dBm\n",
                WiFi.localIP().toString().c_str(), WiFi.RSSI());
  return true;
}

void wifiWatchdog() {
  if (WiFi.status() == WL_CONNECTED) {
    offlineSince = 0;
    return;
  }
  uint32_t now = millis();
  if (offlineSince == 0) {
    offlineSince = now ? now : 1;
    Serial.println("[wifi] offline");
  } else if (now - offlineSince > WIFI_RESTART_AFTER_MS) {
    Serial.println("[wifi] offline for 5 min, restarting");
    delay(100);
    ESP.restart();
  }
}

void tlsConfigure(WiFiClientSecure &client) {
  client.setCACert(ROOT_CA_BUNDLE);
  client.setHandshakeTimeout(10);  // seconds
}
