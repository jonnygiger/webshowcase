import os
import sys
from dotenv import load_dotenv

load_dotenv()

project_root = os.path.abspath(os.path.dirname(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from social_app import create_app, db, scheduler
from social_app.models.db_models import Achievement
from social_app.core.utils import generate_activity_summary
from social_app.services.recommendations_service import update_trending_hashtags

app = create_app(os.getenv('FLASK_CONFIG') or 'default')

@app.cli.command("seed-achievements")
def seed_achievements_cli():
    """CLI command to seed achievements."""
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

if __name__ == "__main__":
    if not app.config.get("TESTING", False):
        if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
            if not scheduler.running:
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

                import atexit
                atexit.register(lambda: scheduler.shutdown() if scheduler.running else None)
                app.logger.info("Scheduler shutdown registered via atexit.")
            else:
                app.logger.info("Scheduler already running.")
        else:
            app.logger.info("Scheduler not started (Werkzeug reloader process or debug mode without WERKZEUG_RUN_MAIN).")
    else:
        app.logger.info("Scheduler not started (app is in TESTING mode).")

    from social_app import socketio as global_socketio

    app_port = int(os.environ.get("PORT", 5000))
    global_socketio.run(app, host='0.0.0.0', port=app_port, debug=app.debug, allow_unsafe_werkzeug=True if app.debug else False)
