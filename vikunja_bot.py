import os
import logging
import requests
import re
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes,
    CallbackQueryHandler, MessageHandler, filters, ConversationHandler
)

load_dotenv()

# --- Configuration ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
VIKUNJA_API = os.getenv("VIKUNJA_API", "http://yourvikunjaip:port/api/v1")
CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE", "user_credentials.json")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Constants ---
TASKS_PER_PAGE = 5
PROJECT_CACHE_SECONDS = 60 # Cache projects for 60 seconds

# --- Conversation States ---
# For /login
(LOGIN_USERNAME, LOGIN_PASSWORD) = range(2)
# For /newtask and /quicktask
(TITLE, PRIORITY, LABEL, PROJECT, DUEDATE, REPEAT, CONFIRM) = range(7, 14)
# For /tasks management
(TASK_LIST_VIEW, TASK_EDIT_VIEW, TASK_EDIT_PROJECT, 
 TASK_EDIT_PRIORITY, TASK_EDIT_DUE, TASK_EDIT_LABELS, TASK_EDIT_REPEAT) = range(14, 21)

# --- Vikunja API Functions ---

def load_saved_credentials():
    """Load saved credentials from file."""
    try:
        if os.path.exists(CREDENTIALS_FILE):
            with open(CREDENTIALS_FILE, 'r') as f:
                return json.load(f)
        return {}
    except Exception as e:
        logger.error(f"❌ Error loading credentials: {e}")
        return {}

def save_credentials(chat_id, username, password):
    """Save credentials to file for persistence across bot restarts."""
    try:
        credentials = load_saved_credentials()
        credentials[str(chat_id)] = {
            'username': username,
            'password': password
        }
        with open(CREDENTIALS_FILE, 'w') as f:
            json.dump(credentials, f, indent=2)
        logger.info(f"✅ Saved credentials for chat_id: {chat_id}")
    except Exception as e:
        logger.error(f"❌ Error saving credentials: {e}")

def delete_saved_credentials(chat_id):
    """Delete saved credentials for a user."""
    try:
        credentials = load_saved_credentials()
        if str(chat_id) in credentials:
            del credentials[str(chat_id)]
            with open(CREDENTIALS_FILE, 'w') as f:
                json.dump(credentials, f, indent=2)
            logger.info(f"✅ Deleted credentials for chat_id: {chat_id}")
    except Exception as e:
        logger.error(f"❌ Error deleting credentials: {e}")

def get_user_session(context: ContextTypes.DEFAULT_TYPE, chat_id=None):
    """Get or initialize the user session data."""
    if 'vikunja_token' not in context.user_data:
        context.user_data['vikunja_token'] = None
    if 'username' not in context.user_data:
        context.user_data['username'] = None
    if 'password' not in context.user_data:
        context.user_data['password'] = None
    
    # Try to load saved credentials if not already in session
    if not context.user_data.get('username') and chat_id:
        saved_creds = load_saved_credentials()
        chat_id_str = str(chat_id)
        if chat_id_str in saved_creds:
            context.user_data['username'] = saved_creds[chat_id_str].get('username')
            context.user_data['password'] = saved_creds[chat_id_str].get('password')
            logger.info(f"✅ Loaded saved credentials for chat_id: {chat_id_str}")
    
    return context.user_data

def is_authenticated(context: ContextTypes.DEFAULT_TYPE):
    """Check if the user has authenticated."""
    session = get_user_session(context)
    return session.get('vikunja_token') is not None

def authenticate(context: ContextTypes.DEFAULT_TYPE, username=None, password=None, save=False, chat_id=None):
    """Authenticate with the Vikunja API and get a token for the user."""
    session = get_user_session(context)
    
    # Use provided credentials or stored credentials
    if username and password:
        session['username'] = username
        session['password'] = password
        if save and chat_id:
            save_credentials(chat_id, username, password)
    else:
        username = session.get('username')
        password = session.get('password')
    
    if not username or not password:
        logger.error("❌ No credentials available for authentication")
        return False
    
    try:
        response = requests.post(f"{VIKUNJA_API}/login", json={
            "username": username,
            "password": password
        }, timeout=10)
        if response.status_code == 200:
            session['vikunja_token'] = response.json()["token"]
            session['username'] = username
            session['password'] = password
            logger.info(f"✅ Successfully authenticated user: {username}")
            return True
        else:
            logger.error(f"❌ Vikunja login failed for {username}: {response.status_code} - {response.text}")
            return False
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Vikunja connection error: {e}")
        return False

