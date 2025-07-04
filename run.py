import os
import sys # For sys.exit if needed, and to check paths
from dotenv import load_dotenv # Optional: for loading .env files

# Optional: Load environment variables from .env file
load_dotenv()

# Ensure the social_app package is discoverable if run.py is at the project root
# and social_app is a directory in the same root.
# This might not be strictly necessary if PYTHONPATH is set correctly or if using a virtual environment
# where the package is installed in editable mode (pip install -e .).
# However, for direct execution (python run.py), this can help.
project_root = os.path.abspath(os.path.dirname(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from social_app import create_app, db, scheduler  # Import create_app, db, and scheduler
from social_app.models.db_models import Achievement  # For seed_achievements_command
from social_app.core.utils import generate_activity_summary # For scheduler job
from social_app.services.recommendations_service import update_trending_hashtags # For scheduler job

# Create the Flask app instance using the factory
app = create_app(os.getenv('FLASK_CONFIG') or 'default')

# CLI commands
@app.cli.command("seed-achievements")
def seed_achievements_cli():
    """CLI command to seed achievements."""
    # Copied from original app.py, adjusted for app context and imports
    with app.app_context():
        predefined_achievements = [
            {"name": "First Post", "description": "Created your first blog post.", "icon_url": "[POST_ICON]", "criteria_type": "num_posts", "criteria_value": 1},
            {"name": "Say What?!", "description": "Posted your first comment.", "icon_url": "[COMMENT_ICON]", "criteria_type": "num_comments_given", "criteria_value": 1},
            {"name": "Post Prolific", "description": "Published 10 blog posts.", "icon_url": "[PROLIFIC_POST_ICON]", "criteria_type": "num_posts", "criteria_value": 10},
            {"name": "Master Communicator", "description": "Wrote 25 insightful comments.", "icon_url": "[PROLIFIC_COMMENT_ICON]", "criteria_type": "num_comments_given", "criteria_value": 25},
            {"name": "Friendly", "description": "Made your first friend.", "icon_url": "[FRIEND_ICON]", "criteria_type": "num_friends", "criteria_value": 1},
            {"name": "Well-Connected", "description": "Built a network of 5 friends.", "icon_url": "[NETWORK_ICON]", "criteria_type": "num_friends", "criteria_value": 5},
            {"name": "Event Enthusiast", "description": "Organized your first event.", "icon_url": "[EVENT_ORGANIZER_ICON]", "criteria_type": "num_events_created", "criteria_value": 1},
            {"name": "Pollster", "description": "Created your first poll.", "icon_url": "[POLL_CREATOR_ICON]", "criteria_type": "num_polls_created", "criteria_value": 1},
            {"name": "Opinion Leader", "description": "Voted in 5 different polls.", "icon_url": "[VOTER_ICON]", "criteria_type": "num_polls_voted", "criteria_value": 5},
            {"name": "Rising Star", "description": "Received 10 likes across all your posts.", "icon_url": "[LIKES_RECEIVED_ICON]", "criteria_type": "num_likes_received", "criteria_value": 10},
            {"name": "Community Contributor", "description": "Joined your first group.", "icon_url": "[GROUP_JOIN_ICON]", "criteria_type": "num_groups_joined", "criteria_value": 1},
            {"name": "Bookworm", "description": "Bookmarked 5 posts.", "icon_url": "[BOOKMARK_ICON]", "criteria_type": "num_bookmarks_created", "criteria_value": 5},
        ]
        achievements_added_count = 0
        achievements_skipped_count = 0
        for ach_data in predefined_achievements:
            existing_achievement = Achievement.query.filter_by(name=ach_data["name"]).first()
            if not existing_achievement:
                achievement = Achievement(**ach_data)
                db.session.add(achievement)
                achievements_added_count += 1
                print(f"Adding achievement: {ach_data['name']}")
            else:
                achievements_skipped_count += 1
        if achievements_added_count > 0:
            try:
                db.session.commit()
                print(f"Successfully added {achievements_added_count} new achievements.")
            except Exception as e:
                db.session.rollback()
                print(f"Error committing new achievements: {e}")
        if achievements_skipped_count > 0:
            print(f"Skipped {achievements_skipped_count} achievements (already exist).")
        print("Achievement seeding process complete.")

# Main execution block
if __name__ == "__main__":
    # Scheduler setup (moved from app.py)
    # The scheduler should be started only in the main process, not the reloader's.
    # app.config.get('TESTING', False) is True if Flask is in testing mode.
    if not app.config.get("TESTING", False):
        if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
            if not scheduler.running:
                # Add jobs to the scheduler
                # It's important that these functions are called within an app context.
                # The scheduler itself doesn't automatically provide one.
                # One way is to wrap them in a function that creates an app context.
                def run_generate_activity_summary():
                    with app.app_context():
                        generate_activity_summary()

                def run_update_trending_hashtags():
                    with app.app_context():
                        update_trending_hashtags()

                scheduler.add_job(func=run_generate_activity_summary, trigger="interval", minutes=1, id="generate_activity_summary_job")
                scheduler.add_job(func=run_update_trending_hashtags, trigger="interval", minutes=10, id="update_trending_hashtags_job")

                try:
                    scheduler.start()
                    app.logger.info("Scheduler started with jobs.")
                except Exception as e:
                    app.logger.error(f"Error starting scheduler: {e}")

                # Register scheduler shutdown
                import atexit
                atexit.register(lambda: scheduler.shutdown() if scheduler.running else None)
                app.logger.info("Scheduler shutdown registered via atexit.")
            else:
                app.logger.info("Scheduler already running.")
        else:
            app.logger.info("Scheduler not started (Werkzeug reloader process or debug mode without WERKZEUG_RUN_MAIN).")
    else:
        app.logger.info("Scheduler not started (app is in TESTING mode).")

    # Use the socketio instance imported from social_app via create_app()
    # The socketio instance is initialized and configured in create_app()
    # We need to get it from the app object if it's stored there, or import it if it's global in social_app
    # Assuming socketio is available from social_app package after create_app() configures it.
    from social_app import socketio as global_socketio # If socketio is a global in social_app __init__

    # Fallback or direct attribute if socketio is attached to app by create_app
    # app_socketio = getattr(app, 'socketio', global_socketio)

    # The `socketio.run(app, ...)` method should be called with the app instance.
    # The `socketio` object here should be the one that all extensions and blueprints were registered with.
    # This is typically the one initialized in `social_app/__init__.py`.
    app_port = int(os.environ.get("PORT", 5000))
    global_socketio.run(app, host='0.0.0.0', port=app_port, debug=app.debug, allow_unsafe_werkzeug=True if app.debug else False)
    # Note: allow_unsafe_werkzeug=True is often needed for SocketIO with Flask's dev server,
    # but should be False or omitted in production. Set based on app.debug.

# Comments for clarity:
# - `create_app` is the application factory.
# - `db` is the SQLAlchemy instance, used by `seed_achievements_cli`.
# - `scheduler` is the APScheduler instance.
# - Models like `Achievement` are imported for CLI commands.
# - Utility functions like `generate_activity_summary` are imported for scheduler jobs.
# - `socketio` instance needs to be correctly referenced for `socketio.run()`.
#   If `create_app` configures a global `socketio` object in `social_app/__init__.py`, that's imported.
#   Or if `create_app` returns it or attaches it to `app`, it's accessed that way.
#   The example assumes `social_app.socketio` is the configured instance.
# - `allow_unsafe_werkzeug=True` is used for development with SocketIO and Werkzeug's reloader.
#   It should ideally be conditional on `app.debug`.
# - Added `host='0.0.0.0'` to make it accessible externally if needed (common for dev).
# - Added `atexit` registration for scheduler shutdown.
# - Added wrappers for scheduler jobs to ensure they run with app context.
# - Added dotenv load for optional .env file configuration.
# - Added sys.path modification for better package discovery in direct execution scenarios.
# - `FLASK_CONFIG` environment variable can be used to specify a config class for `create_app`.
# - Made `allow_unsafe_werkzeug` conditional on `app.debug`.
# - Ensured scheduler jobs have unique IDs to prevent issues if added multiple times (though `if not scheduler.running` should prevent this).
# - Corrected import for socketio in `if __name__ == "__main__":` to be `from social_app import socketio as global_socketio` assuming it's made available that way.
#   This is a common pattern: extensions are initialized in `social_app/__init__.py` and then imported by `run.py`.
# - The `generate_activity_summary` and `update_trending_hashtags` are now wrapped to ensure app context.
# - `Achievement` model import for `seed_achievements_cli` is from `social_app.models.db_models`.
# - `db` and `scheduler` are imported from `social_app` (assuming they are initialized there globally or made available).
# - `sys.path.insert(0, project_root)` makes `social_app` importable.
# - `global_socketio.run(...)` is used, assuming `socketio` is the instance from `social_app`.
# - `app.logger` is used for logging within the `if __name__ == "__main__"` block.
# - `atexit` logic for scheduler shutdown checks `if scheduler.running`.
# - Simplified some scheduler logging.
# - Ensured `Achievement` model import is specific for the CLI command.
# - Ensured `generate_activity_summary` and `update_trending_hashtags` imports are correct.
```
