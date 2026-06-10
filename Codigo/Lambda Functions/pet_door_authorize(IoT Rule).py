# -*- coding: utf-8 -*-
"""
IoT Core Rule → Lambda
Triggered every time a new last_event appears in any pet_door shadow.

Payload (from the SQL projection):
{
    "thing_name":   "pet_door_abc123",
    "event_id":     "evt-xxxx",
    "reader":       "entry" | "exit",
    "tag":          "01:F2:AD:1E",
    "detected_at":  "2026-05-12T01:15:30Z",
    "mode":         "auto" | "open" | "closed",
    "door_state":   "open" | "closed",
    "aws_timestamp": 1234567890123
}
"""

import json
import logging
import uuid
import boto3
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ── AWS clients ───────────────────────────────────────────────────────────────
dynamodb   = boto3.resource("dynamodb")
iot_client = boto3.client("iot-data")

pets_table     = dynamodb.Table("petdoor_pets")
events_table   = dynamodb.Table("petdoor_events")
commands_table = dynamodb.Table("petdoor_commands")


# ══════════════════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════════════════

def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_command_id() -> str:
    return f"cmd-{uuid.uuid4().hex[:8]}"


# ── DynamoDB ──────────────────────────────────────────────────────────────────

def get_pet(thing_name: str, rfid_tag: str) -> dict | None:
    """Fetch a single pet by (thing_name, rfid_tag). Returns None if not found."""
    try:
        resp = pets_table.get_item(
            Key={"thing_name": thing_name, "rfid_tag": rfid_tag}
        )
        return resp.get("Item")
    except Exception as e:
        logger.error("get_pet error: %s", e)
        return None


def update_pet_last_seen(thing_name: str, rfid_tag: str, detected_at: str):
    """Stamp last_seen_at on the pet row."""
    try:
        pets_table.update_item(
            Key={"thing_name": thing_name, "rfid_tag": rfid_tag},
            UpdateExpression="SET last_seen_at = :t",
            ExpressionAttributeValues={":t": detected_at},
        )
    except Exception as e:
        logger.error("update_pet_last_seen error: %s", e)


def save_event(thing_name: str, event_id: str, rfid_tag: str,
               reader: str, detected_at: str,
               event_type: str, door_opened: bool):
    """Write a row to petdoor_events."""
    try:
        events_table.put_item(Item={
            "thing_name":      thing_name,
            "event_timestamp": detected_at,   # SK
            "event_id":        event_id,
            "rfid_tag":        rfid_tag,
            "reader":          reader,
            "event_type":      event_type,
            "door_opened":     door_opened,
        })
    except Exception as e:
        logger.error("save_event error: %s", e)


def save_command(thing_name: str, action: str, status: str,
                 command_id: str = None, error: str = "") -> str:
    """Write a row to petdoor_commands. Returns the command_id used."""
    cmd_id = command_id or new_command_id()
    try:
        commands_table.put_item(Item={
            "thing_name":        thing_name,
            "command_timestamp": now_iso(),   # SK
            "command_id":        cmd_id,
            "action":            action,
            "status":            status,
            "error":             error,
        })
    except Exception as e:
        logger.error("save_command error: %s", e)
    return cmd_id


# ── IoT Shadow ────────────────────────────────────────────────────────────────

def send_open_command(thing_name: str) -> str:
    """
    Patches desired.door_command with action=open and returns the command_id.
    Raises on IoT error so the caller can record the failure.
    """
    cmd_id  = new_command_id()
    payload = json.dumps({
        "state": {
            "desired": {
                "door_command": {
                    "action":     "open",
                    "request_id": cmd_id,
                }
            }
        }
    })
    iot_client.update_thing_shadow(
        thingName=thing_name,
        payload=payload.encode()
    )
    return cmd_id


# ══════════════════════════════════════════════════════════════════════════════
#  Core logic
# ══════════════════════════════════════════════════════════════════════════════

