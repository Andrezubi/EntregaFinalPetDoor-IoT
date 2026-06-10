


#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <WiFiManager.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <SPI.h>
#include <time.h>
#include "TimedMotor.h"
#include "RFID.h"

// ─────────────────────────────────────────────────────────────────────────────
// Network & AWS config
// ─────────────────────────────────────────────────────────────────────────────        
const char* MQTT_BROKER = "a2z78sujrz3n3i-ats.iot.us-east-1.amazonaws.com"; 
const int   MQTT_PORT   = 8883;
const char* CLIENT_ID   = "pet_door_esp32";
const char* THING_NAME  = "pet_door_esp32";   

// Shadow MQTT topics
const char* TOPIC_UPDATE       = "$aws/things/pet_door_esp32/shadow/update";
const char* TOPIC_DELTA        = "$aws/things/pet_door_esp32/shadow/update/delta";
const char* TOPIC_GET          = "$aws/things/pet_door_esp32/shadow/get";
const char* TOPIC_GET_ACCEPTED = "$aws/things/pet_door_esp32/shadow/get/accepted";

// ─────────────────────────────────────────────────────────────────────────────
// Certificates 
// ─────────────────────────────────────────────────────────────────────────────
const char AMAZON_ROOT_CA1[] PROGMEM = R"EOF(
-----BEGIN CERTIFICATE-----
MIIDQTCCAimgAwIBAgITBmyfz5m/jAo54vB4ikPmljZbyjANBgkqhkiG9w0BAQsF
ADA5MQswCQYDVQQGEwJVUzEPMA0GA1UEChMGQW1hem9uMRkwFwYDVQQDExBBbWF6
b24gUm9vdCBDQSAxMB4XDTE1MDUyNjAwMDAwMFoXDTM4MDExNzAwMDAwMFowOTEL
MAkGA1UEBhMCVVMxDzANBgNVBAoTBkFtYXpvbjEZMBcGA1UEAxMQQW1hem9uIFJv
b3QgQ0EgMTCCASIwDQYJKoZIhvcNAQEBBQADggEPADCCAQoCggEBALJ4gHHKeNXj
ca9HgFB0fW7Y14h29Jlo91ghYPl0hAEvrAIthtOgQ3pOsqTQNroBvo3bSMgHFzZM
9O6II8c+6zf1tRn4SWiw3te5djgdYZ6k/oI2peVKVuRF4fn9tBb6dNqcmzU5L/qw
IFAGbHrQgLKm+a/sRxmPUDgH3KKHOVj4utWp+UhnMJbulHheb4mjUcAwhmahRWa6
VOujw5H5SNz/0egwLX0tdHA114gk957EWW67c4cX8jJGKLhD+rcdqsq08p8kDi1L
93FcXmn/6pUCyziKrlA4b9v7LWIbxcceVOF34GfID5yHI9Y/QCB/IIDEgEw+OyQm
jgSubJrIqg0CAwEAAaNCMEAwDwYDVR0TAQH/BAUwAwEB/zAOBgNVHQ8BAf8EBAMC
AYYwHQYDVR0OBBYEFIQYzIU07LwMlJQuCFmcx7IQTgoIMA0GCSqGSIb3DQEBCwUA
A4IBAQCY8jdaQZChGsV2USggNiMOruYou6r4lK5IpDB/G/wkjUu0yKGX9rbxenDI
U5PMCCjjmCXPI6T53iHTfIUJrU6adTrCC2qJeHZERxhlbI1Bjjt/msv0tadQ1wUs
N+gDS63pYaACbvXy8MWy7Vu33PqUXHeeE6V/Uq2V8viTO96LXFvKWlJbYK8U90vv
o/ufQJVtMVT8QtPHRh8jrdkPSHCa2XV4cdFyQzR1bldZwgJcJmApzyMZFo6IQ6XU
5MsI+yMRQ+hDKXJioaldXgjUkK642M4UwtBV8ob2xJNDd2ZhwLnoQdeXeGADbkpy
rqXRfboQnoZsG4q5WTP468SQvvG5
-----END CERTIFICATE-----
)EOF";

