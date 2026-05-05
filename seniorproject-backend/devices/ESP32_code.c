#include <WiFi.h>
#include <HTTPClient.h>
#include <Wire.h>
#include <Adafruit_AHTX0.h>
#include "DFRobot_ENS160.h"
#include <time.h>
#include <sys/time.h>
#include "esp_timer.h"

// =====================================
// Wi-Fi
// =====================================
const char* ssid     = "Nassernxs";
const char* password = "nasser04";

// =====================================
// Raspberry Pi hub endpoint
// =====================================
const char* PI_SERVER_URL = "http://10.220.38.94:5000/api/sensors/room1";
const char* ESP32_DEVICE_KEY = "esp32_01_key_123";

// Disabled because sensor data now goes through Raspberry Pi hub.
// Previous direct Firebase base URL:
// const char* firebaseBaseURL =
//   "https://seniorproject-energy-default-rtdb.asia-southeast1.firebasedatabase.app";

// =====================================
// Pin definitions
// =====================================
#define LIGHT_PIN   34
#define MQ2_PIN     35
#define PIR_PIN     27
#define SOUND_PIN   32

#define I2C_SDA     21
#define I2C_SCL     22

// =====================================
// Sensor objects
// =====================================
Adafruit_AHTX0 aht;
DFRobot_ENS160_I2C ens160(&Wire, 0x53);

// =====================================
// Settings
// =====================================
unsigned long lastSendTime = 0;
const unsigned long sendInterval = 3000;
int mq2Threshold = 900;
int soundThreshold = 1800;   // adjust after testing

unsigned long lastNtpCheck = 0;
const unsigned long ntpCheckInterval = 10000;

// =====================================
// Status flags
// =====================================
bool ahtAvailable = false;
bool ens160Available = false;
bool ntpSynced = false;

// =====================================
// Wi-Fi
// =====================================
void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;

  Serial.print("Connecting to Wi-Fi");
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);
  WiFi.setAutoReconnect(true);
  WiFi.persistent(true);

  int retries = 0;
  while (WiFi.status() != WL_CONNECTED && retries < 40) {
    delay(500);
    Serial.print(".");
    retries++;
  }

  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("Wi-Fi connected");
    Serial.print("IP: ");
    Serial.println(WiFi.localIP());
    Serial.print("RSSI: ");
    Serial.println(WiFi.RSSI());
  } else {
    Serial.println("Wi-Fi connection failed");
  }
}

// =====================================
// Time / NTP
// =====================================
bool timeIsValid() {
  time_t now;
  time(&now);
  return now > 1700000000;
}

void startNTP() {
  configTime(0, 0, "pool.ntp.org", "time.nist.gov", "time.google.com");
  setenv("TZ", "AST-3", 1);
  tzset();
  Serial.println("NTP started");
}

void checkTimeSync() {
  bool wasSynced = ntpSynced;
  ntpSynced = timeIsValid();

  if (!wasSynced && ntpSynced) {
    struct tm timeinfo;
    if (getLocalTime(&timeinfo)) {
      Serial.println("NTP synchronized successfully");
      Serial.println(&timeinfo, "%Y-%m-%d %H:%M:%S");
    }
  }
}

unsigned long getTimestampSec() {
  if (timeIsValid()) {
    time_t now;
    time(&now);
    return (unsigned long)now;
  }

  return millis() / 1000;
}

unsigned long long getTimestampMs() {
  if (timeIsValid()) {
    struct timeval tv;
    gettimeofday(&tv, NULL);
    return ((unsigned long long)tv.tv_sec * 1000ULL) + (tv.tv_usec / 1000ULL);
  }

  return (unsigned long long)(esp_timer_get_time() / 1000ULL);
}

String getReadableTime() {
  if (!timeIsValid()) {
    return "unknown";
  }

  struct tm timeinfo;
  if (!getLocalTime(&timeinfo)) {
    return "unknown";
  }

  char buffer[25];
  strftime(buffer, sizeof(buffer), "%Y-%m-%d %H:%M:%S", &timeinfo);
  return String(buffer);
}

