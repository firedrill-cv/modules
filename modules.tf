provider "aws" {
  region = "us-east-1"
}

variable "environment" {
  type    = string
  default = "dev"
}

resource "aws_iam_role" "steady_state_function_role" {
  name = format("firedrill-steady-state-%s", var.environment)

  assume_role_policy = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Action": "sts:AssumeRole",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Effect": "Allow",
      "Sid": ""
    }
  ]
}
EOF
}

resource "aws_lambda_function" "steady_state_function" {
  filename      = "build.zip"
  function_name = format("firedrill-steady-state-%s", var.environment)
  role          = aws_iam_role.steady_state_function_role.arn
  handler       = "main.main"

  # The filebase64sha256() function is available in Terraform 0.11.12 and later
  # For Terraform 0.11.11 and earlier, use the base64sha256() function and the file() function:
  # source_code_hash = "${base64sha256(file("lambda_function_payload.zip"))}"
  source_code_hash = filebase64sha256("steady-state/build.zip")

  runtime = "python3.9"

  environment {
    variables = {
      environment = "dev"
    }
  }
}