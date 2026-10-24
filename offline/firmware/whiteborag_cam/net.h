#pragma once

void wifiBegin();
bool wifiEnsure();    // waits up to WIFI_CONNECT_TIMEOUT_MS for a connection
void wifiWatchdog();  // call every loop(); restarts after 5 min offline