// =====================================
// Sensors
// =====================================
void initSensors() {
  pinMode(LIGHT_PIN, INPUT);
  pinMode(MQ2_PIN, INPUT);
  pinMode(PIR_PIN, INPUT);
  pinMode(SOUND_PIN, INPUT);

  Wire.begin(I2C_SDA, I2C_SCL);
  delay(300);

  ahtAvailable = aht.begin();
  if (ahtAvailable) {
    Serial.println("AHT21 initialized");
  } else {
    Serial.println("AHT21 not detected");
  }

  int ensRetries = 0;
  while (NO_ERR != ens160.begin() && ensRetries < 10) {
    Serial.println("ENS160 not detected, retrying...");
    delay(1000);
    ensRetries++;
  }

  if (ensRetries < 10) {
    ens160Available = true;
    ens160.setPWRMode(ENS160_STANDARD_MODE);
    Serial.println("ENS160 initialized");
  } else {
    ens160Available = false;
    Serial.println("ENS160 failed to initialize");
  }
}

bool readAHT(float &temperature, float &humidity) {
  if (!ahtAvailable) {
    temperature = -1.0;
    humidity = -1.0;
    return false;
  }

  sensors_event_t humidityEvent, tempEvent;
  aht.getEvent(&humidityEvent, &tempEvent);

  temperature = tempEvent.temperature;
  humidity = humidityEvent.relative_humidity;

  if (isnan(temperature) || isnan(humidity)) {
    temperature = -1.0;
    humidity = -1.0;
    return false;
  }

  return true;
}

bool readENS160(float temperature, float humidity, uint8_t &aqi, uint16_t &tvoc, uint16_t &eco2) {
  if (!ens160Available) {
    aqi = 0;
    tvoc = 0;
    eco2 = 0;
    return false;
  }

  if (temperature >= 0 && humidity >= 0) {
    ens160.setTempAndHum(temperature, humidity);
  }

  aqi = ens160.getAQI();
  tvoc = ens160.getTVOC();
  eco2 = ens160.getECO2();
  return true;
}

// =====================================
// HTTP sender
// =====================================
bool sendPostRequest(const String& url, const String& jsonPayload) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("Wi-Fi not connected");
    return false;
  }

  HTTPClient http;

  if (!http.begin(url)) {
    Serial.println("Failed to start HTTP connection");
    return false;
  }

  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Device-Key", ESP32_DEVICE_KEY);

  int httpCode = http.POST(jsonPayload);

  Serial.print("HTTP response code: ");
  Serial.println(httpCode);

  if (httpCode > 0) {
    String response = http.getString();
    Serial.println("Raspberry Pi response:");
    Serial.println(response);
    http.end();
    return httpCode >= 200 && httpCode < 300;
  } else {
    Serial.print("Request failed: ");
    Serial.println(http.errorToString(httpCode));
    http.end();
    return false;
  }
}

