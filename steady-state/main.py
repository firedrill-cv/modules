import json
from time import sleep
import urllib3
import jq
import boto3
import os

eventbridge_client = boto3.client("events")


def send_event(event_type: str):
    event = {
        "Source": "firedrill.internal",
        "DetailType": "steady_state",
        "Detail": json.dumps(
            {
                "event_type": event_type,
            }
        ),
        "EventBusName": os.environ.get("EVENT_BUS_NAME"),
    }
    print(event)
    try:
        event_result = eventbridge_client.put_events(Entries=[event])
        print("[INFO] Send Eventbridge message successfully.")
        print(event_result)
    except Exception as ex:
        print("[ERROR] Failed to send Eventbridge notification")
        print(ex)

    return


def start_http_check(steady_state):
    request_config = steady_state["request"]
    response_config = steady_state["response"]
    print(request_config)
    print(response_config)

    # Set defaults where needed
    allowed_failures = 3
    expected_pattern = None
    expected_status = 200

    if "failures" in response_config:
        allowed_failures = response_config["failures"]
    if "jq" in response_config:
        expected_pattern = response_config["jq"]
    if "expected_status" in response_config:
        expected_status = response_config["expected_status"]

    print("HTTP CHECK CONFIG:")
    print(
        json.dumps(
            {
                "allowed_failures": allowed_failures,
                "expected_pattern": expected_pattern,
                "expected_status": expected_status,
            }
        )
    )

    http = urllib3.PoolManager()

    failed_requests = 0
    iterations = 0

    send_event("running")

    while failed_requests < allowed_failures:
        r = http.request(
            request_config["method"],
            request_config["url"],
            headers=request_config["headers"],
            body=json.dumps(request_config["body"]),
        )

        response = r.data.decode("utf-8")

        print(
            json.dumps(
                {
                    "status": r.status,
                    "body": response,
                }
            )
        )

        matched_status = False
        matched_payload = False

        # HTTP Status
        if r.status == expected_status:
            matched_status = True

        # Compare payload to jq pattern
        if expected_pattern is not None:
            try:
                if (
                    response is not None
                    and jq.first(expected_pattern, json.loads(response)) is not None
                ):
                    print("[SUCCESS] Payload matched pattern.")
                    matched_payload = True
                else:
                    print("[FAIL] Payload didn't match JQ.")
                    matched_payload = False
            except json.JSONDecodeError as jEr:
                print("[FAIL] Failed to decode and verify payload.")
                print(jEr)
                matched_payload = False

        # Check if any conditions failed to mark this as failed
        if matched_status == False or matched_payload == False:
            failed_requests = failed_requests + 1

        iterations = iterations + 1

        print(
            json.dumps(
                {
                    "matched_status": matched_status,
                    "matched_payload": matched_payload,
                    "failed_requests": failed_requests,
                    "allowed_failures": allowed_failures,
                    "iterations": iterations,
                }
            )
        )
        sleep(1)

    if failed_requests >= allowed_failures:
        print("[FAIL] Status check failed - too many failed requests")
        send_event("failed")
    else:
        print("[SUCCESS] Status check passed successfully.")
        send_event("success")

    return


def main(event, context):
    method = event["method"]

    if method == "http":
        start_http_check(event)
