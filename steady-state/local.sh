AWS_ACCESS_KEY_ID=$(aws --profile default configure get aws_access_key_id)
AWS_SECRET_ACCESS_KEY=$(aws --profile default configure get aws_secret_access_key)

docker build . -t http-steady-state

docker run -it --rm -p 9000:8080  \
    -e AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID \
    -e AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY \
    -e AWS_DEFAULT_REGION=us-east-1 \
    -e MESSAGE_QUEUE_URL="https://sqs.us-east-1.amazonaws.com/332697329009/firedrill-runner-messages-dev.fifo" \
    -e EVENT_BUS_NAME="firedrill-control-panel-inbound-dev" \
    http-steady-state