def get_headers(context: ContextTypes.DEFAULT_TYPE):
    """Get authorization headers for the user."""
    session = get_user_session(context)
    token = session.get('vikunja_token')
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}

def get_all_projects_cached(context: ContextTypes.DEFAULT_TYPE):
    """Get all projects, using a short-term cache to avoid repeated API calls."""
    now = datetime.now()
    # Use user-specific cache
    if 'project_cache' not in context.user_data:
        context.user_data['project_cache'] = {}
    
    cache = context.user_data['project_cache']
    if cache and 'timestamp' in cache and (now - cache['timestamp']) < timedelta(seconds=PROJECT_CACHE_SECONDS):
        return cache['data']

    try:
        response = requests.get(f"{VIKUNJA_API}/projects", headers=get_headers(context), timeout=10)
        if response.status_code == 200:
            projects = response.json()
            context.user_data['project_cache'] = {'data': projects, 'timestamp': now}
            return projects
        return []
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Error fetching projects: {e}")
        return []

def get_project_by_name(project_name, context: ContextTypes.DEFAULT_TYPE):
    """Get a project by its name."""
    projects = get_all_projects_cached(context)
    for proj in projects:
        if proj["title"].lower() == project_name.lower():
            return proj
    return None

def get_project_by_id(project_id, context: ContextTypes.DEFAULT_TYPE):
    """Get a project by its ID."""
    projects = get_all_projects_cached(context)
    for proj in projects:
        if proj["id"] == project_id:
            return proj
    return None

def _format_display_date(due_date_str):
    """Helper to format due date strings for display."""
    if not due_date_str or not isinstance(due_date_str, str):
        return "No due date"
    try:
        # Vikunja's API format
        return datetime.strptime(due_date_str, '%Y-%m-%dT%H:%M:%SZ').strftime('%Y-%m-%d')
    except ValueError:
        return due_date_str # Return as is if format is different

def get_active_tasks_from_projects(context: ContextTypes.DEFAULT_TYPE, date_filter=None):
    """Helper function to fetch active (non-completed) tasks from all projects.
    
    Args:
        context: The user context
        date_filter: Optional date string in YYYY-MM-DD format to filter tasks by due date
    
    Returns:
        List of active tasks
    """
    all_tasks = []
    projects = get_all_projects_cached(context)
    
    for project in projects:
        params = {'due_date': date_filter} if date_filter else {}
        response = requests.get(
            f"{VIKUNJA_API}/projects/{project['id']}/tasks", 
            headers=get_headers(context), 
            params=params,
            timeout=10
        )
        if response.status_code == 200:
            tasks_data = response.json()
            # Ensure we handle both list and dict responses for tasks
            tasks = tasks_data if isinstance(tasks_data, list) else tasks_data.get('tasks', [])
            for task in tasks:
                task['project_id'] = project['id']  # Ensure project context
            all_tasks.extend(tasks)
    
    # Filter to only active (non-completed) tasks
    return [t for t in all_tasks if isinstance(t, dict) and not t.get('done', False)]