const char CERTIFICATE[] PROGMEM = R"KEY(
-----BEGIN CERTIFICATE-----
MIIDWTCCAkGgAwIBAgIUZTFpScN1ghjBAwRh5XaSHdmCBc8wDQYJKoZIhvcNAQEL
BQAwTTFLMEkGA1UECwxCQW1hem9uIFdlYiBTZXJ2aWNlcyBPPUFtYXpvbi5jb20g
SW5jLiBMPVNlYXR0bGUgU1Q9V2FzaGluZ3RvbiBDPVVTMB4XDTI2MDUxMDA4NTMx
N1oXDTQ5MTIzMTIzNTk1OVowHjEcMBoGA1UEAwwTQVdTIElvVCBDZXJ0aWZpY2F0
ZTCCASIwDQYJKoZIhvcNAQEBBQADggEPADCCAQoCggEBANBJ6oZa1l36ult0Yv2m
KQyww4Jk3xLIoH6cQWtsdOusucwUY4FvII1FF+I/VpLycQD5AEuRXN/w2o/o8srH
TZmn8DknKaiRwZJP0uwqX0d7RMTG/Xadd4VyaAiIpag35Sur5bhNpkxb7dOuTxs/
hbq2qqcZ/1AMT1uXSm31g6pvR8wPD7KVMstnZ3q528y/K+eGYd/FOILgTT4yQLkr
1DVKWVAS+hmabD/sUy7cJkkRc/AtmE29RRP2rdoDBcOAoPIqy4mHI/ehOVGqnlES
0AV3a/bu5ef1BTnwjqWOc6GSYR3MpXraQ+zFiDNRAUuUrw8LOwDi+fLg5HLKxoVz
uMMCAwEAAaNgMF4wHwYDVR0jBBgwFoAUFdd5Ers6L4kzROkdp/C7aQaY0WYwHQYD
VR0OBBYEFJeo8rBiuMipvVkrLsnrgF8dF7OwMAwGA1UdEwEB/wQCMAAwDgYDVR0P
AQH/BAQDAgeAMA0GCSqGSIb3DQEBCwUAA4IBAQC8Pc3gCDsy36Tm7UnL2mkOy8/U
0n0CTyrnBiai0w7/GFM2k35Fyr2CFHM3gfVNNbyG5xoco/87LZhdCBJt7RKx9B9M
O44w/818P9xqtVUqQ0C28m+r5o8xox+3B1GyEIuoHHiW9Ct0u4ZMhexe99rxgoI0
GAWogkMmLAZ4UTYUxi4iHZ7dn4C+d54D+fDRD7XroddEm4gyZC36UA1luYVdVPBH
FERoSQDAuQ14CO8gyh/3is6lfh0UCG+OGMfaBc9ikeAle9a4fC+b8l3wfedNFUA3
8ZsnAP3BHC2mC5VrdwHjM9rqFZVR22X3PjzWIZ4lPu1xGFG2y4ZFkOvdlgbi
-----END CERTIFICATE-----
)KEY";

