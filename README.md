# Vikunja Telegram Bot 🤖

A lightweight Telegram bot to create and manage Vikunja tasks using quick syntax or guided UI.

## Features
- 🔁 Quick task creation via Telegram
- 🧠 Smart parsing (`*label`, `+project`, `!priority`, `tomorrow`)
- 📆 View and edit tasks, labels, and due dates
- 👥 Multi-user support with per-chat authentication
- 🛠️ Minimal deployment using Python + Telegram + requests

## Setup

1. Clone the repo
2. Create a `.env` file with your credentials:
   ```env
   TELEGRAM_TOKEN=your_telegram_token
   VIKUNJA_API=http://your-vikunja-url/api/v1
   
   # Optional: Set default credentials for backward compatibility
   VIKUNJA_USER=your_username
   VIKUNJA_PASSWORD=your_password
   ```
3. Install dependencies:
    ```pip install python-telegram-bot requests python-dotenv```
4. Create a venv
5. Run the bot:
    ```python vikunja_bot.py```

## Usage

### Multi-User Authentication

The bot now supports multiple users! Each user can authenticate with their own Vikunja credentials:

1. Start a conversation with the bot: `/start`
2. Log in with your credentials: `/login`
3. Enter your Vikunja username when prompted
4. Enter your Vikunja password when prompted (the message will be deleted for security)
5. Use the bot commands: `/tasks`, `/today`, `/status`
6. Log out when done: `/logout`

### Commands

- `/start` - Welcome message and command list
- `/login` - Authenticate with your Vikunja credentials
- `/logout` - Log out from your account
- `/tasks` - View, edit, or complete your active tasks
- `/today` - Show all tasks due today
- `/status` - Check Vikunja API connection status

### Legacy Single-User Mode

If you set `VIKUNJA_USER` and `VIKUNJA_PASSWORD` in the `.env` file, users will be automatically authenticated with those credentials on `/start`. This provides backward compatibility with the single-user setup.