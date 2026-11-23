# Phase 2: 偽の AWS アクセスキー

ビーコン（Phase 1）とは別の通知経路。権限ゼロの IAM ユーザーのアクセスキーをおとりとして置き、使われたら通知する。

## なぜ要るか

- 開かれなくても鳴る。持ち出されたキーは TruffleHog などの自動スキャナがすぐ `sts:GetCallerIdentity` で生死を確かめるので、人が中を見なくても検知できる
- docx / xlsx のビーコンが効かない場所（サーバー、リポジトリ、`.env`、パスワード一覧）を補う
- 自前で持つので、canarytokens.org のように発行元アカウント ID から見破られない

## 流れ

```
canari new ──> IAM ユーザー作成（権限なし + 全拒否）──> アクセスキー発行 ──> 台帳に登録 ──> ファイル出力

キーが使われる ──> CloudTrail（全リージョン）──> CloudWatch Logs
  ──> サブスクリプションフィルタ { $.userIdentity.accessKeyId = "AKIA*" }
  ──> canari-beacon Lambda ──> 台帳で照合 ──> SNS（Phase 1 と同じ通知先）
```

## CLI

`canari new` の候補に「AWS アクセスキー」を足す。処理の順番:

1. IAM ユーザーを作る。名前は普通のもの（`ci-deploy`、`backup-s3`、`svc-reporting`、`github-actions` など）。`canari` を名乗らない（`GetCallerIdentity` で攻撃者に ARN が見える）。衝突したら番号を付ける
2. 全拒否のインラインポリシーを付ける（`Deny * on *`）。後から誤ってグループに入れても何もできないように
3. アクセスキーを発行する
4. 台帳に登録する。`id` はアクセスキー ID（`AKIA...`）、ほかの項目はビーコンと同じ（`template`、`filename`、`label`、`created_at`、`hit_count`）に `iam_user` を足す
5. ファイルを書き出す。シークレットは台帳に残さない

途中で失敗したら、作った IAM ユーザーとキーを消す（鳴らないキーを残さない）。

- `revoke`: ビーコンと同じく記録だけ（通知しない）。キーは消さない。消すと以後の使用がアカウントの CloudTrail に残らず、検知できなくなる
- `list`: 変更なし

CLI を使う側に要る IAM 権限: `iam:CreateUser`、`iam:PutUserPolicy`、`iam:CreateAccessKey`、`iam:DeleteUser`、`iam:DeleteUserPolicy`、`iam:DeleteAccessKey`

## Lambda

- `event` に `awslogs` があれば CloudWatch Logs サブスクリプションから来たもの。base64 → gzip を展開し、`logEvents` ごとに CloudTrail の JSON を読んで `userIdentity.accessKeyId` で照合する
- 5 分の重複抑止、失効済みは記録だけ、という振る舞いはビーコンと同じ。`hit()` を共通にし、通知に載せる詳細だけ呼び出し側から渡す
- 通知に載せるもの: `eventName`、`eventSource`、`awsRegion`、`sourceIPAddress`、`userAgent`、`errorCode`

## Terraform

| リソース | 内容 |
|---|---|
| `aws_s3_bucket` | trail の保存先。`bucket_prefix = "canari-trail-"`。CloudTrail 用のバケットポリシーと、30 日で消すライフサイクル |
| `aws_cloudwatch_log_group` | `/aws/cloudtrail/canari`。検知に使うだけなので保存期間は短く（7 日） |
| `aws_iam_role` | CloudTrail が CloudWatch Logs に書くためのロール |
| `aws_cloudtrail` | `is_multi_region_trail = true`、`include_global_service_events = true`、管理イベントのみ |
| `aws_cloudwatch_log_subscription_filter` | `{ $.userIdentity.accessKeyId = "AKIA*" }` → `canari-beacon` |
| `aws_lambda_permission` | `logs.amazonaws.com` からの呼び出しを許可 |

Lambda のロールは変更なし（`dynamodb:UpdateItem`、`sns:Publish` のまま）。追加は 60 行ほどの見込み。

## 制約

- 遅い: 使われてから通知まで 5〜15 分（CloudTrail の配信待ち）
- 費用: 全リージョンの管理イベントを CloudWatch Logs に流す取り込み料金。個人アカウントなら月 1 ドル未満が目安。アカウントにすでに別の trail があると、2 本目の管理イベントは 10 万件あたり 2 ドル
- 完全ではない: CloudTrail に残らない API でキーの生死だけ確かめる手口がある
- 攻撃者にアカウント ID と IAM ユーザー名が見える

## 未決

1. アカウントにすでに CloudTrail の trail があるか。あれば、その trail のロググループにサブスクリプションフィルタだけ足す形も検討する
2. 出力形式。候補はコンソールのダウンロードと同じ `<ユーザー名>_accessKeys.csv`（推奨）、`~/.aws/credentials` 形式の `credentials`、`.env`
3. 既存のテンプレート（パスワード一覧、サーバー接続情報、接続情報.txt）にもキーを混ぜるか
