#include <Arduino.h>
#pragma once
class LED {
// has three types of states in order to track what the led should be doing we put it in an enum in order to avoid applying an incorrect state
public:
  enum State : byte {
    OFF,
    ON,
    BLINK
  };

private:
  byte pin;//the number of the pin in the board the led is connected to
  State state = OFF;// what state the led should be in
  bool isOn = false;// wether the led is powered on or not
  unsigned long blinkMillis = 0;// amount of milliseconds should pass before the led toggles
  unsigned long previousMillis = 0;//a variable to keep track of the time passed asyncrhonously

public:
//consturctor

  LED(byte pin) {
    this->pin = pin;
    pinMode(pin, OUTPUT);
    turnOff();
  }

  //sets the state  of the led and turns it on immedately if its set to blink and checks if the blinks per second are distinct to 0
  void setState(State newState) {

    state = newState;

    switch (state) {

      case OFF:
        turnOff();
        break;

      case ON:
        turnOn();
        break;

      case BLINK:

        if (blinkMillis == 0) {
          state = OFF;
          turnOff();
          return;
        }

        turnOn();
        previousMillis = millis();
        break;
    }
  }


  //calculates the amount of milliseconds should happen every time the led toggles  to achieve the blinks per second assigned
  void setBlinksPerSecond(byte blinksPerSecond) {

    if (blinksPerSecond == 0) {
      blinkMillis = 0;
      return;
    }

    blinkMillis = 1000UL / (blinksPerSecond*2);
  }

  //if the led is set to blink checks wether to toggle the led or not depending on the previous millis and current millis 
  void update() {

    if (state != BLINK) return;

    unsigned long currentMillis = millis();

    if (currentMillis - previousMillis >= blinkMillis) {

      previousMillis += blinkMillis;
      toggle();
    }
  }

  // changes the LED state from on to off and viceversa and writes it in console for debugging
  
  void toggle() {

    isOn = !isOn;

    Serial.print(pin);
    Serial.print(" -> ");

    if (isOn)
      Serial.println("HIGH");
    else
      Serial.println("LOW");

    digitalWrite(pin, isOn ? HIGH : LOW);
  }

  // turns the led on and writes it in serial for debugging
  void turnOn() {

    isOn = true;

    Serial.print(pin);
    Serial.println(" -> HIGH");

    digitalWrite(pin, HIGH);
  }

  // turns the led off and writes it in serial for debugging
  void turnOff() {

    isOn = false;

    Serial.print(pin);
    Serial.println(" -> LOW");

    digitalWrite(pin, LOW);
  }

  LED::State getState() {
  return state;
  }

};