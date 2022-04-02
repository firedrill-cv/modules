import boto3
from logzero import logger
import os
import json
import urllib3
from urllib3 import Retry


def main(event, context):
    print(event)

    for record in event["Records"]:
        record_body = json.loads(record["body"])
        notification_target = record_body["target"]
        notification_payload = record_body["payload"]

        logger.debug(
            {
                "message": "Processing notification",
                "notification_target": notification_target,
                "notification_payload": notification_payload,
            }
        )

        if notification_target["type"] == "http":
            headers = (
                notification_target["headers"]
                if hasattr(notification_target, "headers")
                else {"Content-Type": "application/json"}
            )
            method = (
                json.dumps(notification_target["method"])
                if hasattr(notification_target, "method")
                else "POST"
            )

            http = None
            if notification_target["url"].startswith("https://"):
                http = urllib3.PoolManager(
                    # This is probably going to be some weirdly protected endpoint so don't bother verifying SSL
                    cert_reqs="CERT_NONE",
                    assert_hostname=False,
                )
            else:
                http = urllib3.PoolManager()

            logger.debug(
                {
                    "message": "Sending HTTP request",
                    "url": notification_target["url"],
                    "headers": headers,
                    "method": method,
                    "body": json.dumps(notification_payload),
                }
            )

            try:
                r = http.request(
                    method,
                    notification_target["url"],
                    headers=headers,
                    body=json.dumps(notification_payload),
                    timeout=5.0,
                    retries=Retry(3),
                )
                logger.debug({"message": "Webhook sent.", "status": r.status})
            except Exception as ex:
                logger.error(ex)
    return
