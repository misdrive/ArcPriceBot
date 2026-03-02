# ARC Raiders Price Bot

A Discord bot with a `/value` slash command that looks up the **Seeds** value of any item in the ARC Raiders database on [MetaForge](https://metaforge.app/arc-raiders/database).

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Create a Discord bot

1. Go to https://discord.com/developers/applications and create a new application.
2. Under **Bot**, click **Add Bot** and copy the **Token**.
3. Under **OAuth2 → URL Generator**, select the `bot` and `applications.commands` scopes, then the `Send Messages` permission. Use the generated URL to invite the bot to your server.

### 3. Configure your token

Edit `.env` and replace `your_token_here` with your bot token:

```
DISCORD_TOKEN=your_actual_token
```

### 4. Run the bot

```bash
python bot.py
```

## Usage

In any channel the bot has access to:

```
/value battery
/value medkit
/value copper wire
```

The bot will reply with an embed showing the Seeds value for the item.
