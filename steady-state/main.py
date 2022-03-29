import json
from time import sleep
import urllib3
import boto3
import os
import threading
import sys
import sched
import time
import jmespath
import signal
from logzero import logger

eventbridge_client = boto3.client("events")


scheduler = sched.scheduler(time.time, time.sleep)
schedule_interval = 3
monitor = None
t = None
sqs = boto3.client("sqs")
account_id = boto3.client("sts").get_caller_identity().get("Account")
queue_url = os.environ.get("MESSAGE_QUEUE_URL")


def setInterval(interval):
    def decorator(function):
        def wrapper(*args, **kwargs):
            stopped = threading.Event()

            def loop():  # executed in another thread
                while not stopped.wait(interval):  # until stopped
                    function(*args, **kwargs)

            t = threading.Thread(target=loop)
            t.daemon = True  # stop if the program exits
            t.start()
            return stopped

        return wrapper

    return decorator


class GracefulKiller:
    kill_now = False
    signals = {signal.SIGINT: "SIGINT", signal.SIGTERM: "SIGTERM"}

    def __init__(self):
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self, signum, frame):
        self.kill_now = True


def send_event(steady_state_id: str, status: str, reason: str):
    event = {
        "Source": "firedrill.internal",
        "DetailType": "steady_state",
        "Detail": json.dumps(
            {
                "status": status,
                "steady_state_id": steady_state_id,
                "reason": reason,
            }
        ),
        "EventBusName": os.environ.get("EVENT_BUS_NAME"),
    }
    logger.info({"message": "Sending event to Eventbridge", "event": event})
    try:
        event_result = eventbridge_client.put_events(Entries=[event])
        logger.info("[INFO] Send Eventbridge message successfully.")
        logger.info(event_result)
    except Exception as ex:
        logger.info("[ERROR] Failed to send Eventbridge notification")
        logger.info(ex)

    return


# @setInterval(schedule_interval)
def check_sqs(steady_state_id):
    logger.info(
        {
            "message": "Checking SQS for messages",
            "queue_url": queue_url,
            "steady_state_id": steady_state_id,
        }
    )
    response = sqs.receive_message(
        QueueUrl=queue_url,
        AttributeNames=["All"],
        MaxNumberOfMessages=10,
        WaitTimeSeconds=1,
    )

    if "Messages" not in response or len(response["Messages"]) == 0:
        return

    messages = response["Messages"]

    for message in messages:
        if "Body" not in message:
            logger.error(
                {
                    "message": "Body not in payload - ignoring.",
                    "payload": message,
                }
            )
            return

        message_body = json.loads(message["Body"])

        if message_body["id"] != steady_state_id:
            logger.info(
                {
                    "message": "Message not intended for this steady state.",
                    "steady_state_id": steady_state_id,
                    "intended_steady_state_id": message_body["id"],
                }
            )
            return

        type = message_body["type"]

        sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=message["ReceiptHandle"])

        logger.info(
            {
                "message": "Message received.",
                "type": type,
                "steady_state_id": steady_state_id,
            }
        )
        if type == "killswitch":
            logger.debug(
                {
                    "message": "KILLSWITCH! KILLING THE INSTANCE",
                    "type": type,
                }
            )
            send_event(steady_state_id, "success", "killswitch")
            stop_watching_queue()
            sys.exit(0)

        else:
            logger.error(
                {
                    "message": "Unknown type in message.",
                    "type": type,
                }
            )


def stop_watching_queue():
    if t is not None:
        t.stop()
        print("[STOP WATCHING QUEUE] Stopped thread.")
    if monitor is None:
        print("[STOP WATCHING QUEUE] Watcher was already closed.")
    else:
        print("[STOP WATCHING QUEUE] Stopping watcher...")
        try:
            monitor()
            print("[STOP WATCHING QUEUE] Watcher stopped successfully.")
        except Exception as ex:
            print("[STOP WATCHING QUEUE] Failed to stop watcher!")
            print(str(ex))


