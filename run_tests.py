import unittest

# Import all test classes
from tests.test_achievement_logic import TestAchievementLogic
from tests.test_api import TestApi
from tests.test_api_edge_cases import TestApiEdgeCases
from tests.test_app import TestApp
from tests.test_base import AppTestCase
from tests.test_chat import TestChat
from tests.test_chat_api import TestChatAPI as TestChatApi
from tests.test_chat_model import TestChatModel
from tests.test_collaborative_editing import TestCollaborativeEditing
from tests.test_comment_api import TestCommentAPI as TestCommentApi
from tests.test_content_management import TestContentManagement
from tests.test_discover_page import TestDiscoverPageViews as TestDiscoverPage
from tests.test_event_rendering import TestEventRendering
from tests.test_file_sharing import TestFileSharing
from tests.test_friend_post_notifications import TestFriendPostNotifications
from tests.test_group_model import TestGroupModel
from tests.test_like_notifications import TestLikeNotifications
# from tests.test_live_activity_feed import TestLiveActivityFeed
from tests.test_models import TestUserModel, TestPostModel, TestFriendshipModel, TestUserBlockModel, TestSeriesModel, TestEventRSVPModel, TestPollVoteModel
from tests.test_on_this_day import TestOnThisDay
from tests.test_personalized_feed_api import TestPersonalizedFeedAPI as TestPersonalizedFeedApi
from tests.test_poll_api import TestPollAPI as TestPollApi
# from tests.test_realtime_post_notifications import TestRealtimePostNotifications
from tests.test_recommendation_api import TestRecommendationAPI as TestRecommendationApi
from tests.test_recommendations import TestRecommendations
from tests.test_sanity import TestSanity
from tests.test_series_feature import TestSeriesFeature
from tests.test_trending_hashtags import TestTrendingHashtags
from tests.test_user_feed_api import TestUserFeedAPI as TestUserFeedApi
from tests.test_user_interactions import TestUserInteractions
from tests.test_user_model_isolated import TestUserModelIsolated
from tests.test_user_stats_api import TestUserStatsAPI as TestUserStatsApi
from tests.test_user_status import TestUserStatus
from tests.test_utils import TestUtils
from tests.test_views import TestViews

if __name__ == '__main__':
    # Create a TestLoader
    loader = unittest.TestLoader()

    # Create a TestSuite
    suite = unittest.TestSuite()

    # Add all test classes to the suite using the loader
    suite.addTest(loader.loadTestsFromTestCase(TestAchievementLogic))
    suite.addTest(loader.loadTestsFromTestCase(TestApi))
    suite.addTest(loader.loadTestsFromTestCase(TestApiEdgeCases))
    suite.addTest(loader.loadTestsFromTestCase(TestApp))
    suite.addTest(loader.loadTestsFromTestCase(AppTestCase))
    suite.addTest(loader.loadTestsFromTestCase(TestChat))
    suite.addTest(loader.loadTestsFromTestCase(TestChatApi))
    suite.addTest(loader.loadTestsFromTestCase(TestChatModel))
    suite.addTest(loader.loadTestsFromTestCase(TestCollaborativeEditing))
    suite.addTest(loader.loadTestsFromTestCase(TestCommentApi))
    suite.addTest(loader.loadTestsFromTestCase(TestContentManagement))
    suite.addTest(loader.loadTestsFromTestCase(TestDiscoverPage))
    suite.addTest(loader.loadTestsFromTestCase(TestEventRendering))
    suite.addTest(loader.loadTestsFromTestCase(TestFileSharing))
    suite.addTest(loader.loadTestsFromTestCase(TestFriendPostNotifications))
    suite.addTest(loader.loadTestsFromTestCase(TestGroupModel))
    suite.addTest(loader.loadTestsFromTestCase(TestLikeNotifications))
    # suite.addTest(loader.loadTestsFromTestCase(TestLiveActivityFeed))
    suite.addTest(loader.loadTestsFromTestCase(TestUserModel))
    suite.addTest(loader.loadTestsFromTestCase(TestPostModel))
    suite.addTest(loader.loadTestsFromTestCase(TestFriendshipModel))
    suite.addTest(loader.loadTestsFromTestCase(TestUserBlockModel))
    suite.addTest(loader.loadTestsFromTestCase(TestSeriesModel))
    suite.addTest(loader.loadTestsFromTestCase(TestEventRSVPModel))
    suite.addTest(loader.loadTestsFromTestCase(TestPollVoteModel))
    suite.addTest(loader.loadTestsFromTestCase(TestOnThisDay))
    suite.addTest(loader.loadTestsFromTestCase(TestPersonalizedFeedApi))
    suite.addTest(loader.loadTestsFromTestCase(TestPollApi))
    # suite.addTest(loader.loadTestsFromTestCase(TestRealtimePostNotifications))
    suite.addTest(loader.loadTestsFromTestCase(TestRecommendationApi))
    suite.addTest(loader.loadTestsFromTestCase(TestRecommendations))
    suite.addTest(loader.loadTestsFromTestCase(TestSanity))
    suite.addTest(loader.loadTestsFromTestCase(TestSeriesFeature))
    suite.addTest(loader.loadTestsFromTestCase(TestTrendingHashtags))
    suite.addTest(loader.loadTestsFromTestCase(TestUserFeedApi))
    suite.addTest(loader.loadTestsFromTestCase(TestUserInteractions))
    suite.addTest(loader.loadTestsFromTestCase(TestUserModelIsolated))
    suite.addTest(loader.loadTestsFromTestCase(TestUserStatsApi))
    suite.addTest(loader.loadTestsFromTestCase(TestUserStatus))
    suite.addTest(loader.loadTestsFromTestCase(TestUtils))
    suite.addTest(loader.loadTestsFromTestCase(TestViews))

    # Run the tests
    runner = unittest.TextTestRunner()
    runner.run(suite)
