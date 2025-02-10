import os
import logging
from datetime import datetime, time, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from apscheduler.schedulers.background import BackgroundScheduler
from tinydb import TinyDB, Query
import nest_asyncio

# Bot token (already included for direct use)
TOKEN = "7955720833:AAHVRf7L12HbrZT9rtxHc0KB97kW22Blw2s"

# Setup logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize Database
db = TinyDB("habits.json")
User = Query()

# Initialize Scheduler
scheduler = BackgroundScheduler()
scheduler.start()

# Achievement definitions
ACHIEVEMENTS = {
    'streak_warrior': {
        'name': '🔥 Streak Warrior',
        'description': 'Maintain a 7-day streak',
        'threshold': 7
    },
    'habit_master': {
        'name': '⭐ Habit Master',
        'description': 'Complete a habit 30 times',
        'threshold': 30
    },
    'consistency_king': {
        'name': '👑 Consistency King',
        'description': 'Maintain a 30-day streak',
        'threshold': 30
    }
}

def calculate_streak(completion_dates):
    """Calculate the current streak from completion dates."""
    if not completion_dates or not isinstance(completion_dates, list):
        return 0

    dates = sorted([datetime.strptime(date, "%Y-%m-%d") for date in completion_dates], reverse=True)
    current_date = datetime.now().date()

    if dates[0].date() < current_date:
        current_date = current_date - timedelta(days=1)

    streak = 0
    for i, date in enumerate(dates):
        if date.date() == current_date - timedelta(days=i):
            streak += 1
        else:
            break
    return streak

def check_achievements(user_data, habit, streak):
    """Check and award new achievements."""
    if "achievements" not in user_data:
        user_data["achievements"] = {}

    new_achievements = []

    # Check streak-based achievements
    if streak >= ACHIEVEMENTS['streak_warrior']['threshold']:
        achievement_key = f"streak_warrior_{habit}"
        if achievement_key not in user_data["achievements"]:
            user_data["achievements"][achievement_key] = {
                "name": ACHIEVEMENTS['streak_warrior']['name'],
                "description": ACHIEVEMENTS['streak_warrior']['description'],
                "earned_date": datetime.now().strftime("%Y-%m-%d")
            }
            new_achievements.append(ACHIEVEMENTS['streak_warrior']['name'])

    if streak >= ACHIEVEMENTS['consistency_king']['threshold']:
        achievement_key = f"consistency_king_{habit}"
        if achievement_key not in user_data["achievements"]:
            user_data["achievements"][achievement_key] = {
                "name": ACHIEVEMENTS['consistency_king']['name'],
                "description": ACHIEVEMENTS['consistency_king']['description'],
                "earned_date": datetime.now().strftime("%Y-%m-%d")
            }
            new_achievements.append(ACHIEVEMENTS['consistency_king']['name'])

    # Check completion count achievements
    completion_dates = user_data["completed"].get(habit, [])
    if isinstance(completion_dates, list) and len(completion_dates) >= ACHIEVEMENTS['habit_master']['threshold']:
        achievement_key = f"habit_master_{habit}"
        if achievement_key not in user_data["achievements"]:
            user_data["achievements"][achievement_key] = {
                "name": ACHIEVEMENTS['habit_master']['name'],
                "description": ACHIEVEMENTS['habit_master']['description'],
                "earned_date": datetime.now().strftime("%Y-%m-%d")
            }
            new_achievements.append(ACHIEVEMENTS['habit_master']['name'])

    return new_achievements

async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    """Send reminder to a specific user."""
    job = context.job
    user_id, habits = job.data
    try:
        reminder_text = "⏰ Reminder! Don't forget your habits today:\n" + "\n".join(f"🔹 {h}" for h in habits)
        await context.bot.send_message(chat_id=user_id, text=reminder_text)
        logger.info(f"Sent reminder to user {user_id}")
    except Exception as e:
        logger.error(f"Failed to send reminder to user {user_id}: {str(e)}")