def start_http_check(steady_state):

    steady_state_id = steady_state["id"]

    logger.info(
        {
            "event": json.dumps(steady_state),
            "steady_state_id": steady_state_id,
        }
    )

    request_config = (
        json.loads(steady_state["request"])
        if isinstance(steady_state["request"], str)
        else steady_state["request"]
    )
    response_config = (
        json.loads(steady_state["response"])
        if isinstance(steady_state["response"], str)
        else steady_state["response"]
    )
    logger.info(request_config)
    logger.info(response_config)

    # Set defaults where needed
    allowed_failures = 3
    expected_pattern = None
    expected_status = 200

    if "failures" in response_config:
        allowed_failures = response_config["failures"]
    if "pattern" in response_config:
        expected_pattern = response_config["pattern"]
    if "expected_status" in response_config:
        expected_status = response_config["expected_status"]

    http = None

    target_url = request_config["url"]

    if target_url.startswith("https://"):
        http = urllib3.PoolManager(
            # This is probably going to be some weirdly protected endpoint so don't bother verifying SSL
            cert_reqs="CERT_NONE",
            assert_hostname=False,
        )
    else:
        http = urllib3.PoolManager()

    failed_requests = 0
    iterations = 0

    logger.info(
        {
            "message": "Starting steady state.",
            "allowed_failures": allowed_failures,
            "expected_pattern": expected_pattern,
            "expected_status": expected_status,
        }
    )

    send_event(steady_state_id, "running", None)

    while failed_requests < allowed_failures:

        sleep(schedule_interval)

        check_sqs(steady_state_id)

        headers = (
            request_config["headers"] if hasattr(request_config, "headers") else {}
        )
        timeout = (
            float(request_config["timeout"])
            if hasattr(request_config, "timeout")
            else 3.0
        )
        body = (
            json.dumps(request_config["body"])
            if hasattr(request_config, "body")
            else ""
        )

        # Start
        logger.debug(
            {
                "message": "Sending request.",
                "url": target_url,
                "method": request_config["method"],
                "headers": headers,
                "body": body,
            }
        )
        try:
            r = http.request(
                request_config["method"],
                target_url,
                headers=headers,
                body=body,
                timeout=timeout,
                retries=False,
            )

            response = r.data.decode("utf-8")
            logger.debug({"message": "Recieved response.", "response": response})

            # Check the status code
            if r.status == expected_status:
                matched_status = True

            # Compare payload to pattern
            if expected_pattern is not None:
                try:
                    if (
                        response is not None
                        and jmespath.search(expected_pattern, json.loads(response))
                        is not None
                    ):
                        logger.debug(
                            {
                                "message": "Payload matched pattern.",
                                "expected_pattern": expected_pattern,
                                "payload": response,
                            }
                        )
                        matched_payload = True
                    else:
                        logger.debug(
                            {
                                "message": "Payload did NOT match pattern.",
                                "expected_pattern": expected_pattern,
                                "payload": response,
                            }
                        )
                        matched_payload = False
                except json.JSONDecodeError as jEr:
                    logger.info("[FAIL] Failed to decode and verify payload.")
                    logger.info(jEr)
                    matched_payload = False
            else:
                logger.info({"message": "No pattern provided, defaulting to True."})
                matched_payload = True

            # Check if any conditions failed to mark this as failed
            if matched_status == False or matched_payload == False:
                failed_requests = failed_requests + 1

        except urllib3.exceptions.ConnectTimeoutError as ex:
            logger.error({"message": "Request timed out."})
            failed_requests = failed_requests + 1

        except Exception as ex:
            logger.error({"message": "Unknown error thrown during request."})
            logger.error(ex)
            failed_requests = failed_requests + 1

        matched_status = False
        matched_payload = False

        iterations = iterations + 1

        logger.info(
            {
                "matched_status": matched_status,
                "matched_payload": matched_payload,
                "failed_requests": failed_requests,
                "allowed_failures": allowed_failures,
                "iterations": iterations,
            }
        )

    if failed_requests >= allowed_failures:
        logger.error(
            {
                "message": "Status check failed - too many failed requests",
                "reason": "too many failed requests",
                "matched_status": matched_status,
                "matched_payload": matched_payload,
                "failed_requests": failed_requests,
                "allowed_failures": allowed_failures,
                "iterations": iterations,
            }
        )
        send_event(steady_state_id, "failed", "Too many failed requests")
    else:
        logger.info(
            {
                "message": "Status check succeeded",
                "matched_status": matched_status,
                "matched_payload": matched_payload,
                "failed_requests": failed_requests,
                "allowed_failures": allowed_failures,
                "iterations": iterations,
            }
        )
        send_event(steady_state_id, "success", None)


def main(event, context):
    print(event)
    type = event["type"]
    steady_state_id = event["id"]

    if type == "http":
        start_http_check(event)

    logger.info(
        {
            "message": "Hit the end of the program, exiting.",
            "steady_state_id": steady_state_id,
        }
    )
    return
