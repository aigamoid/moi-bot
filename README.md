# moi-bot

Discord上で「もい」を検知して「もい」とリプライし、🦆リアクションを付けるBot。

## セットアップ

### 1. Discord Bot の作成

1. [Discord Developer Portal](https://discord.com/developers/applications) で「New Application」を作成
2. **Bot** タブを開く
3. **Privileged Gateway Intents** セクションで **Message Content Intent** を有効化（必須）
4. 「Reset Token」でトークンを生成し、コピーする

### 2. Bot をサーバーに招待

1. **OAuth2** > **URL Generator** を開く
2. **Scopes**: `bot` にチェック
3. **Bot Permissions**: `View Channels`, `Send Messages`, `Send Messages in Threads`, `Read Message History`, `Add Reactions` にチェック
4. 生成されたURLをブラウザで開き、対象サーバーに招待

対象チャンネルの権限上書きでも、閲覧・送信・履歴の閲覧・リアクションが許可されていることを確認してください。スレッドへの返信には `Send Messages in Threads` が必要で、通常チャンネルの `Send Messages` だけでは代替できません。非公開スレッドではBotが参加していることも必要です。

招待後は、通常チャンネルとBotが閲覧できるスレッドのそれぞれで「もい」と投稿し、返信と🦆を確認してください。ログに `forbidden` が出る場合は、該当チャンネルの権限を確認します。[Discord のスレッド権限仕様](https://docs.discord.com/developers/topics/permissions#inherited-permissions-threads)

### 3. 環境変数の設定

```bash
cp .env.example .env
```

`.env` を編集し、コピーしたトークンを設定:

```
DISCORD_TOKEN=your-bot-token-here
```

### 4. 起動（Docker）

```bash
docker-compose up -d --build
```

### ログ確認

```bash
docker-compose logs -f moi-bot
```

### 停止

```bash
docker-compose down
```

## 動作

| トリガー | 応答 |
|---------|------|
| メッセージに「もい」を含む | 「もい」とリプライ + 🦆リアクション |
| Botからのメッセージ | 無視（無限ループ防止） |

連投時は、同じユーザーは10秒、同じチャンネル（スレッドも個別に数える）は2秒に1件まで受け付けます。同時に処理するメッセージは最大8件で、超過分は返信待ちの列に入れず破棄します。クールダウンに使うIDの記録もユーザー・チャンネルそれぞれ最大4096件です。期限切れを受付時に取り除き、上限に達している間は新しい投稿を受け付けません。これらの値は `bot/responder.py` の `Limits` で定義しています。

返信とリアクションにはそれぞれ10秒のタイムアウトがあります。返信が権限不足・HTTPエラー・タイムアウトになっても、リアクションは独立して試します。対象が削除されていた場合は後続処理を省略します。権限不足の無限リトライは行いません。制限はプロセスごとなので、同じトークンで複数のBotプロセスを起動しないでください。

## 開発用テスト

Python 3.12 で、依存関係を導入して実行します。

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

テストはDiscordのログインや実APIへの投稿をせず、SDKのイベント処理とAPIの応答をローカルで検証します。実サーバー上の権限確認は、上の招待手順で行ってください。