async def setup_user_reminder(context: ContextTypes.DEFAULT_TYPE, user_id: int, reminder_time: str, habits: list):
    """Setup or update reminder for a user."""
    job_name = f"reminder_{user_id}"

    # Remove existing jobs
    current_jobs = context.job_queue.get_jobs_by_name(job_name)
    for job in current_jobs:
        job.schedule_removal()

    # Add new reminder job
    try:
        hour, minute = map(int, reminder_time.split(':'))
        reminder_time_obj = time(hour=hour, minute=minute)
        context.job_queue.run_daily(
            send_reminder,
            time=reminder_time_obj,
            data=(user_id, habits),
            name=job_name
        )
    except ValueError as e:
        logger.error(f"Error setting up reminder: {str(e)}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start command handler."""
    await update.message.reply_text(
        "Welcome to Habit Tracker Bot! 🏆\n\n"
        "Available commands:\n"
        "/addhabit <habit> - Add a new habit\n"
        "/removehabit <habit> - Remove a habit\n"
        "/myhabits - List your habits\n"
        "/done <habit> - Mark a habit as done\n"
        "/stats - View your habit statistics\n"
        "/setreminder <HH:MM> - Set custom reminder time"
    )

async def add_habit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Add a new habit."""
    user_id = update.message.from_user.id

    if not context.args:
        await update.message.reply_text("⚠️ Usage: /addhabit <habit name>")
        return

    habit = " ".join(context.args)
    user_data = db.get(User.id == user_id)

    if user_data:
        if habit in user_data["habits"]:
            await update.message.reply_text("⚠️ This habit already exists!")
            return
        user_data["habits"].append(habit)
        if "completed" not in user_data:
            user_data["completed"] = {}
        user_data["completed"][habit] = []
        db.update(user_data, User.id == user_id)
    else:
        user_data = {
            "id": user_id,
            "habits": [habit],
            "completed": {habit: []},
            "reminder_time": "08:00",
            "achievements": {}
        }
        db.insert(user_data)
        await setup_user_reminder(context, user_id, "08:00", [habit])

    await update.message.reply_text(f"✅ Added new habit: '{habit}'")

async def remove_habit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove a habit."""
    user_id = update.message.from_user.id

    if not context.args:
        await update.message.reply_text("⚠️ Usage: /removehabit <habit name>")
        return

    habit = " ".join(context.args)
    user_data = db.get(User.id == user_id)

    if not user_data or habit not in user_data["habits"]:
        await update.message.reply_text("⚠️ Habit not found!")
        return

    user_data["habits"].remove(habit)
    if habit in user_data["completed"]:
        del user_data["completed"][habit]

    db.update(user_data, User.id == user_id)
    await update.message.reply_text(f"🗑️ Removed habit: '{habit}'")

async def list_habits(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all habits."""
    user_id = update.message.from_user.id
    user_data = db.get(User.id == user_id)

    if not user_data or not user_data["habits"]:
        await update.message.reply_text("📝 You don't have any habits yet. Add one with /addhabit")
        return

    habits_list = "\n".join(f"🔹 {h}" for h in user_data["habits"])
    await update.message.reply_text(f"📋 Your habits:\n{habits_list}")

async def mark_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mark a habit as completed and update streaks."""
    user_id = update.message.from_user.id

    if not context.args:
        await update.message.reply_text("Usage: /done <habit name>")
        return

    habit = " ".join(context.args)
    user_data = db.get(User.id == user_id)

    if not user_data or habit not in user_data["habits"]:
        await update.message.reply_text("⚠️ Habit not found!")
        return

    today = datetime.now().strftime("%Y-%m-%d")

    # Initialize completed data structure if needed
    if "completed" not in user_data:
        user_data["completed"] = {}
    if habit not in user_data["completed"]:
        user_data["completed"][habit] = []
    elif not isinstance(user_data["completed"][habit], list):
        # Ensure the completed data is always a list
        user_data["completed"][habit] = []
        logger.warning(f"Fixed non-list completed data for habit: {habit}")

    # Check if already completed today
    if today in user_data["completed"][habit]:
        await update.message.reply_text(f"⚠️ You've already completed '{habit}' today!")
        return

    # Add completion with extra validation
    try:
        user_data["completed"][habit].append(today)
        streak = calculate_streak(user_data["completed"][habit])
        new_achievements = check_achievements(user_data, habit, streak)
        db.update(user_data, User.id == user_id)

        response = f"🎉 Well done! You've completed '{habit}'\n"
        response += f"🔥 Current streak: {streak} days\n"

        if new_achievements:
            response += "\n🏆 New Achievements Unlocked!\n"
            for achievement in new_achievements:
                response += f"- {achievement}\n"

        await update.message.reply_text(response)
        logger.info(f"Successfully marked habit '{habit}' as done for user {user_id}")
    except Exception as e:
        logger.error(f"Error marking habit as done: {str(e)}")
        await update.message.reply_text("⚠️ An error occurred while marking the habit as done. Please try again.")

async def view_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """View habit statistics including streaks and achievements."""
    user_id = update.message.from_user.id
    user_data = db.get(User.id == user_id)

    if not user_data or not user_data.get("completed"):
        await update.message.reply_text("📊 No statistics available yet! Start tracking with /done")
        return

    stats = "📊 Your Habit Statistics:\n\n"

    for habit in user_data["habits"]:
        completion_dates = user_data["completed"].get(habit, [])
        if isinstance(completion_dates, list):
            completions = len(completion_dates)
            streak = calculate_streak(completion_dates)
            stats += f"🔹 {habit}:\n"
            stats += f"   ├ Total completions: {completions}\n"
            stats += f"   └ Current streak: {streak} days\n\n"

    if user_data.get("achievements"):
        stats += "🏆 Your Achievements:\n"
        achievements = user_data["achievements"]
        for achievement in achievements.values():
            stats += f"✨ {achievement['name']}\n"
            stats += f"   └ Earned on: {achievement['earned_date']}\n"

    await update.message.reply_text(stats)

async def set_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Set custom reminder time."""
    user_id = update.message.from_user.id

    if not context.args or len(context.args) != 1:
        await update.message.reply_text("⚠️ Usage: /setreminder HH:MM (24-hour format)")
        return

    try:
        time_str = context.args[0]
        time_obj = datetime.strptime(time_str, "%H:%M").strftime("%H:%M")
        user_data = db.get(User.id == user_id)

        if not user_data:
            await update.message.reply_text("⚠️ Please add some habits first!")
            return

        user_data["reminder_time"] = time_obj
        db.update(user_data, User.id == user_id)

        await setup_user_reminder(
            context,
            user_id,
            time_obj,
            user_data["habits"]
        )

        await update.message.reply_text(f"⏰ Reminder time set to {time_obj}")
    except ValueError:
        await update.message.reply_text("⚠️ Invalid time format! Use HH:MM (24-hour format)")

async def main():
    """Start the bot."""
    try:
        # Initialize bot
        app = Application.builder().token(TOKEN).build()

        # Add command handlers
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("addhabit", add_habit))
        app.add_handler(CommandHandler("removehabit", remove_habit))
        app.add_handler(CommandHandler("myhabits", list_habits))
        app.add_handler(CommandHandler("done", mark_done))
        app.add_handler(CommandHandler("stats", view_stats))
        app.add_handler(CommandHandler("setreminder", set_reminder))

        # Log startup
        logger.info("🤖 Habit Tracking Bot is running!")

        # Start polling
        await app.run_polling(drop_pending_updates=True)

    except Exception as e:
        logger.error(f"Error running bot: {str(e)}")
        if scheduler.running:
            scheduler.shutdown()

if __name__ == "__main__":
    # Handle event loop conflicts in Replit environment
    nest_asyncio.apply()
    import asyncio
    asyncio.run(main())