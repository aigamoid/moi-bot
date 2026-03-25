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
3. **Bot Permissions**: `Send Messages`, `Read Message History`, `Add Reactions` にチェック
4. 生成されたURLをブラウザで開き、対象サーバーに招待

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
