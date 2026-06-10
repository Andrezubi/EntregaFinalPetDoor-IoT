# -*- coding: utf-8 -*-
import logging
import json
import uuid
import time
import boto3
from botocore.exceptions import ClientError
from botocore.config import Config
from boto3.dynamodb.conditions import Key
from datetime import datetime, timezone

import ask_sdk_core.utils as ask_utils
from ask_sdk_core.skill_builder import SkillBuilder
from ask_sdk_core.dispatch_components import AbstractRequestHandler, AbstractExceptionHandler
from ask_sdk_core.handler_input import HandlerInput
from ask_sdk_model import Response

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ── AWS clients ───────────────────────────────────────────────────────────────
iot_client = boto3.client(
    "iot-data",
    config=Config(connect_timeout=2, read_timeout=4),
)
dynamodb = boto3.resource("dynamodb")

devices_table  = dynamodb.Table("petdoor_devices")
pets_table     = dynamodb.Table("petdoor_pets")
commands_table = dynamodb.Table("petdoor_commands")

SESSION_KEY_THING         = "thing_name"
SESSION_KEY_DISPLAY_NAME  = "display_name"


# ══════════════════════════════════════════════════════════════════════════════
#  Session helpers
# ══════════════════════════════════════════════════════════════════════════════

def get_thing_from_session(handler_input) -> str | None:
    """Return the thing_name stored in session attributes, or None."""
    attrs = handler_input.attributes_manager.session_attributes
    return attrs.get(SESSION_KEY_THING)


def set_thing_in_session(handler_input, thing_name: str, display_name: str = ""):
    """Persist thing_name and display_name in session attributes."""
    attrs = handler_input.attributes_manager.session_attributes
    attrs[SESSION_KEY_THING]        = thing_name
    attrs[SESSION_KEY_DISPLAY_NAME] = display_name


def get_display_name_from_session(handler_input) -> str:
    """Return the display_name stored in session attributes, or empty string."""
    attrs = handler_input.attributes_manager.session_attributes
    return attrs.get(SESSION_KEY_DISPLAY_NAME, "")


def initialize_default_thing(handler_input) -> str | None:
    """
    If no thing_name is in the session yet, look up the user's default device
    and store it. Returns the thing_name, or None if no device is found.
    """
    thing = get_thing_from_session(handler_input)
    if thing:
        return thing

    user_id = get_alexa_user_id(handler_input)
    device  = get_default_thing_name(user_id)
    if device:
        set_thing_in_session(
            handler_input,
            device["thing_name"],
            device.get("display_name", ""),
        )
        return device["thing_name"]
    return None


def require_thing(handler_input):
    """
    Returns (thing_name, error_response).
    If no device is connected, error_response is a ready Response object.
    """
    thing = initialize_default_thing(handler_input)
    if not thing:
        speak = (
            "No door is connected. "
            "Say 'connect to the door at' followed by the location name."
        )
        resp = (
            handler_input.response_builder
                .speak(speak)
                .ask(speak)
                .response
        )
        return None, resp
    return thing, None


# ══════════════════════════════════════════════════════════════════════════════
#  DynamoDB helpers
# ══════════════════════════════════════════════════════════════════════════════

def get_alexa_user_id(handler_input) -> str:
    return handler_input.request_envelope.session.user.user_id


def get_thing_name_by_location(user_id: str, location_name: str) -> dict | None:
    """
    Returns the full device item of the first enabled device whose
    location_name matches (case-insensitive) for the given user.
    """
    try:
        response = devices_table.query(
            KeyConditionExpression=Key("user_id").eq(user_id)
        )
        for device in response.get("Items", []):
            if (
                device.get("location", "").lower() == location_name.lower()
                and device.get("enabled", True)
            ):
                return device
        return None
    except Exception as e:
        logger.error("get_thing_name_by_location error: %s", e)
        return None