const char PRIVATE_KEY[] PROGMEM = R"KEY(
-----BEGIN RSA PRIVATE KEY-----
MIIEpQIBAAKCAQEA0EnqhlrWXfq6W3Ri/aYpDLDDgmTfEsigfpxBa2x066y5zBRj
gW8gjUUX4j9WkvJxAPkAS5Fc3/Daj+jyysdNmafwOScpqJHBkk/S7CpfR3tExMb9
dp13hXJoCIilqDflK6vluE2mTFvt065PGz+Furaqpxn/UAxPW5dKbfWDqm9HzA8P
spUyy2dnernbzL8r54Zh38U4guBNPjJAuSvUNUpZUBL6GZpsP+xTLtwmSRFz8C2Y
Tb1FE/at2gMFw4Cg8irLiYcj96E5UaqeURLQBXdr9u7l5/UFOfCOpY5zoZJhHcyl
etpD7MWIM1EBS5SvDws7AOL58uDkcsrGhXO4wwIDAQABAoIBAAE+H6cTjanb4BbB
mAGZZy9LMq9peKc9CTAYMI+6guwRCL699GYGSrRtEBpqdFLGHYR699R7lolDf5pS
MnihPcZH6Tf+EtKNpBECZui/y/e6NYvTABogEGF8cEB0yEA7rSNYkDNMS0yzU7Tq
mlA4TczyYAxFLG/G0wZh3bDQQSvYIVqxo540sne44cIsfVTdILhtswrwlnLeXonD
uK3ec1umN8mxRBdPCq1g7meQpnh4MCh3RYyB0/s9I6osrdHU1FaJVXgEQV9OEZJL
6dfiXBFB832pIUQNUIjDBRlbsSsZKFZD5LEmpn6+jvb3vNhY8fdpIRVjmRNCvBiT
dZUHiMkCgYEA+wYt0O4whtPiG0ot1P9bKgGtjyK6GaTSzd2JU8OE/c8cSwUMucDb
grwhWRJxXOIQjwZFgvd1S20U5BPSt8Mg4iD4kQ34FbVdNkyaKSOvp8vLebOls17L
JkjVExD6BaX5U18Q6nCIxatLMHydUCRNPC/pqDnP/aRqbePP1Y7wCVcCgYEA1Grg
YuD+v1WSu3UhoRZre1BLF7izyXQa+wjBg9Dm2kMaIK8pv6SbkNnRqpBEyfqKobPv
7jKtyx9GBnVuggu785xgtf9XJh33fTcpPveRBR7QxqZmDcBvixYQcYMJ78HEor88
vaFWTttOAuioB4WynoFxIIPYaRWgIeUKjR+vrHUCgYEAif05jlKBRnyPHKVIUIAW
4x6NA9P5LUOXxibz6KHgJ42EZhDej/XeNR2pz0b+Hir/I0A1UesqBU5vX3kuKmoP
V378ZPCi4XwTQ1gUnmzJkJnMvpfsjI+daOw8hQCeECDOz+/AYr99z/t7l6nI6Fcs
RduovBsbpLiO8N18UE8E0H0CgYEAhOUg4Xv2pWo6VQGhOpE2SX4gnQS3pq/3OVtv
BrMp2x/kNtKgAgBQO72rCVUdVGhlV2mmEJawWMaGHwBVVRNWUcFiWDsaIQTalAJw
0a49ksCGyeHNM4lTv+bb/siG7PODvHZ83/8Sal+WXQeGKL6i07wUNM2IFaar+si7
YzORywkCgYEAhThPCxyO7KxqAQAHq2tQv2/sm+qsjIxL3qv1Zo9Mto1ipC6l4qAt
M7AVOAZ/uS9gG0C5NW2sszMQ3HBLTFAzNcc5ERc9gmA8PKoLoYiCRU/0KT6C8bbo
4h1fv3qzkq7lx2y/9b+ymhJ0cPJcH1UXI6cX/JIWstC9cpkk1xti38k=
-----END RSA PRIVATE KEY-----
)KEY";

// ─────────────────────────────────────────────────────────────────────────────
// Pin definitions
// ─────────────────────────────────────────────────────────────────────────────
#define RFID_ENTRY_SS_PIN   5
#define RFID_ENTRY_RST_PIN  4
#define RFID_EXIT_SS_PIN    14
#define RFID_EXIT_RST_PIN   13
#define DOOR_IN1_PIN 32
#define DOOR_IN2_PIN 33
#define DOOR_ENA_PIN 25
#define DOOR_SPEED 180
 
// ─────────────────────────────────────────────────────────────────────────────
// Hardware objects
// ─────────────────────────────────────────────────────────────────────────────
RFID rfidEntry(RFID_ENTRY_SS_PIN, RFID_ENTRY_RST_PIN, "entry");
RFID rfidExit (RFID_EXIT_SS_PIN,  RFID_EXIT_RST_PIN,  "exit");