// =====================================
// JSON builders
// =====================================
String buildLiveJson(
  float temperature,
  float humidity,
  bool aht_ok,
  uint8_t aqi,
  uint16_t tvoc,
  uint16_t eco2,
  bool ens160_ok,
  int lightRaw,
  String lightStatus,
  int motion,
  String motionText,
  int mq2Raw,
  int smokeDetected,
  String smokeText,
  int soundRaw,
  int noiseDetected,
  String noiseText,
  unsigned long tsSec,
  unsigned long long tsMs,
  String readableTime
) {
  String jsonData = "{";

  jsonData += "\"status\":{";
  jsonData += "\"online\":true,";
  jsonData += "\"lastSeen\":" + String(tsSec) + ",";
  jsonData += "\"lastSeenMs\":" + String(tsMs) + ",";
  jsonData += "\"readableTime\":\"" + readableTime + "\",";
  jsonData += "\"wifiRssi\":" + String(WiFi.RSSI()) + ",";
  jsonData += "\"ntp_synced\":" + String(ntpSynced ? "true" : "false");
  jsonData += "},";

  jsonData += "\"sensors\":{";
  jsonData += "\"temperature\":" + String(temperature, 2) + ",";
  jsonData += "\"humidity\":" + String(humidity, 2) + ",";
  jsonData += "\"aht_ok\":" + String(aht_ok ? "true" : "false") + ",";
  jsonData += "\"aqi\":" + String(aqi) + ",";
  jsonData += "\"tvoc\":" + String(tvoc) + ",";
  jsonData += "\"eco2\":" + String(eco2) + ",";
  jsonData += "\"ens160_ok\":" + String(ens160_ok ? "true" : "false") + ",";
  jsonData += "\"light_raw\":" + String(lightRaw) + ",";
  jsonData += "\"light_status\":\"" + lightStatus + "\",";
  jsonData += "\"motion\":" + String(motion) + ",";
  jsonData += "\"motion_text\":\"" + motionText + "\",";
  jsonData += "\"smoke_raw\":" + String(mq2Raw) + ",";
  jsonData += "\"smoke\":" + String(smokeDetected) + ",";
  jsonData += "\"smoke_text\":\"" + smokeText + "\",";
  jsonData += "\"sound_raw\":" + String(soundRaw) + ",";
  jsonData += "\"noise\":" + String(noiseDetected) + ",";
  jsonData += "\"noise_text\":\"" + noiseText + "\",";
  jsonData += "\"timestamp\":" + String(tsSec) + ",";
  jsonData += "\"timestamp_ms\":" + String(tsMs) + ",";
  jsonData += "\"readable_time\":\"" + readableTime + "\"";
  jsonData += "}";

  jsonData += "}";

  return jsonData;
}

String buildHistoryJson(
  float temperature,
  float humidity,
  bool aht_ok,
  uint8_t aqi,
  uint16_t tvoc,
  uint16_t eco2,
  bool ens160_ok,
  int lightRaw,
  String lightStatus,
  int motion,
  String motionText,
  int mq2Raw,
  int smokeDetected,
  String smokeText,
  int soundRaw,
  int noiseDetected,
  String noiseText,
  unsigned long tsSec,
  unsigned long long tsMs,
  String readableTime
) {
  String jsonData = "{";

  jsonData += "\"timestamp\":" + String(tsSec) + ",";
  jsonData += "\"timestamp_ms\":" + String(tsMs) + ",";
  jsonData += "\"readable_time\":\"" + readableTime + "\",";
  jsonData += "\"ntp_synced\":" + String(ntpSynced ? "true" : "false") + ",";
  jsonData += "\"temperature\":" + String(temperature, 2) + ",";
  jsonData += "\"humidity\":" + String(humidity, 2) + ",";
  jsonData += "\"aht_ok\":" + String(aht_ok ? "true" : "false") + ",";
  jsonData += "\"aqi\":" + String(aqi) + ",";
  jsonData += "\"tvoc\":" + String(tvoc) + ",";
  jsonData += "\"eco2\":" + String(eco2) + ",";
  jsonData += "\"ens160_ok\":" + String(ens160_ok ? "true" : "false") + ",";
  jsonData += "\"light_raw\":" + String(lightRaw) + ",";
  jsonData += "\"light_status\":\"" + lightStatus + "\",";
  jsonData += "\"motion\":" + String(motion) + ",";
  jsonData += "\"motion_text\":\"" + motionText + "\",";
  jsonData += "\"smoke_raw\":" + String(mq2Raw) + ",";
  jsonData += "\"smoke\":" + String(smokeDetected) + ",";
  jsonData += "\"smoke_text\":\"" + smokeText + "\",";
  jsonData += "\"sound_raw\":" + String(soundRaw) + ",";
  jsonData += "\"noise\":" + String(noiseDetected) + ",";
  jsonData += "\"noise_text\":\"" + noiseText + "\"";

  jsonData += "}";

  return jsonData;
}