def get_default_thing_name(user_id: str) -> dict | None:
    """Return the full device item for the user's default enabled device, or None."""
    try:
        response = devices_table.query(
            KeyConditionExpression=Key("user_id").eq(user_id)
        )
        for device in response.get("Items", []):
            if (
                device.get("enabled", True)
                and device.get("is_default", False)
            ):
                return device
        return None
    except Exception as e:
        logger.error("get_default_thing_name error: %s", e)
        return None


# ── Command helpers ───────────────────────────────────────────────────────────

def new_command_id() -> str:
    return f"cmd-{uuid.uuid4().hex[:8]}"


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def record_command(thing_name: str, action: str, status: str = "sent",
                   command_id: str = None, error: str = "") -> str:
    """Write a row to petdoor_commands and return the command_id."""
    cmd_id = command_id or new_command_id()
    try:
        commands_table.put_item(Item={
            "thing_name":        thing_name,
            "command_timestamp": now_iso(),
            "command_id":        cmd_id,
            "action":            action,
            "status":            status,
            "error":             error,
        })
    except Exception as e:
        logger.error("record_command error: %s", e)
    return cmd_id


def update_command_status(thing_name: str, command_timestamp: str,
                          status: str, error: str = ""):
    """Update status on an existing command row (requires the SK)."""
    try:
        commands_table.update_item(
            Key={"thing_name": thing_name, "command_timestamp": command_timestamp},
            UpdateExpression="SET #s = :s, #e = :e",
            ExpressionAttributeNames={"#s": "status", "#e": "error"},
            ExpressionAttributeValues={":s": status, ":e": error},
        )
    except Exception as e:
        logger.error("update_command_status error: %s", e)


# ══════════════════════════════════════════════════════════════════════════════
#  Shadow helpers
# ══════════════════════════════════════════════════════════════════════════════

def get_shadow(thing_name: str) -> dict:
    try:
        resp = iot_client.get_thing_shadow(thingName=thing_name)
        return json.loads(resp["payload"].read())
    except ClientError as e:
        logger.error("get_shadow error: %s", e)
        return {}


def update_desired(patch: dict, thing_name: str) -> bool:
    payload = json.dumps({"state": {"desired": patch}})
    try:
        iot_client.update_thing_shadow(
            thingName=thing_name,
            payload=payload.encode()
        )
        return True
    except ClientError as e:
        logger.error("update_desired error: %s", e)
        return False


def get_reported(thing_name: str) -> dict:
    return get_shadow(thing_name).get("state", {}).get("reported", {})


def get_desired_state(thing_name: str) -> dict:
    return get_shadow(thing_name).get("state", {}).get("desired", {})


# ── Convenience accessors ─────────────────────────────────────────────────────

def reported_door(thing_name: str) -> dict:
    return get_reported(thing_name).get("door", {})


def reported_config(thing_name: str) -> dict:
    return get_reported(thing_name).get("config", {})


def reported_last_event(thing_name: str) -> dict:
    return get_reported(thing_name).get("last_event", {})


# ══════════════════════════════════════════════════════════════════════════════
#  Pets helpers
# ══════════════════════════════════════════════════════════════════════════════

def get_pets(thing_name: str) -> list[dict]:
    try:
        resp = pets_table.query(
            KeyConditionExpression=Key("thing_name").eq(thing_name)
        )
        return resp.get("Items", [])
    except Exception as e:
        logger.error("get_pets error: %s", e)
        return []


def find_pet_by_tag(thing_name: str, rfid_tag: str) -> dict | None:
    try:
        response = pets_table.get_item(
            Key={"thing_name": thing_name, "rfid_tag": rfid_tag}
        )
        return response.get("Item")
    except Exception as e:
        logger.error("find_pet_by_tag error: %s", e)
        return None


def find_pet_by_name(thing_name: str, name: str) -> dict | None:
    pets = get_pets(thing_name)
    name_lower = name.lower()
    for p in pets:
        if p.get("name", "").lower() == name_lower:
            return p
    return None