TimedMotor doorMotor(DOOR_IN1_PIN,DOOR_IN2_PIN,DOOR_ENA_PIN,DOOR_SPEED);
  
WiFiClientSecure wifiClient;
PubSubClient     mqttClient(wifiClient);
 
// ─────────────────────────────────────────────────────────────────────────────
// Runtime state
// ─────────────────────────────────────────────────────────────────────────────
String        currentMode          = "auto";
unsigned int  openDurationSec      = 30;
unsigned int  registerDurationSec  = 20;
unsigned long openedAt             = 0;   //millis()when door opened
unsigned long registerStartedAt    = 0;   // millis() when register mode began
bool          autoCloseArmed       = false;
bool          needsReport          = false;
bool          registerMode         = false;
String        pendingCommandId     = "";


String lastOpenedAt = "";
String lastCommandAction = "open";
String lastCommandId     = "";
 
// ─────────────────────────────────────────────────────────────────────────────
// Door helpers
// ─────────────────────────────────────────────────────────────────────────────
 
bool doorIsOpen() {
  return doorMotor.getState() == TimedMotor::OPEN;
}

bool doorIsClosed() {
  return doorMotor.getState() == TimedMotor::CLOSED;
}

bool doorIsMoving() {
  return doorMotor.isMoving();
}
 
const char* getDoorStateStr() {

  switch (doorMotor.getState()) {

    case TimedMotor::OPEN:
      return "open";

    case TimedMotor::CLOSED:
      return "closed";

    case TimedMotor::OPENING:
      return "opening";

    case TimedMotor::CLOSING:
      return "closing";

    default:
      return "unknown";
  }
}
 
const char* getMotorStateStr() {
  return doorMotor.isMoving() ? "running" : "idle";
}
void commandOpen() {
  if (doorIsOpen()) {
    Serial.println("[DOOR] Already open, ignoring.");
    return;
  }
  Serial.println("[DOOR] → OPEN");
  doorMotor.open(800);
  openedAt = millis();
  lastOpenedAt = getISOTimestamp();  // ← add this
  if (currentMode == "auto") {
    autoCloseArmed = (openDurationSec > 0);
  } else {
    autoCloseArmed = false;
  }
  needsReport = true;
}

 
void commandClose() {
  if (doorIsClosed()) { Serial.println("[DOOR] Already closed."); return; }
  Serial.println("[DOOR] → CLOSE");
  doorMotor.close(800);
  autoCloseArmed = false;
  needsReport    = true;
}
 
// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────
 
String getISOTimestamp() {
  struct tm timeinfo;
  if (!getLocalTime(&timeinfo)) return "1970-01-01T00:00:00Z";
  char buf[25];
  strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ", &timeinfo);
  return String(buf);
}
 
// Generates a UUID4 using the ESP32 hardware RNG
String newEventId() {
  uint32_t r[4];
  for (int i = 0; i < 4; i++) r[i] = esp_random();
  // Set version 4 (0100) and variant bits (10xx)
  r[1] = (r[1] & 0xFFFF0FFF) | 0x00004000;  // version 4
  r[2] = (r[2] & 0x3FFFFFFF) | 0x80000000;  // variant 10
  char buf[37];
  snprintf(buf, sizeof(buf),
    "%08x-%04x-%04x-%04x-%04x%08x",
    r[0],
    (r[1] >> 16) & 0xFFFF,
    r[1] & 0xFFFF,
    (r[2] >> 16) & 0xFFFF,
    r[2] & 0xFFFF,
    r[3]
  );
  return String(buf);
}
 
// ─────────────────────────────────────────────────────────────────────────────
// Shadow publishing
// ─────────────────────────────────────────────────────────────────────────────
 
