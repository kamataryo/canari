terraform {
  required_version = ">= 1.5"
  required_providers {
    aws     = { source = "hashicorp/aws", version = "~> 6.0" }
    archive = { source = "hashicorp/archive", version = "~> 2.0" }
  }
}

# リージョンは aws CLI の設定に従う。canari CLI と同じところに作るため
provider "aws" {}

variable "reserved_concurrency" {
  description = "公開 URL を連打されたときの課金の上限。同時実行の上限が 10 のままのアカウントでは設定できないので -1 に"
  type        = number
  default     = 5
}

# 名前は固定。同じ名前があれば apply が止まるので、tfstate をなくしてもスタックが 2 つにならない
resource "aws_dynamodb_table" "tokens" {
  name                        = "canari-tokens"
  billing_mode                = "PAY_PER_REQUEST"
  hash_key                    = "id"
  deletion_protection_enabled = true # どこに何を置いたかの台帳なので

  attribute {
    name = "id"
    type = "S"
  }
}

# 通知先のメールは canari notify add/remove で出し入れする
resource "aws_sns_topic" "alerts" {
  name = "canari-alerts"
}

resource "aws_iam_role" "beacon" {
  name = "canari-beacon"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy_attachment" "logs" {
  role       = aws_iam_role.beacon.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "beacon" {
  role = aws_iam_role.beacon.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = "dynamodb:UpdateItem", Resource = aws_dynamodb_table.tokens.arn },
      { Effect = "Allow", Action = "sns:Publish", Resource = aws_sns_topic.alerts.arn },
    ]
  })
}

resource "aws_cloudwatch_log_group" "beacon" {
  name              = "/aws/lambda/canari-beacon"
  retention_in_days = 90
}

data "archive_file" "beacon" {
  type        = "zip"
  source_file = "${path.module}/lambda/beacon.py"
  output_path = "${path.module}/.build/beacon.zip"
}

resource "aws_lambda_function" "beacon" {
  function_name                  = "canari-beacon"
  role                           = aws_iam_role.beacon.arn
  runtime                        = "python3.13"
  architectures                  = ["arm64"]
  handler                        = "beacon.handler"
  filename                       = data.archive_file.beacon.output_path
  source_code_hash               = data.archive_file.beacon.output_base64sha256
  timeout                        = 10
  reserved_concurrent_executions = var.reserved_concurrency

  environment {
    variables = {
      TABLE = aws_dynamodb_table.tokens.name
      TOPIC = aws_sns_topic.alerts.arn
    }
  }

  depends_on = [aws_cloudwatch_log_group.beacon]
}

resource "aws_lambda_function_url" "beacon" {
  function_name      = aws_lambda_function.beacon.function_name
  authorization_type = "NONE"
}

# 認証なしの Function URL には InvokeFunctionUrl と InvokeFunction の両方の許可が要る
resource "aws_lambda_permission" "url" {
  statement_id           = "FunctionURLAllowPublicAccess"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.beacon.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}

resource "aws_lambda_permission" "invoke" {
  statement_id             = "FunctionURLAllowInvokeAction"
  action                   = "lambda:InvokeFunction"
  function_name            = aws_lambda_function.beacon.function_name
  principal                = "*"
  invoked_via_function_url = true
}

output "url" {
  value = aws_lambda_function_url.beacon.function_url
}