def register_pet_in_db(thing_name: str, rfid_tag: str, pet_name: str) -> bool:
    try:
        pets_table.put_item(Item={
            "thing_name":   thing_name,
            "rfid_tag":     rfid_tag,
            "name":         pet_name,
            "enabled":      True,
            "created_at":   now_iso(),
            "last_seen_at": "",
        })
        return True
    except Exception as e:
        logger.error("register_pet_in_db error: %s", e)
        return False


def delete_pet_from_db(thing_name: str, rfid_tag: str) -> bool:
    try:
        pets_table.delete_item(
            Key={"thing_name": thing_name, "rfid_tag": rfid_tag}
        )
        return True
    except Exception as e:
        logger.error("delete_pet_from_db error: %s", e)
        return False


# ══════════════════════════════════════════════════════════════════════════════
#  Skill handlers
# ══════════════════════════════════════════════════════════════════════════════

class LaunchRequestHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_request_type("LaunchRequest")(handler_input)

    def handle(self, handler_input):
        thing = initialize_default_thing(handler_input)
        if thing:
            display_name = get_display_name_from_session(handler_input) or "the smart pet door"
            door  = reported_door(thing).get("state", "unknown")
            mode  = reported_config(thing).get("mode", "unknown")
            speak = (
                f"Welcome to {display_name}. "
                f"The door is {door} and the mode is {mode}. "
                f"What would you like to do?"
            )
        else:
            speak = (
                "Welcome to the smart pet door. "
                "No door is connected. "
                "Say 'connect to the door at' followed by the location name."
            )
        return (
            handler_input.response_builder
                .speak(speak)
                .ask("What would you like to do?")
                .response
        )


# ── Device connection ─────────────────────────────────────────────────────────

class ConnectToDoorIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("ConnectToDoorIntent")(handler_input)

    def handle(self, handler_input):
        slots    = handler_input.request_envelope.request.intent.slots
        loc_slot = slots.get("location") if slots else None
        location = loc_slot.value.strip() if loc_slot and loc_slot.value else None

        if not location:
            speak = "I didn't catch the location. Try saying: connect to the front door."
            return handler_input.response_builder.speak(speak).ask(speak).response

        user_id = get_alexa_user_id(handler_input)
        device  = get_thing_name_by_location(user_id, location)

        if not device:
            speak = (
                f"I couldn't find any door at {location}. "
                "Please check the name and try again."
            )
            return handler_input.response_builder.speak(speak).ask("What would you like to do?").response

        thing        = device["thing_name"]
        display_name = device.get("display_name", location)
        set_thing_in_session(handler_input, thing, display_name)
        door  = reported_door(thing).get("state", "unknown")
        speak = (
            f"Connected to {display_name}. "
            f"The door is {door}. "
            "What would you like to do?"
        )
        return handler_input.response_builder.speak(speak).ask("What would you like to do?").response


# ── Mode setters ──────────────────────────────────────────────────────────────

class SetModeAutoIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("SetModeAutoIntent")(handler_input)

    def handle(self, handler_input):
        thing, err = require_thing(handler_input)
        if err:
            return err
        ok    = update_desired({"config": {"mode": "auto"}}, thing)
        speak = "The door has been set to automatic mode." if ok else "I couldn't change the mode. Please try again."
        return handler_input.response_builder.speak(speak).ask("What else would you like to do?").response


class SetModeClosedIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("SetModeClosedIntent")(handler_input)

    def handle(self, handler_input):
        thing, err = require_thing(handler_input)
        if err:
            return err
        ok    = update_desired({"config": {"mode": "closed"}}, thing)
        speak = "The door has been closed and locked." if ok else "I couldn't close the door. Please try again."
        return handler_input.response_builder.speak(speak).ask("What else would you like to do?").response


class SetModeOpenIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("SetModeOpenIntent")(handler_input)

    def handle(self, handler_input):
        thing, err = require_thing(handler_input)
        if err:
            return err
        ok    = update_desired({"config": {"mode": "open"}}, thing)
        speak = "The door has been opened." if ok else "I couldn't open the door. Please try again."
        return handler_input.response_builder.speak(speak).ask("What else would you like to do?").response