def parse_vikunja_task_format(task_text):
    """Parse Vikunja's special formatting for tasks to extract details."""
    parsed_data = {"title": task_text, "labels": [], "priority": None, "project": None, "due_date": None, "repeat": None}
    
    # Simple patterns first
    patterns = {
        'labels': r'\*(?:"([^"]+)"|\'([^\']+)\'|(\S+))',
        'priority': r'!([1-5])',
        'project': r'\+(?:"([^"]+)"|\'([^\']+)\'|(\S+))',
    }
    
    # Extract labels
    labels = re.findall(patterns['labels'], task_text)
    for match in labels:
        parsed_data["labels"].append(next(s for s in match if s))
    task_text = re.sub(patterns['labels'], '', task_text)

    # Extract priority
    priority_match = re.search(patterns['priority'], task_text)
    if priority_match:
        parsed_data["priority"] = int(priority_match.group(1))
        task_text = re.sub(patterns['priority'], '', task_text, 1)

    # Extract project
    project_match = re.search(patterns['project'], task_text)
    if project_match:
        parsed_data["project"] = next(s for s in project_match.groups() if s)
        task_text = re.sub(patterns['project'], '', task_text, 1)

    # Date parsing logic
    def get_next_weekday(weekday):
        days_ahead = weekday - datetime.now().weekday()
        if days_ahead <= 0: days_ahead += 7
        return (datetime.now() + timedelta(days=days_ahead)).date()

    date_patterns = {
        r'\btoday\b': lambda m: datetime.now().date(),
        r'\btomorrow\b': lambda m: (datetime.now() + timedelta(days=1)).date(),
        r'\bnext monday\b': lambda m: get_next_weekday(0),
        r'\bnext tuesday\b': lambda m: get_next_weekday(1),
        r'\bnext wednesday\b': lambda m: get_next_weekday(2),
        r'\bnext thursday\b': lambda m: get_next_weekday(3),
        r'\bnext friday\b': lambda m: get_next_weekday(4),
        r'\bnext saturday\b': lambda m: get_next_weekday(5),
        r'\bnext sunday\b': lambda m: get_next_weekday(6),
        r'in (\d+) days?': lambda m: (datetime.now() + timedelta(days=int(m.group(1)))).date(),
        r'in (\d+) weeks?': lambda m: (datetime.now() + timedelta(weeks=int(m.group(1)))).date(),
        r'(\d{1,2})/(\d{1,2})/(\d{4})': lambda m: datetime(int(m.group(3)), int(m.group(2)), int(m.group(1))).date(),
    }
    
    for pattern, func in date_patterns.items():
        match = re.search(pattern, task_text, re.IGNORECASE)
        if match:
            parsed_data["due_date"] = func(match).strftime('%Y-%m-%d')
            task_text = re.sub(pattern, '', task_text, 1, flags=re.IGNORECASE)
            break
            
    parsed_data["title"] = ' '.join(task_text.split())
    return parsed_data

def create_task(data, context: ContextTypes.DEFAULT_TYPE):
    """Constructs and sends a request to create a new task in Vikunja."""
    try:
        payload = {
            "title": data["title"],
            "priority": int(data.get("priority", 3)),
            "project_id": int(data.get("project_id", 1)),
        }
        
        if data.get("due"):
            payload["due_date"] = f"{data['due']}T23:59:59Z"
        if data.get("repeat"):
            payload["repeat_after"] = data["repeat"]
        if data.get("label_ids"):
            payload["label_ids"] = data["label_ids"]

        logger.info(f"🔍 Creating task with payload: {payload}")
        response = requests.put(f"{VIKUNJA_API}/projects/{payload['project_id']}/tasks", headers=get_headers(context), json=payload, timeout=10)
        
        if response.status_code in [200, 201]:
            logger.info(f"✅ Task created successfully: {response.json().get('title')}")
            return True, response.json()
        else:
            logger.error(f"❌ Task creation failed: {response.status_code} - {response.text}")
            return False, f"HTTP {response.status_code}: {response.text}"
            
    except Exception as e:
        logger.error(f"❌ Error during task creation: {e}")
        return False, f"Error: {e}"

# --- Command Handlers: General ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command - shows welcome message and instructions."""
    chat_id = update.effective_chat.id
    
    # Try to load and authenticate with saved credentials if available
    session = get_user_session(context, chat_id)
    if session.get('username') and session.get('password') and not is_authenticated(context):
        authenticate(context)
    
    if is_authenticated(context):
        session = get_user_session(context)
        await update.message.reply_text(
            f"🎯 Welcome to Vikunja Bot!\n\n"
            f"✅ You are logged in as: {session.get('username')}\n\n"
            "Commands:\n"
            "/newtask - Create a new task with a guided process.\n"
            "/quicktask - Create a task using Vikunja's quick-add syntax.\n"
            "/tasks - View, edit, or complete your active tasks.\n"
            "/today - Show all tasks due today.\n"
            "/projects - List all available projects.\n"
            "/status - Check Vikunja API connection status.\n"
            "/logout - Log out from your Vikunja account."
        )
    else:
        await update.message.reply_text(
            "🎯 Welcome to Vikunja Bot!\n\n"
            "⚠️ You need to log in first.\n\n"
            "Use /login to authenticate with your Vikunja credentials.\n\n"
            "Commands after login:\n"
            "/tasks - View and manage tasks\n"
            "/today - Show tasks due today\n"
            "/status - Check connection status"
        )

