#pragma once
#include <Arduino.h>

class TimedMotor {

public:

    enum DoorState {
        OPEN,
        CLOSED,
        OPENING,
        CLOSING,
        UNKNOWN
    };

private:

    int _in1;
    int _in2;
    int _ena;

    int _speed;

    unsigned long _startTime;
    unsigned long _duration;

    bool _running;

    DoorState _state;

public:

    TimedMotor(
        int in1,
        int in2,
        int ena,
        int speed = 180
    ) {

        _in1 = in1;
        _in2 = in2;
        _ena = ena;

        _speed = speed;

        _running = false;

        _state = CLOSED;
    }

    void begin() {

        pinMode(_in1, OUTPUT);
        pinMode(_in2, OUTPUT);

        ledcAttach(_ena, 5000, 8);

        stop();
    }

    void open(unsigned long ms) {

        _duration = ms;
        _startTime = millis();

        _running = true;
        _state = OPENING;

        digitalWrite(_in1, HIGH);
        digitalWrite(_in2, LOW);

        ledcWrite(_ena, _speed);
    }

    void close(unsigned long ms) {

        _duration = ms;
        _startTime = millis();

        _running = true;
        _state = CLOSING;

        digitalWrite(_in1, LOW);
        digitalWrite(_in2, HIGH);

        ledcWrite(_ena, _speed);
    }

    void stop() {

        ledcWrite(_ena, 0);

        digitalWrite(_in1, LOW);
        digitalWrite(_in2, LOW);

        _running = false;

        if (_state == OPENING)
            _state = OPEN;

        if (_state == CLOSING)
            _state = CLOSED;
    }

    bool update() {

        if (!_running)
            return false;

        if (millis() - _startTime >= _duration) {

            stop();

            return true;
        }

        return false;
    }

    bool isMoving() {
        return _running;
    }

    DoorState getState() {
        return _state;
    }
};