#pragma once
#include <Arduino.h>
#include <ESP32Servo.h>

// ─────────────────────────────────────────────────────────────────────────────
// SmoothServo — generic non-blocking servo controller
//
// Knows nothing about doors, pets, or application logic.
// Just moves to a target angle smoothly and reports its position.
//
// Wiring (MG995 → ESP32):
//   Signal (orange) → any PWM-capable GPIO (e.g. GPIO 13)
//   VCC    (red)    → External 5V (NOT from ESP32)
//   GND    (brown)  → Common GND with ESP32
// ─────────────────────────────────────────────────────────────────────────────

class SmoothServo {
public:
  enum State : byte {
    IDLE,   // at target angle, not moving
    MOVING  // currently sweeping toward target
  };

private:
  Servo  servo;
  byte   pin;

  int    currentAngle  = 0;
  int    targetAngle   = 0;
  int    stepDeg       = 1;      // degrees moved per step
  unsigned long stepIntervalMs = 15; // ms between steps
  unsigned long lastStepMillis = 0;
  int minPulseUs;
  int maxPulseUs;

  State  state = IDLE;

  // Called internally each step to write angle and log
  void writeAngle(int angle) {
    currentAngle = angle;
    int us = map(angle, 0, 180, minPulseUs, maxPulseUs);
    servo.writeMicroseconds(us);
    Serial.print("[SERVO] pin=");
    Serial.print(pin);
    Serial.print(" angle=");
    Serial.print(currentAngle);
    Serial.println("°");
  }

public:
  // ── Constructor ────────────────────────────────────────────────────────────
  // pin:          PWM GPIO
  // initialAngle: angle to go to on init
  // stepDeg:      degrees per step (smaller = smoother, slower)
  // stepIntervalMs: milliseconds between steps
  SmoothServo(byte pin, int initialAngle = 0, int stepDeg = 1,unsigned long stepIntervalMs = 15,int minPulseUs = 500, int maxPulseUs = 2500)
  : pin(pin), stepDeg(stepDeg), stepIntervalMs(stepIntervalMs),
    minPulseUs(minPulseUs), maxPulseUs(maxPulseUs)
  {
    targetAngle  = initialAngle;
    currentAngle = initialAngle;
  }

  // ── init() — call once in setup() ─────────────────────────────────────────
  void init() {
    servo.attach(pin);
    servo.write(currentAngle);
    Serial.print("[SERVO] Initialized on pin ");
    Serial.print(pin);
    Serial.print(" at angle ");
    Serial.print(currentAngle);
    Serial.println("°");
  }

  // ── moveTo() — set a new target angle ────────────────────────────────────
  // Clamps to [0, 180]. Movement happens in update().
  void moveTo(int angle) {
    angle = constrain(angle, 0, 180);

    if (angle == currentAngle) {
      Serial.print("[SERVO] moveTo(");
      Serial.print(angle);
      Serial.println("°) — already there, ignoring.");
      return;
    }

    targetAngle = angle;
    state       = MOVING;

    Serial.print("[SERVO] moveTo(");
    Serial.print(targetAngle);
    Serial.print("°) from ");
    Serial.print(currentAngle);
    Serial.println("°");
  }

  // ── snapTo() — jump instantly to angle, no smooth movement ───────────────
  void snapTo(int angle) {
    angle        = constrain(angle, 0, 180);
    targetAngle  = angle;
    state        = IDLE;
    writeAngle(angle);
  }

  // ── update() — call every loop() ─────────────────────────────────────────
  // Returns true when the servo has just reached its target.
  bool update() {
    if (state != MOVING) return false;

    unsigned long now = millis();
    if (now - lastStepMillis < stepIntervalMs) return false;
    lastStepMillis = now;

    // Step one degree toward target
    if (currentAngle < targetAngle)
      writeAngle(min(currentAngle + stepDeg, targetAngle));
    else
      writeAngle(max(currentAngle - stepDeg, targetAngle));

    // Check arrival
    if (currentAngle == targetAngle) {
      state = IDLE;
      Serial.print("[SERVO] Reached target ");
      Serial.print(currentAngle);
      Serial.println("°");
      return true; // signal: just arrived
    }

    return false;
  }

  // ── Getters ────────────────────────────────────────────────────────────────
  int    getCurrentAngle() const { return currentAngle; }
  int    getTargetAngle()  const { return targetAngle; }
  State  getState()        const { return state; }
  bool   isMoving()        const { return state == MOVING; }
  bool   isIdle()          const { return state == IDLE; }
};