def process_event(thing_name: str, event_id: str, rfid_tag: str,
                  reader: str, detected_at: str, mode: str, door_state: str):
    """
    1. Look up the pet in DynamoDB.
    2. Decide whether to open the door (mode=auto, pet enabled & registered).
    3. Save the event record.
    4. If opening: send shadow command + save command record.
    5. Update pet's last_seen_at.
    """

    logger.info(
        "Processing event %s | thing=%s tag=%s reader=%s mode=%s",
        event_id, thing_name, rfid_tag, reader, mode
    )
    # ── 0. Registration event — save and exit, no auth needed ─────────────────
    if reader.startswith("register"):
        actual_reader = reader.split(" ")[1] if " " in reader else reader
        save_event(
            thing_name  = thing_name,
            event_id    = event_id,
            rfid_tag    = rfid_tag,
            reader      = actual_reader,
            detected_at = detected_at,
            event_type  = "registration",
            door_opened = False,
        )
        logger.info("Registration event saved for tag %s — skipping auth.", rfid_tag)
        return


    # ── 1. Look up pet ────────────────────────────────────────────────────────
    pet = get_pet(thing_name, rfid_tag)

    registered = pet is not None
    enabled    = pet.get("enabled", False) if registered else False
    pet_name   = pet.get("name", "") if registered else ""

    logger.info(
        "Pet lookup → registered=%s enabled=%s name=%s",
        registered, enabled, pet_name
    )

    # ── 2. Decide action ──────────────────────────────────────────────────────
    #
    # Open the door when ALL of:
    #   • mode is "auto"  (open/closed modes are handled by the device itself)
    #   • pet is registered and enabled
    #   • reader is "entry" (we don't open on exit reader detections)
    #
    should_open = (
        mode == "auto"
        and registered
        and enabled
    )

    # Determine event type for the log
    if not registered:
        event_type = "unknown_tag"
    elif not enabled:
        event_type = "disabled_pet"
    elif should_open:
        event_type = f"access_granted_{reader}"   # access_granted_entry / access_granted_exit
    else:
        event_type = "access_denied"

    # ── 3. Save event record ──────────────────────────────────────────────────
    save_event(
        thing_name  = thing_name,
        event_id    = event_id,
        rfid_tag    = rfid_tag,
        reader      = reader,
        detected_at = detected_at,
        event_type  = event_type,
        door_opened = should_open,
    )

    # ── 4. Send open command if needed ────────────────────────────────────────
    if should_open:
        try:
            cmd_id = send_open_command(thing_name)
            save_command(
                thing_name = thing_name,
                action     = "open",
                status     = "sent",
                command_id = cmd_id,
            )
            logger.info("Open command sent: %s", cmd_id)
        except ClientError as e:
            save_command(
                thing_name = thing_name,
                action     = "open",
                status     = "failed",
                error      = str(e),
            )
            logger.error("Failed to send open command: %s", e)

    # ── 5. Stamp last_seen_at ─────────────────────────────────────────────────
    if registered:
        update_pet_last_seen(thing_name, rfid_tag, detected_at)


# ══════════════════════════════════════════════════════════════════════════════
#  Lambda entry point
# ══════════════════════════════════════════════════════════════════════════════

def lambda_handler(event: dict, context):
    logger.info("Raw event: %s", json.dumps(event))

    # ── Extract fields projected by the IoT rule SQL ──────────────────────────
    thing_name  = event.get("thing_name", "")
    event_id    = event.get("event_id", "")
    reader      = event.get("reader", "")
    rfid_tag    = event.get("tag", "")
    detected_at = event.get("detected_at", now_iso())
    mode        = event.get("mode", "auto")
    door_state  = event.get("door_state", "")

    # ── Basic validation ──────────────────────────────────────────────────────
    missing = [f for f, v in {
        "thing_name":  thing_name,
        "event_id":    event_id,
        "tag":         rfid_tag,
        "reader":      reader,
        "detected_at": detected_at,
    }.items() if not v]

    if missing:
        logger.error("Missing required fields: %s", missing)
        return {"statusCode": 400, "body": f"Missing fields: {missing}"}

    process_event(
        thing_name  = thing_name,
        event_id    = event_id,
        rfid_tag    = rfid_tag,
        reader      = reader,
        detected_at = detected_at,
        mode        = mode,
        door_state  = door_state,
    )

    return {"statusCode": 200, "body": "ok"}