// Publishes reported state. If tag/reader are provided, updates last_event too.
void publishReport(const String& tag = "", const String& reader = "") {
  StaticJsonDocument<768> doc;

  JsonObject state = doc["state"].to<JsonObject>();


  JsonObject reported = state["reported"].to<JsonObject>();

  JsonObject reportedCmd = reported["door_command"].to<JsonObject>();

reportedCmd["action"]     = lastCommandAction;
reportedCmd["request_id"] = pendingCommandId;

  
  JsonObject config = reported["config"].to<JsonObject>();
  config["mode"] = currentMode;
  config["open_duration_sec"] = openDurationSec;
  config["register_duration_sec"] = registerDurationSec;

  JsonObject door = reported["door"].to<JsonObject>();
  door["state"]           = getDoorStateStr();
  door["motor_state"]     = getMotorStateStr();
  door["last_command_id"] = pendingCommandId;
  if (lastOpenedAt.length() > 0) {
    door["last_opened_at"] = lastOpenedAt;  // ← add this
  }


  

  // reported.last_event — only update when a real tag read happened
  if (tag.length() > 0 && reader.length() > 0) {
    JsonObject lastEvent = reported["last_event"].to<JsonObject>();
    lastEvent["reader"]      = reader;
    lastEvent["tag"]         = tag;
    lastEvent["detected_at"] = getISOTimestamp();
    lastEvent["event_id"]    = newEventId();
  }
 
  char buffer[512];
  serializeJson(doc, buffer);
  Serial.print("[MQTT] Report → ");
  Serial.println(buffer);
  mqttClient.publish(TOPIC_UPDATE, buffer);
  needsReport = false;
}
 
// ─────────────────────────────────────────────────────────────────────────────
// RFID event handler — called for both entry and exit readers
// ─────────────────────────────────────────────────────────────────────────────
 
void handleTagDetected(const String& uid, const String& reader) {
  Serial.print("[AUTH][");
  Serial.print(reader);
  Serial.print("] Tag: ");
  Serial.println(uid);
 
  // ── Register mode: just report the tag so the shadow picks it up ──────────
  if (registerMode) {
    // Prefix reader with "register " so the Lambda can identify this as a
    // registration event and skip the auth flow.
    Serial.println("[REGISTER] Tag detected in register mode — reporting.");
    publishReport(uid, "register " + reader);
    needsReport = false;
    return;
  }
 
  // Normal event — Lambda decides whether to open.
  publishReport(uid, reader);
  needsReport = false;
}
 
// ─────────────────────────────────────────────────────────────────────────────
// Delta / shadow sync handler
// ─────────────────────────────────────────────────────────────────────────────
 