# ── Timers ────────────────────────────────────────────────────────────────────

class SetAutoTimerIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("SetAutoTimerIntent")(handler_input)

    def handle(self, handler_input):
        thing, err = require_thing(handler_input)
        if err:
            return err

        slots = handler_input.request_envelope.request.intent.slots
        raw   = slots.get("openTime").value if slots and slots.get("openTime") else None

        try:
            seconds = int(float(raw))
        except (TypeError, ValueError):
            speak = "I didn't catch the time. Try saying: set open timer to 30."
            return handler_input.response_builder.speak(speak).ask(speak).response

        if not (5 <= seconds <= 300):
            speak = "The time must be between 5 and 300 seconds."
            return handler_input.response_builder.speak(speak).ask("What else would you like to do?").response

        ok    = update_desired({"config": {"open_duration_sec": seconds}}, thing)
        speak = (
            f"Open timer set to {seconds} seconds."
            if ok else
            "I couldn't set the timer. Please try again."
        )
        return handler_input.response_builder.speak(speak).ask("What else would you like to do?").response


class SetRegisterDurationIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("SetRegisterDurationIntent")(handler_input)

    def handle(self, handler_input):
        thing, err = require_thing(handler_input)
        if err:
            return err

        slots = handler_input.request_envelope.request.intent.slots
        raw   = slots.get("registerTime").value if slots and slots.get("registerTime") else None

        try:
            seconds = int(float(raw))
        except (TypeError, ValueError):
            speak = "I didn't catch the time. Try saying: set registration time to twenty."
            return handler_input.response_builder.speak(speak).ask(speak).response

        if not (5 <= seconds <= 120):
            speak = "The registration time must be between 5 and 120 seconds."
            return handler_input.response_builder.speak(speak).ask("What else would you like to do?").response

        ok    = update_desired({"config": {"register_duration_sec": seconds}}, thing)
        speak = (
            f"Registration duration set to {seconds} seconds."
            if ok else
            "I couldn't set the registration duration. Please try again."
        )
        return handler_input.response_builder.speak(speak).ask("What else would you like to do?").response


# ── Tag / Pet management ──────────────────────────────────────────────────────

class AddNewTagIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("AddNewTagIntent")(handler_input)

    def handle(self, handler_input):
        thing, err = require_thing(handler_input)
        if err:
            return err

        slots        = handler_input.request_envelope.request.intent.slots
        pet_name_raw = slots.get("petName").value if slots and slots.get("petName") else None
        pet_name     = pet_name_raw.strip() if pet_name_raw else None

        if not pet_name:
            speak = "I didn't catch the pet's name. What is it called?"
            return handler_input.response_builder.speak(speak).ask(speak).response

        time_before = reported_last_event(thing).get("detected_at", "")

        cmd_id        = new_command_id()
        cmd_timestamp = now_iso()
        patch = {
            "door_command": {
                "action":     "register",
                "request_id": cmd_id,
            }
        }
        if not update_desired(patch, thing):
            record_command(thing, "register", "failed", cmd_id,
                           error="could not update shadow")
            speak = "I couldn't start registration mode. Please try again."
            return handler_input.response_builder.speak(speak).ask("What else would you like to do?").response

        record_command(thing, "register", "sent", cmd_id)

        attrs = handler_input.attributes_manager.session_attributes
        attrs["pending_registration"] = {
            "pet_name":      pet_name,
            "cmd_id":        cmd_id,
            "cmd_timestamp": cmd_timestamp,
            "time_before":   time_before,
        }

        register_sec = reported_config(thing).get("register_duration_sec", 20)
        speak = (
            f"Registration mode activated for {pet_name}. "
            f"You have {register_sec} seconds to bring the tag close to the reader. "
            "When you've done that, say 'confirm registration'."
        )
        return (
            handler_input.response_builder
                .speak(speak)
                .ask("Say 'confirm registration' once you have placed the tag on the reader.")
                .response
        )


class ConfirmTagRegistrationIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("ConfirmTagRegistrationIntent")(handler_input)

    def handle(self, handler_input):
        thing, err = require_thing(handler_input)
        if err:
            return err

        attrs   = handler_input.attributes_manager.session_attributes
        pending = attrs.get("pending_registration")

        if not pending:
            speak = (
                "There is no pending registration. "
                "Please say 'register pet' followed by the name first."
            )
            return handler_input.response_builder.speak(speak).ask("What else would you like to do?").response

        pet_name      = pending["pet_name"]
        cmd_id        = pending["cmd_id"]
        cmd_timestamp = pending["cmd_timestamp"]
        time_before   = pending["time_before"]

        event    = reported_last_event(thing)
        tag_now  = event.get("tag", "")
        time_now = event.get("detected_at", "")

        if not tag_now or time_now == time_before:
            update_command_status(thing, cmd_timestamp, "timeout",
                                  error="no new tag detected at confirmation")
            attrs.pop("pending_registration", None)
            speak = (
                "I didn't detect any new tag. "
                "Please try again by saying 'register pet' followed by the name."
            )
            return handler_input.response_builder.speak(speak).ask("What else would you like to do?").response

        new_tag = tag_now

        if find_pet_by_tag(thing, new_tag):
            update_command_status(thing, cmd_timestamp, "duplicate",
                                  error=f"tag {new_tag} already registered")
            attrs.pop("pending_registration", None)
            speak = "That tag already belongs to a registered pet."
            return handler_input.response_builder.speak(speak).ask("What else would you like to do?").response

        ok = register_pet_in_db(thing, new_tag, pet_name)
        attrs.pop("pending_registration", None)

        if ok:
            update_command_status(thing, cmd_timestamp, "completed")
            speak = f"{pet_name} has been registered successfully."
        else:
            update_command_status(thing, cmd_timestamp, "failed",
                                  error="DynamoDB write failed")
            speak = "I detected the tag but couldn't save it. Please try again."

        return handler_input.response_builder.speak(speak).ask("What else would you like to do?").response


class RegisterLastTagIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("RegisterLastTagIntent")(handler_input)

    def handle(self, handler_input):
        thing, err = require_thing(handler_input)
        if err:
            return err

        slots        = handler_input.request_envelope.request.intent.slots
        pet_name_raw = slots.get("petName").value if slots and slots.get("petName") else None
        pet_name     = pet_name_raw.strip() if pet_name_raw else None

        if not pet_name:
            speak = "I didn't catch the pet's name. What is it called?"
            return handler_input.response_builder.speak(speak).ask(speak).response

        last_tag = reported_last_event(thing).get("tag", "")

        if not last_tag:
            speak = "There is no recent tag to register."
            return handler_input.response_builder.speak(speak).ask("What else would you like to do?").response

        if find_pet_by_tag(thing, last_tag):
            record_command(thing, "register_last", "duplicate",
                           error=f"tag {last_tag} already registered")
            speak = "That tag already belongs to a registered pet."
            return handler_input.response_builder.speak(speak).ask("What else would you like to do?").response

        ok = register_pet_in_db(thing, last_tag, pet_name)

        if ok:
            record_command(thing, "register_last", "completed")
            speak = f"{pet_name} has been registered successfully."
        else:
            record_command(thing, "register_last", "failed",
                           error="DynamoDB write failed")
            speak = "I couldn't register the pet. Please try again."

        return handler_input.response_builder.speak(speak).ask("What else would you like to do?").response


class RemoveTagIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("RemoveTagIntent")(handler_input)

    def handle(self, handler_input):
        thing, err = require_thing(handler_input)
        if err:
            return err

        slots        = handler_input.request_envelope.request.intent.slots
        pet_name_raw = slots.get("petName").value if slots and slots.get("petName") else None
        pet_name     = pet_name_raw.strip() if pet_name_raw else None

        if not pet_name:
            speak = "I didn't catch the pet's name. Please say the name of the pet you want to remove."
            return handler_input.response_builder.speak(speak).ask(speak).response

        pet = find_pet_by_name(thing, pet_name)
        if not pet:
            speak = f"I couldn't find any pet named {pet_name}."
            return handler_input.response_builder.speak(speak).ask("What else would you like to do?").response

        ok    = delete_pet_from_db(thing, pet["rfid_tag"])
        speak = (
            f"{pet_name} has been removed successfully."
            if ok else
            f"I couldn't remove {pet_name}. Please try again."
        )
        return handler_input.response_builder.speak(speak).ask("What else would you like to do?").response