async def login_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the login conversation."""
    await update.message.reply_text(
        "🔐 Let's log you in to Vikunja!\n\n"
        "Please enter your Vikunja username:\n\n"
        "Use /cancel to abort."
    )
    return LOGIN_USERNAME

async def login_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle username input during login."""
    username = update.message.text.strip()
    context.user_data['temp_username'] = username
    await update.message.reply_text(
        f"👤 Username: {username}\n\n"
        "Now please enter your Vikunja password:"
    )
    return LOGIN_PASSWORD

async def login_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle password input and complete login."""
    password = update.message.text.strip()
    username = context.user_data.get('temp_username')
    chat_id = update.effective_chat.id
    
    # Delete the message containing the password for security
    try:
        await update.message.delete()
    except Exception as e:
        logger.warning(f"Could not delete password message: {e}")
    
    await update.message.reply_text("🔄 Authenticating...")
    
    if authenticate(context, username, password, save=True, chat_id=chat_id):
        # Clear temporary data
        context.user_data.pop('temp_username', None)
        await update.message.reply_text(
            f"✅ Successfully logged in as {username}!\n\n"
            "Your credentials have been saved securely.\n\n"
            "You can now use:\n"
            "/tasks - View and manage tasks\n"
            "/today - Show tasks due today\n"
            "/status - Check connection status\n"
            "/logout - Log out"
        )
        return ConversationHandler.END
    else:
        context.user_data.pop('temp_username', None)
        await update.message.reply_text(
            "❌ Authentication failed. Please check your credentials and try again.\n\n"
            "Use /login to try again."
        )
        return ConversationHandler.END

async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log out the user."""
    session = get_user_session(context)
    username = session.get('username', 'Unknown')
    chat_id = update.effective_chat.id
    
    # Delete saved credentials
    delete_saved_credentials(chat_id)
    
    # Clear all user data
    context.user_data.clear()
    
    await update.message.reply_text(
        f"👋 Logged out successfully!\n\n"
        f"Previous user: {username}\n\n"
        "Your saved credentials have been removed.\n\n"
        "Use /login to log in again."
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check connection status and authentication."""
    if not is_authenticated(context):
        await update.message.reply_text(
            "❌ You are not logged in.\n\n"
            "Use /login to authenticate with your Vikunja credentials."
        )
        return
    
    # Try to re-authenticate to verify credentials are still valid
    if authenticate(context):
        session = get_user_session(context)
        await update.message.reply_text(
            f"✅ Connected to Vikunja successfully!\n"
            f"👤 Logged in as: {session.get('username')}"
        )
    else:
        await update.message.reply_text(
            "❌ Cannot connect to Vikunja. Your session may have expired.\n\n"
            "Use /login to authenticate again."
        )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Action canceled.")
    context.user_data.clear()
    return ConversationHandler.END

# --- Command Handlers: Task Listing & Management (/tasks) ---

async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point for the task management conversation."""
    if not is_authenticated(context):
        await update.message.reply_text(
            "❌ You need to log in first.\n\n"
            "Use /login to authenticate with your Vikunja credentials."
        )
        return ConversationHandler.END
    
    if not authenticate(context):
        await update.message.reply_text("❌ Cannot connect to Vikunja.")
        return ConversationHandler.END

    context.user_data['task_page'] = 0
    await show_task_page(update, context)
    return TASK_LIST_VIEW

async def show_task_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays a paginated list of active tasks."""
    page = context.user_data.get('task_page', 0)
    
    try:
        # Fetch all active tasks using helper function
        active_tasks = get_active_tasks_from_projects(context)
        
        if not active_tasks:
            await update.message.reply_text("✅ No active tasks found!")
            return

        total_pages = (len(active_tasks) - 1) // TASKS_PER_PAGE + 1
        offset = page * TASKS_PER_PAGE
        page_tasks = active_tasks[offset : offset + TASKS_PER_PAGE]
        
        message = f"📋 *Tasks (Page {page+1}/{total_pages})*\n\nSelect a task to manage it."
        
        keyboard = []
        for i, task in enumerate(page_tasks, 1):
            keyboard.append([InlineKeyboardButton(
                f"{i}. {task.get('title', 'Untitled')}", 
                callback_data=f"task_select_{task['id']}"
            )])

        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"task_prev_{page}"))
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"task_next_{page}"))
        if nav_buttons:
            keyboard.append(nav_buttons)
            
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Edit the message if it's a callback, otherwise send a new one
        if update.callback_query:
            await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode="Markdown")
        else:
            await update.message.reply_text(message, reply_markup=reply_markup, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"❌ Error fetching tasks: {e}")
        await update.message.reply_text(f"❌ Error fetching tasks: {e}")

async def task_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles callbacks from the task list view (pagination, selection)."""
    query = update.callback_query
    await query.answer()
    
    action = query.data.split('_')[1]
    
    if action in ("prev", "next"):
        page = int(query.data.split('_')[2])
        context.user_data['task_page'] = page - 1 if action == "prev" else page + 1
        await show_task_page(update, context)
        return TASK_LIST_VIEW

    elif action == "select":
        task_id = query.data.split('_')[2]
        context.user_data['selected_task_id'] = task_id
        await show_task_edit_menu(update, context)
        return TASK_EDIT_VIEW

async def show_task_edit_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the action menu for a selected task."""
    task_id = context.user_data['selected_task_id']
    try:
        response = requests.get(f"{VIKUNJA_API}/tasks/{task_id}", headers=get_headers(context), timeout=10)
        if response.status_code != 200:
            await update.callback_query.edit_message_text("❌ Failed to fetch task details.")
            return

        task = response.json()
        project = get_project_by_id(task.get("project_id"), context)
        
        message = (
            f"📝 *Task:* {task.get('title', 'Untitled')}\n"
            f"------------------------------------\n"
            f"📁 *Project:* {project.get('title', 'Unknown') if project else 'Unknown'}\n"
            f"⭐ *Priority:* {task.get('priority', 'N/A')}\n"
            f"📅 *Due:* {_format_display_date(task.get('due_date'))}\n"
            f"🔁 *Repeat:* {task.get('repeat_after', 'None')}"
        )

        keyboard = [
            [InlineKeyboardButton("✅ Mark Done", callback_data="task_edit_done")],
            [InlineKeyboardButton("Change Project", callback_data="task_edit_project")],
            [InlineKeyboardButton("Change Priority", callback_data="task_edit_priority")],
            [InlineKeyboardButton("Change Due Date", callback_data="task_edit_due")],
            [InlineKeyboardButton("🗑️ Delete Task", callback_data="task_edit_delete")],
            [InlineKeyboardButton("⬅️ Back to List", callback_data="task_edit_back")]
        ]
        await update.callback_query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Error showing edit menu: {e}")
        await update.callback_query.edit_message_text(f"❌ Error: {e}")

async def task_edit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles callbacks from the task edit menu."""
    query = update.callback_query
    await query.answer()
    
    action = query.data.split('_')[-1] # e.g., 'done', 'project', 'back'
    task_id = context.user_data['selected_task_id']

    if action == "back":
        await show_task_page(update, context)
        return TASK_LIST_VIEW

    elif action == "done" or action == "delete":
        endpoint = f"{VIKUNJA_API}/tasks/{task_id}"
        try:
            if action == "done":
                response = requests.post(endpoint, headers=get_headers(context), json={"done": True}, timeout=10)
                success_msg = "✅ Task marked as done!"
            else: # delete
                response = requests.delete(endpoint, headers=get_headers(context), timeout=10)
                success_msg = "🗑️ Task deleted!"

            if response.status_code in [200, 204]:
                await query.edit_message_text(success_msg)
            else:
                await query.edit_message_text(f"❌ Operation failed ({response.status_code})")
        except Exception as e:
            await query.edit_message_text(f"❌ Error: {e}")
        return ConversationHandler.END

    elif action == "due":
        await query.edit_message_text("📅 Enter new due date (e.g., 'tomorrow', '2025-06-20') or 'none' to remove.")
        return TASK_EDIT_DUE
    
    # ... Other edit actions would go here, returning new states ...

    return TASK_EDIT_VIEW

async def handle_task_due_date_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles text input for updating a task's due date."""
    due_text = update.message.text.lower()
    task_id = context.user_data['selected_task_id']
    
    payload = {"due_date": None}
    if due_text != 'none':
        parsed = parse_vikunja_task_format(due_text)
        if parsed.get('due_date'):
            payload["due_date"] = f"{parsed['due_date']}T23:59:59Z"
        else:
            await update.message.reply_text("❌ Invalid date. Please try again (e.g., 'tomorrow', '2025-06-20').")
            return TASK_EDIT_DUE

    try:
        response = requests.post(f"{VIKUNJA_API}/tasks/{task_id}", headers=get_headers(context), json=payload, timeout=10)
        if response.status_code in [200, 204]:
            await update.message.reply_text(f"✅ Due date updated successfully!")
        else:
            await update.message.reply_text(f"❌ Failed to update due date ({response.status_code})")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

    # Show the main list again
    await show_task_page(update, context)
    return TASK_LIST_VIEW

# --- Command Handlers: Today's Tasks (/today) ---
async def today_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authenticated(context):
        await update.message.reply_text(
            "❌ You need to log in first.\n\n"
            "Use /login to authenticate with your Vikunja credentials."
        )
        return
    
    if not authenticate(context):
        await update.message.reply_text("❌ Cannot connect to Vikunja.")
        return

    today_str = datetime.now().strftime('%Y-%m-%d')
    
    try:
        projects = get_all_projects_cached(context)
        if not projects:
            await update.message.reply_text("📁 No projects found in Vikunja.")
            return

        # Use the helper function to get active tasks filtered by today's date
        today_tasks_list = get_active_tasks_from_projects(context, date_filter=today_str)

        if not today_tasks_list:
            await update.message.reply_text("👍 No tasks due today!")
            return

        message = "🗓️ *Tasks Due Today*\n\n"
        for task in today_tasks_list:
             project = get_project_by_id(task.get("project_id"), context)
             message += f"📝 *{task.get('title', 'Untitled')}* in project *{project.get('title', 'Unknown') if project else 'Unknown'}*\n"
        
        await update.message.reply_text(message, parse_mode='Markdown')

    except Exception as e:
        await update.message.reply_text(f"❌ Error fetching today's tasks: {e}")


# --- Main Application Setup ---
def main():
    if not TELEGRAM_TOKEN:
        logger.critical("❌ Missing TELEGRAM_TOKEN environment variable")
        return
    
    logger.info(f"🚀 Starting bot with Vikunja API: {VIKUNJA_API}")
    
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Conversation handler for login
    login_handler = ConversationHandler(
        entry_points=[CommandHandler("login", login_start)],
        states={
            LOGIN_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, login_username)],
            LOGIN_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, login_password)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_user=True,
        per_chat=True,
        per_message=False
    )

    # Conversation handler for listing and managing tasks (/tasks)
    task_management_handler = ConversationHandler(
        entry_points=[CommandHandler("tasks", list_tasks)],
        states={
            TASK_LIST_VIEW: [CallbackQueryHandler(task_list_callback, pattern="^task_")],
            TASK_EDIT_VIEW: [CallbackQueryHandler(task_edit_callback, pattern="^task_edit_")],
            TASK_EDIT_DUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_task_due_date_update)],
            # Add more states for editing other fields (priority, project) here
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_user=True,
        per_chat=True,
        per_message=False
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(login_handler)
    app.add_handler(CommandHandler("logout", logout))
    app.add_handler(CommandHandler("status", status))
    # app.add_handler(CommandHandler("projects", list_projects)) # Add this back if you have the function
    app.add_handler(CommandHandler("today", today_tasks))
    app.add_handler(task_management_handler)
    # Add other handlers like /newtask, /quicktask here if you have them

    logger.info("✅ Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