void applyDelta(JsonObject delta) {
  bool changed = false;
 
  // ── config block ──────────────────────────────────────────────────────────
  if (delta.containsKey("config")) {
    JsonObject cfg = delta["config"].as<JsonObject>();
 
    if (cfg.containsKey("mode")) {
      String newMode = cfg["mode"].as<String>();
      if (newMode != currentMode) {
        Serial.print("[DELTA] mode: ");
        Serial.print(currentMode);
        Serial.print(" → ");
        Serial.println(newMode);
        currentMode = newMode;
        changed = true;
      }
 
      if (currentMode == "open") {
        // mode=open: force door open and disable auto-close
        autoCloseArmed = false;
        commandOpen();
      } else if (currentMode == "closed") {
        // mode=closed: force door closed regardless of current position
        // commandClose guard is bypassed here so we always attempt the move
        autoCloseArmed = false;
        commandClose();
        needsReport = true;
      } else if (currentMode == "auto" && doorIsOpen()) {
        // mode=auto: if door is already open, rearm the auto-close timer
        openedAt = millis();
        autoCloseArmed = (openDurationSec > 0);
        Serial.println("[AUTO] Auto-close rearmed.");
      }
    }
 
    if (cfg.containsKey("open_duration_sec")) {
      unsigned int newDur = cfg["open_duration_sec"].as<unsigned int>();
      if (newDur != openDurationSec) {
        openDurationSec = newDur;
        Serial.print("[DELTA] open_duration_sec → ");
        Serial.println(openDurationSec);
        changed = true;
      }
    }
 
    if (cfg.containsKey("register_duration_sec")) {
      unsigned int newRegDur = cfg["register_duration_sec"].as<unsigned int>();
      if (newRegDur != registerDurationSec) {
        registerDurationSec = newRegDur;
        Serial.print("[DELTA] register_duration_sec → ");
        Serial.println(registerDurationSec);
        changed = true;
      }
    }
  }
 
  // ── door_command block ────────────────────────────────────────────────────
  if (delta.containsKey("door_command")) {
    JsonObject cmd    = delta["door_command"].as<JsonObject>();
    String     action = cmd["action"].as<String>();
    String     reqId  = cmd["request_id"].as<String>();

    // A delta with no request_id is just an echo-back, ignore it
  if (reqId.length() == 0 || reqId == "null") return;

  // If action is missing from delta, reuse the last known action
  // (AWS IoT omits fields that haven't changed from desired vs reported)
  if (action.length() == 0 || action == "null") {
    action = lastCommandAction;
  }

  // Still nothing to do
  if (action.length() == 0) return;

    if (reqId != pendingCommandId) {
      pendingCommandId  = reqId;
      lastCommandAction = action;
      Serial.print("[CMD] action=");
      Serial.print(action);
      Serial.print(" id=");
      Serial.println(reqId);

      if (action == "open") {
        commandOpen();
      }
      else if (action == "register") {
        registerMode      = true;
        registerStartedAt = millis();

        Serial.print("[REGISTER] Mode ON for ");
        Serial.print(registerDurationSec);
        Serial.println("s - waiting for tag...");
      }

      changed = true;



    }
  }
 
  if (changed) needsReport = true;
}
 
// ─────────────────────────────────────────────────────────────────────────────
// MQTT callback
// ─────────────────────────────────────────────────────────────────────────────
 
void mqttCallback(char* topic, byte* payload, unsigned int length) {
  String topicStr(topic);
  Serial.print("[MQTT] Received: ");
  Serial.println(topicStr);
 
  StaticJsonDocument<1024> doc;
  DeserializationError err = deserializeJson(doc, payload, length);
  if (err) {
    Serial.print("[MQTT] JSON error: ");
    Serial.println(err.c_str());
    return;
  }
 
  if (topicStr == TOPIC_DELTA) {
    applyDelta(doc["state"].as<JsonObject>());
 
  } else if (topicStr == TOPIC_GET_ACCEPTED) {
    Serial.println("[MQTT] Full shadow received, syncing desired...");
    if (doc["state"].containsKey("desired")) {
      applyDelta(doc["state"]["desired"].as<JsonObject>());
    }
  }
}
 
// ─────────────────────────────────────────────────────────────────────────────
// WiFi & MQTT
// ─────────────────────────────────────────────────────────────────────────────
 