# ── Queries ───────────────────────────────────────────────────────────────────

class GetLastTagIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("GetLastTagIntent")(handler_input)

    def handle(self, handler_input):
        thing, err = require_thing(handler_input)
        if err:
            return err

        event    = reported_last_event(thing)
        last_tag = event.get("tag", "")

        if not last_tag:
            speak = "There are no recent tag detections."
            return handler_input.response_builder.speak(speak).ask("What else would you like to do?").response

        pet  = find_pet_by_tag(thing, last_tag)
        name = pet["name"] if pet else "an unregistered pet"

        reader_raw = event.get("reader", "")
        reader_map = {"entry": "entry", "exit": "exit"}
        reader     = reader_map.get(reader_raw.lower(), reader_raw) if reader_raw else None

        detected_at = event.get("detected_at", "")
        time_phrase = None
        if detected_at:
            try:
                dt      = datetime.fromisoformat(detected_at.replace("Z", "+00:00"))
                now     = datetime.now(timezone.utc)
                minutes = int((now - dt).total_seconds() // 60)
                if minutes < 1:
                    time_phrase = "less than a minute ago"
                elif minutes < 60:
                    time_phrase = f"{minutes} minutes ago"
                else:
                    time_phrase = f"{minutes // 60} hours ago"
            except ValueError:
                time_phrase = None

        speak = f"The last detection was {name}"
        if reader:
            speak += f" at the {reader} reader"
        if time_phrase:
            speak += f", {time_phrase}"
        speak += "."

        return handler_input.response_builder.speak(speak).ask("What else would you like to do?").response


class GetDoorStateIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("GetDoorStateIntent")(handler_input)

    def handle(self, handler_input):
        thing, err = require_thing(handler_input)
        if err:
            return err

        door         = reported_door(thing)
        state        = door.get("state", "unknown")
        mode         = reported_config(thing).get("mode", "unknown")
        display_name = get_display_name_from_session(handler_input)
        if display_name:
            speak = f"{display_name} is {state} and the mode is {mode}."
        else:
            speak = f"The door is {state} and the mode is {mode}."
        return handler_input.response_builder.speak(speak).ask("What else would you like to do?").response


class GetMotorStateIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("GetMotorStateIntent")(handler_input)

    def handle(self, handler_input):
        thing, err = require_thing(handler_input)
        if err:
            return err

        motor     = reported_door(thing).get("motor_state", "unknown")
        state_map = {
            "idle":    "idle",
            "running": "running",
            "error":   "in an error state",
            "stalled": "stalled",
        }
        speak = f"The motor is {state_map.get(motor, motor)}."
        return handler_input.response_builder.speak(speak).ask("What else would you like to do?").response


class GetLastOpenTimeIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("GetLastOpenTimeIntent")(handler_input)

    def handle(self, handler_input):
        thing, err = require_thing(handler_input)
        if err:
            return err

        ts = reported_door(thing).get("last_opened_at", "")

        if not ts:
            speak = "There is no record of when the door was last opened."
            return handler_input.response_builder.speak(speak).ask("What else would you like to do?").response

        try:
            dt      = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            now     = datetime.now(timezone.utc)
            minutes = int((now - dt).total_seconds() // 60)
            if minutes < 1:
                speak = "The door was opened less than a minute ago."
            elif minutes < 60:
                speak = f"The door was opened {minutes} minutes ago."
            else:
                speak = f"The door was opened {minutes // 60} hours ago."
        except ValueError:
            speak = f"The last opening was recorded as {ts}."

        return handler_input.response_builder.speak(speak).ask("What else would you like to do?").response


class GetListOfPetsIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("GetListOfPetsIntent")(handler_input)

    def handle(self, handler_input):
        thing, err = require_thing(handler_input)
        if err:
            return err

        pets         = get_pets(thing)
        enabled_pets = [p for p in pets if p.get("enabled", True)]

        if not enabled_pets:
            speak = "There are no registered pets."
        else:
            names = ", ".join(p.get("name", "unknown") for p in enabled_pets)
            speak = f"The registered pets are: {names}."

        return handler_input.response_builder.speak(speak).ask("What else would you like to do?").response


# ── Built-in handlers ─────────────────────────────────────────────────────────

class HelpIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("AMAZON.HelpIntent")(handler_input)

    def handle(self, handler_input):
        speak = (
            "You can say: connect to the front door, "
            "open the door, close the door, automatic mode, "
            "register pet named Luna, remove pet Luna, "
            "what was the last tag, is the door open, "
            "when was it last opened, list pets, "
            "set open timer to 30, set registration time to 20. "
            "What would you like to do?"
        )
        return (
            handler_input.response_builder
                .speak(speak)
                .ask("What would you like to do?")
                .response
        )


class CancelOrStopIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return (
            ask_utils.is_intent_name("AMAZON.CancelIntent")(handler_input) or
            ask_utils.is_intent_name("AMAZON.StopIntent")(handler_input)
        )

    def handle(self, handler_input):
        return handler_input.response_builder.speak("Goodbye!").response


class SessionEndedRequestHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_request_type("SessionEndedRequest")(handler_input)

    def handle(self, handler_input):
        return handler_input.response_builder.response


class IntentReflectorHandler(AbstractRequestHandler):
    """Fallback debugger — keep last in chain."""
    def can_handle(self, handler_input):
        return ask_utils.is_request_type("IntentRequest")(handler_input)

    def handle(self, handler_input):
        intent_name = ask_utils.get_intent_name(handler_input)
        speak = f"You triggered the {intent_name} intent."
        return handler_input.response_builder.speak(speak).response


class CatchAllExceptionHandler(AbstractExceptionHandler):
    def can_handle(self, handler_input, exception):
        return True

    def handle(self, handler_input, exception):
        logger.error(exception, exc_info=True)
        speak = "Sorry, something went wrong. Please try again."
        return (
            handler_input.response_builder
                .speak(speak)
                .ask(speak)
                .response
        )


# ══════════════════════════════════════════════════════════════════════════════
#  Skill builder
# ══════════════════════════════════════════════════════════════════════════════

sb = SkillBuilder()

sb.add_request_handler(LaunchRequestHandler())
sb.add_request_handler(ConnectToDoorIntentHandler())
sb.add_request_handler(SetModeAutoIntentHandler())
sb.add_request_handler(SetModeClosedIntentHandler())
sb.add_request_handler(SetModeOpenIntentHandler())
sb.add_request_handler(SetAutoTimerIntentHandler())
sb.add_request_handler(SetRegisterDurationIntentHandler())
sb.add_request_handler(AddNewTagIntentHandler())
sb.add_request_handler(ConfirmTagRegistrationIntentHandler())
sb.add_request_handler(RegisterLastTagIntentHandler())
sb.add_request_handler(RemoveTagIntentHandler())
sb.add_request_handler(GetLastTagIntentHandler())
sb.add_request_handler(GetDoorStateIntentHandler())
sb.add_request_handler(GetMotorStateIntentHandler())
sb.add_request_handler(GetLastOpenTimeIntentHandler())
sb.add_request_handler(GetListOfPetsIntentHandler())
sb.add_request_handler(HelpIntentHandler())
sb.add_request_handler(CancelOrStopIntentHandler())
sb.add_request_handler(SessionEndedRequestHandler())
sb.add_request_handler(IntentReflectorHandler())  # must be last

sb.add_exception_handler(CatchAllExceptionHandler())

lambda_handler = sb.lambda_handler()