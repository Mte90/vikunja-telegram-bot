# Vikunja Telegram Bot 🤖

A lightweight Telegram bot to create and manage Vikunja tasks using quick syntax or guided UI.

## Features
- 🔁 Quick task creation via Telegram
- 🧠 Smart parsing (`*label`, `+project`, `!priority`, `tomorrow`)
- 📆 View and edit tasks, labels, and due dates
- 👥 Multi-user support with per-chat authentication
- ⚡ Auto-create tasks from plain messages
- ✅ Quick task completion with inline buttons
- 🛠️ Minimal deployment using Python + Telegram + requests

## Setup

1. Clone the repo
2. Create a `.env` file with your credentials:
   ```env
   TELEGRAM_TOKEN=your_telegram_token
   VIKUNJA_API=http://your-vikunja-url/api/v1
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

### Quick Task Creation

Simply send any message (without a command) to automatically create a task! After creating the task, the bot will show you a list of your active tasks with quick action buttons.

**Examples:**
- `Buy groceries tomorrow` - Creates a task with a due date
- `Finish report !5` - Creates a high priority task (priority 5)
- `Call John +Work` - Creates a task in the "Work" project

**Quick Actions:**
After creating a task, you'll see inline buttons to quickly mark tasks as done without entering any commands. Just tap "✅ Mark #1 Done" to complete a task instantly!

### Credential Storage

Your credentials are securely saved to a local file (`user_credentials.json`) when you log in. This allows:
- Automatic re-authentication when the bot restarts
- Persistent sessions across bot restarts
- No need to log in every time you use the bot

The credentials file is protected with restrictive permissions (600 - owner read/write only).

**Security Note**: Credentials are stored in plain text in the JSON file. Ensure the bot runs in a secure environment and the credentials file is not accessible to unauthorized users.

To remove your saved credentials, use the `/logout` command.