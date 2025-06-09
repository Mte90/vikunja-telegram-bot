# Vikunja Telegram Bot 🤖

A lightweight Telegram bot to create and manage Vikunja tasks using quick syntax or guided UI.

## Features
- 🔁 Quick task creation via Telegram
- 🧠 Smart parsing (`*label`, `+project`, `!priority`, `tomorrow`)
- 📆 View and edit tasks, labels, and due dates
- 🛠️ Minimal deployment using Python + Telegram + requests

## Setup

1. Clone the repo
2. Create a `.env` file with your credentials:
   ```env
   TELEGRAM_TOKEN=your_telegram_token
   VIKUNJA_API=http://your-vikunja-url/api/v1
   VIKUNJA_USER=your_username
   VIKUNJA_PASSWORD=your_password
   ```
3. Install dependencies:
    ```pip install python-telegram-bot requests python-dotenv```
4. Create a venv
5. Run the bot:
    ```python vikunja_bot.py```