void setupWiFi() {

  WiFiManager wm;

  wm.setConfigPortalTimeout(180);   // portal active for 3 mins

  bool connected = wm.autoConnect("PetDoor-Setup");

  if (!connected) {
    Serial.println("[WIFI] Failed. Restarting...");
    ESP.restart();
  }

  Serial.println("[WIFI] Connected!");
  Serial.print("[WIFI] IP: ");
  Serial.println(WiFi.localIP());

  configTime(0, 0, "pool.ntp.org", "time.nist.gov");

  Serial.print("[NTP] Syncing");

  struct tm ti;
  int attempts = 0;

  while (!getLocalTime(&ti) && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  Serial.println(attempts < 20 ? " OK" : "\n[NTP Failed]");
}
 
void reconnect() {
  while (!mqttClient.connected()) {
    Serial.print("[MQTT] Connecting...");
    if (mqttClient.connect(CLIENT_ID)) {
      Serial.println(" connected.");
      mqttClient.subscribe(TOPIC_DELTA);
      mqttClient.subscribe(TOPIC_GET_ACCEPTED);
      mqttClient.publish(TOPIC_GET, "{}");
      Serial.println("[MQTT] Shadow requested.");
    } else {
      Serial.print(" failed rc=");
      Serial.print(mqttClient.state());
      Serial.println(", retry in 5s...");
      delay(5000);
    }
  }
}

void checkSerialCommands() {

  if (!Serial.available())
    return;

  String cmd = Serial.readStringUntil('\n');

  cmd.trim();
  cmd.toLowerCase();

  Serial.print("[SERIAL CMD] ");
  Serial.println(cmd);

  if (cmd == "resetwifi") {

    Serial.println("[WIFI] Clearing saved credentials...");

    WiFiManager wm;

    wm.resetSettings();

    wm.startConfigPortal("PetDoor-Setup");

    delay(1000);

    Serial.println("[WIFI] Credentials removed. Restarting...");

    ESP.restart();
  }
}

 
// ─────────────────────────────────────────────────────────────────────────────
// setup()
// ─────────────────────────────────────────────────────────────────────────────
 
void setup() {
  Serial.begin(115200);
  Serial.println("\n[SYS] Pet Door starting...");
 
  setupWiFi();
 
  wifiClient.setCACert(AMAZON_ROOT_CA1);
  wifiClient.setCertificate(CERTIFICATE);
  wifiClient.setPrivateKey(PRIVATE_KEY);
 
  mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
  mqttClient.setKeepAlive(60);
  mqttClient.setSocketTimeout(30);
  mqttClient.setCallback(mqttCallback);
  mqttClient.setBufferSize(1024);
 
  SPI.begin();
  rfidEntry.init();
  rfidExit.init();
  doorMotor.begin();
 
  Serial.println("[SYS] Setup complete.");
}
 
// ─────────────────────────────────────────────────────────────────────────────
// loop()
// ─────────────────────────────────────────────────────────────────────────────
 
void loop() {
  checkSerialCommands();
  if (WiFi.status() != WL_CONNECTED) {

    Serial.println("[WIFI] Lost connection");

    WiFi.reconnect();

    delay(5000);

    if (WiFi.status() != WL_CONNECTED) {
        setupWiFi();
    }
}
  if (!mqttClient.connected()) reconnect();
  mqttClient.loop();
 
  // ── motor update to stop movement  ──────────────────────────────────────────────────────
  bool motorFinished = doorMotor.update();

  if (motorFinished) {

      Serial.print("[DOOR] Settled → ");

      Serial.println(getDoorStateStr());

      needsReport = true;
  }
 
  // ── RFID polling — entry reader ───────────────────────────────────────────
  if (rfidEntry.update()) {
    if (rfidEntry.getState() == RFID::TAG_PRESENT) {
      handleTagDetected(rfidEntry.getCurrentUID(), "entry");
    } else if (rfidEntry.getState() == RFID::TAG_REMOVED) {
      Serial.println("[RFID][entry] Tag gone.");
    }
  }
 
  // ── RFID polling — exit reader ────────────────────────────────────────────
  if (rfidExit.update()) {
    if (rfidExit.getState() == RFID::TAG_PRESENT) {
      handleTagDetected(rfidExit.getCurrentUID(), "exit");
    } else if (rfidExit.getState() == RFID::TAG_REMOVED) {
      Serial.println("[RFID][exit] Tag gone.");
    }
  }
 
  // ── Register mode expiry ──────────────────────────────────────────────────
  if (registerMode) {
    if ((millis() - registerStartedAt) / 1000UL >= registerDurationSec) {
      registerMode = false;
      Serial.println("[REGISTER] Mode expired.");
      needsReport = true;
    }
  }
 
  // ── Auto-close timer ──────────────────────────────────────────────────────
  if (autoCloseArmed && doorIsOpen()) {
    if ((millis() - openedAt) / 1000UL >= openDurationSec) {
      Serial.print("[AUTO] Timer (");
      Serial.print(openDurationSec);
      Serial.println("s) expired — closing.");
      commandClose();
    }
  }
 
  // ── Pending report ────────────────────────────────────────────────────────
  if (needsReport && mqttClient.connected()) {
    publishReport();  // state-only report, no new event
  }
}



