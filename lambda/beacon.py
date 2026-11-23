"""canari のビーコン。登録済みトークンへのアクセスを SNS に通知する"""
import json
import os
import re
import time
import traceback
from datetime import datetime, timedelta, timezone

import boto3

GIF = "R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
WINDOW = 300  # Word は 1 回開くと OPTIONS/HEAD/GET を続けて送ってくるので、5 分を 1 回の検知にまとめる
PATH = re.compile(r"/t/([A-Za-z0-9_-]{22})(?:[./].*)?")
JST = timezone(timedelta(hours=9))
ddb = boto3.client("dynamodb")
sns = boto3.client("sns")


def handler(event, _context):
    http = event["requestContext"]["http"]
    path = event.get("rawPath", "")
    headers = event.get("headers", {})
    # 全リクエストをヘッダごと CloudWatch Logs に残す（未登録・重複抑止したものも）
    print(json.dumps({"path": path, "query": event.get("rawQueryString", ""), "method": http["method"],
                      "ip": http["sourceIp"], "headers": headers}, ensure_ascii=False))
    m = PATH.fullmatch(path)
    if m:
        try:
            hit(m[1], path, http, headers)
        except Exception:
            traceback.print_exc()  # 失敗しても応答は変えない。攻撃者に違いを見せない
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "image/gif", "Cache-Control": "no-store"},
        "body": GIF,
        "isBase64Encoded": True,
    }


def hit(token, path, http, headers):
    now = int(time.time())
    try:
        item = ddb.update_item(
            TableName=os.environ["TABLE"],
            Key={"id": {"S": token}},
            UpdateExpression="SET last_hit_at = :now ADD hit_count :one",
            ConditionExpression="attribute_exists(id) AND (attribute_not_exists(last_hit_at) OR last_hit_at < :cutoff)",
            ExpressionAttributeValues={":now": {"N": str(now)}, ":one": {"N": "1"}, ":cutoff": {"N": str(now - WINDOW)}},
            ReturnValues="ALL_NEW",
        )["Attributes"]
    except ddb.exceptions.ConditionalCheckFailedException:
        return  # 未登録か、直前の検知から 5 分以内
    if "revoked_at" in item:
        return  # 失効済みは記録だけ

    def jst(key):
        return datetime.fromtimestamp(int(item[key]["N"]), JST).strftime("%Y-%m-%d %H:%M:%S")

    name = item["filename"]["S"]
    sns.publish(
        TopicArn=os.environ["TOPIC"],
        Subject=f"canari: {name}"[:99],
        Message="\n".join([
            f"メモ: {item['description']['S']}",
            f"ファイル: {name}",
            f"日時: {jst('last_hit_at')}",
            f"IP: {http['sourceIp']}",
            f"UA: {http.get('userAgent', '-')}",
            f"リクエスト: {http['method']} {path}",
            f"作成: {jst('created_at')}",
            "",
            "ヘッダ:",
            *(f"  {k}: {v}" for k, v in sorted(headers.items())),
        ]),
    )
