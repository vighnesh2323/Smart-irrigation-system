#include <WiFi.h>
#include <HTTPClient.h>
#include "DHT.h"

// ------------------- Hardware Pins -------------------
#define SOIL_MOISTURE_ANALOG 34   // Analog sensor for monitoring
#define SOIL_MOISTURE_DIGITAL 21  // Digital sensor to control pump
#define PUMP_PIN 26
#define DHTPIN 18
#define DHTTYPE DHT11
DHT dht(DHTPIN, DHTTYPE);

// ------------------- ThingSpeak -------------------
const char* WIFI_SSID = "abcd";
const char* WIFI_PASS = "00000000";
const char* TS_WRITE_KEY = "6SP78VL51TQZKI7E";
const char* TS_SERVER = "http://api.thingspeak.com/update";

// ------------------- Functions -------------------
int readSoilMoistureAnalog() {
  int raw = analogRead(SOIL_MOISTURE_ANALOG);
  return raw;  // Just raw value, no percentage
}

void sendSensorData() {
  int soilAnalog = readSoilMoistureAnalog();
  int soilDigital = digitalRead(SOIL_MOISTURE_DIGITAL); // 1 = dry, 0 = wet
  float temperature = dht.readTemperature();
  float humidity = dht.readHumidity();

  // ------------------- Serial Output -------------------
  Serial.print("Soil Analog: "); Serial.print(soilAnalog);
  Serial.print(" | Soil Digital: "); Serial.print(soilDigital);
  Serial.print(" | Temp: "); Serial.print(temperature);
  Serial.print("°C | Humidity: "); Serial.println(humidity);

  // ------------------- Pump Control -------------------
  if (soilDigital == HIGH) {  // Dry → Pump ON
    digitalWrite(PUMP_PIN, LOW);
    Serial.println("Pump OFF");
  } else {                    // Wet → Pump OFF
    digitalWrite(PUMP_PIN, HIGH);
    Serial.println("Pump ON");
  }

  // ------------------- ThingSpeak Upload -------------------
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    String tsUrl = String(TS_SERVER) + "?api_key=" + TS_WRITE_KEY;
    tsUrl += "&field1=" + String(soilAnalog);
    tsUrl += "&field2=" + String(soilDigital);
    tsUrl += "&field3=" + String(temperature);
    tsUrl += "&field4=" + String(humidity);

    http.begin(tsUrl);
    int code = http.GET();
    if (code == 200) Serial.println("✅ Data sent to ThingSpeak");
    else Serial.println("❌ ThingSpeak error: " + String(code));
    http.end();
  }
}

// ------------------- Setup -------------------
void setup() {
  Serial.begin(115200);
  pinMode(PUMP_PIN, OUTPUT);
  pinMode(SOIL_MOISTURE_DIGITAL, INPUT);
  dht.begin();

  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi Connected!");
}

// ------------------- Loop -------------------
void loop() {
  sendSensorData();
  delay(2000);  // Send every 2 seconds
}
