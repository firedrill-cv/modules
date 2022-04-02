`source ./modules-venv/bin/activate`


Run locally:
`./local.sh`

Deploy to S3 and update the lambda
`make update`

Example SQS messages:

```
{
    "id": "1234-1234-1234-1234",
    "type": "killswitch"
}
```