// =====================================
// Upload data
// =====================================
void uploadData() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("Wi-Fi disconnected, reconnecting...");
    connectWiFi();
    if (WiFi.status() != WL_CONNECTED) {
      Serial.println("Upload skipped: no Wi-Fi");
      return;
    }
  }

  checkTimeSync();

  int lightRaw = analogRead(LIGHT_PIN);
  int mq2Raw = analogRead(MQ2_PIN);
  int soundRaw = analogRead(SOUND_PIN);

  int smokeDetected = (mq2Raw > mq2Threshold) ? 1 : 0;
  int noiseDetected = (soundRaw > soundThreshold) ? 1 : 0;

  int motion = digitalRead(PIR_PIN);

  float temperature = -1.0;
  float humidity = -1.0;
  bool aht_ok = readAHT(temperature, humidity);

  uint8_t aqi = 0;
  uint16_t tvoc = 0;
  uint16_t eco2 = 0;
  bool ens160_ok = readENS160(temperature, humidity, aqi, tvoc, eco2);

  unsigned long tsSec = getTimestampSec();
  unsigned long long tsMs = getTimestampMs();
  String readableTime = getReadableTime();

  String lightStatus = (lightRaw < 1000) ? "Dark" : "Bright";
  String motionText = (motion == 1) ? "Motion detected" : "No motion";
  String smokeText = (smokeDetected == 1) ? "Detected" : "Clear";
  String noiseText = (noiseDetected == 1) ? "Noise detected" : "Quiet";

  String liveJson = buildLiveJson(
    temperature, humidity, aht_ok,
    aqi, tvoc, eco2, ens160_ok,
    lightRaw, lightStatus,
    motion, motionText,
    mq2Raw, smokeDetected, smokeText,
    soundRaw, noiseDetected, noiseText,
    tsSec, tsMs, readableTime
  );

  // Disabled because sensor data now goes through Raspberry Pi hub.
  // Previous direct Firebase upload targets:
  // String liveURL = String(firebaseBaseURL) +
  //   "/homes/home_001/devices/esp32_01.json";
  // String historyURL = String(firebaseBaseURL) +
  //   "/homes/home_001/history/sensor_logs/" + String(tsMs) + ".json";

  Serial.println("========== SENSOR DATA ==========");
  Serial.print("Readable Time : ");
  Serial.println(readableTime);
  Serial.print("Timestamp Sec : ");
  Serial.println(tsSec);
  Serial.print("Timestamp Ms  : ");
  Serial.println(tsMs);
  Serial.print("NTP Synced    : ");
  Serial.println(ntpSynced ? "true" : "false");
  Serial.print("AHT OK        : ");
  Serial.println(aht_ok ? "true" : "false");
  Serial.print("ENS160 OK     : ");
  Serial.println(ens160_ok ? "true" : "false");
  Serial.print("Temperature   : ");
  Serial.println(temperature);
  Serial.print("Humidity      : ");
  Serial.println(humidity);
  Serial.print("AQI           : ");
  Serial.println(aqi);
  Serial.print("TVOC          : ");
  Serial.println(tvoc);
  Serial.print("eCO2          : ");
  Serial.println(eco2);
  Serial.print("Light Raw     : ");
  Serial.println(lightRaw);
  Serial.print("Light Status  : ");
  Serial.println(lightStatus);
  Serial.print("Motion        : ");
  Serial.println(motionText);
  Serial.print("MQ2 Raw       : ");
  Serial.println(mq2Raw);
  Serial.print("Smoke/Gas     : ");
  Serial.println(smokeText);
  Serial.print("Sound Raw     : ");
  Serial.println(soundRaw);
  Serial.print("Noise         : ");
  Serial.println(noiseText);
  Serial.println("================================");

  Serial.println("Sending sensor data to Raspberry Pi hub...");
  bool piOk = sendPostRequest(String(PI_SERVER_URL), liveJson);

  Serial.print("Pi hub upload  : ");
  Serial.println(piOk ? "SUCCESS" : "FAILED");
}

// =====================================
// Setup
// =====================================
void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("Starting setup...");

  connectWiFi();
  Serial.println("Wi-Fi step done");

  startNTP();
  checkTimeSync();
  Serial.println("Time step done");

  initSensors();
  Serial.println("Sensor step done");

  Serial.println("Setup complete");
}

// =====================================
// Loop
// =====================================
void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
  }

  if (millis() - lastNtpCheck >= ntpCheckInterval) {
    lastNtpCheck = millis();
    checkTimeSync();
  }

  if (millis() - lastSendTime >= sendInterval) {
    lastSendTime = millis();
    uploadData();
  }
}
