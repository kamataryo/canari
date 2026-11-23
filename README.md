# canari

```plaintext
                                       .-.
                                      ( o >
                             _        /   \
   ___ __ _ _ __   __ _ _ __(_)      / /// )
  / __/ _` | '_ \ / _` | '__| |     / ///  )
 | (_| (_| | | | | (_| | |  | |    /_____./
  \___\__,_|_| |_|\__,_|_|  |_|   //   ||
```

給与一覧やパスワード一覧に見せかけたおとりファイルを作り、開かれたらメールで知らせる炭鉱のカナリア。ファイルには透明な 1px の画像（とリンク）が外部参照で埋め込まれていて、取りに来たアクセスを AWS Lambda が受けて通知する。

## 必要なもの

- AWS CLI v2（`aws login` が使えるもの）
- Terraform 1.5 以上
- Python 3.9 以上（標準ライブラリのみ）
- zsh（補完を使う場合）

## インストール

```sh
git clone git@github.com:kamataryo/tf-canary-securite.git
cd tf-canary-securite
aws login
```

### デプロイ

リソースは aws CLI に設定されたリージョンに作られる。

```sh
terraform init
env $(aws configure export-credentials --format env-no-export) terraform apply
```

同時実行数の上限が 10 のままのアカウントでは apply が失敗するので、`-var reserved_concurrency=-1` を付ける。

### パスを通す

```sh
mkdir -p ~/.local/bin
ln -s "$PWD/canari" ~/.local/bin/canari
```

`~/.local/bin` がパスに入っていなければ `~/.zshrc` に足す。

```sh
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
```

### 補完

`~/.zshrc` の `compinit` より後に読み込まれるように足す（oh-my-zsh などを使っていれば末尾でよい）。

```sh
echo 'source <(canari completion)' >> ~/.zshrc
exec zsh
```

### 通知先

```sh
canari notify add
```

届いた確認メールのリンクは開かずに URL をコピーして貼る。こうするとメールの購読解除リンクから解除できなくなり、うっかり踏んで通知が止まるのを防げる。

`canari notify list` で「確認済み・解除保護」になっていれば OK。

## 使い方

```
canari new              おとりファイルをカレントディレクトリに作る
canari list [ラベル]    ラベルごとの一覧。ラベル（部分一致）を付けるとファイルごと
canari revoke [ラベル]  失効させる（通知は止まり、記録は残る）。ラベルで絞り込める
canari remove [ラベル]  台帳から消す（試験用や、もう置いていないもの）。ラベルで絞り込める
canari notify list      通知先の一覧
canari notify add       通知先のメールを足す
canari notify remove    通知先のメールを外す
canari stack            スタックの状態
```

ファイルは置き場所ごとに `canari new` で作り、置き場所をラベルにする（`Google Drive`、`Dropbox /経理/` など）。2 回目からは既存のラベルを選べるので、表記ゆれで分かれない。

```sh
canari list            # ラベルごと
canari list dropbox    # Dropbox のファイルごと
canari revoke dropbox  # Dropbox から撤去したら、all で全部失効
canari remove test     # 試験用に作ったものを台帳から消す
```

`revoke` したものは鳴っても通知されないが、記録は `list` に残る（撤去したあとに鳴れば、誰かが事前にコピーしていた証拠になる）。`remove` は台帳ごと消すので、以後鳴っても何も残らない。

鳴ったときのリクエストはヘッダごと CloudWatch Logs に 90 日残る。

```sh
aws logs tail /aws/lambda/canari-beacon --since 1d
```

## 開発

```sh
python3 test_canari.py   # 生成したファイルが壊れていないか
social/build.sh          # GitHub の Social preview 画像（要 Google Chrome）
```

偽の AWS アクセスキーによる検知は [docs/phase2.md](docs/phase2.md) にまとめてある（未実装）。
