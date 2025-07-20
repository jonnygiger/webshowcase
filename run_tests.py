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
    # Create a TestSuite
    suite = unittest.TestSuite()

    # Add all test classes to the suite
    suite.addTest(unittest.makeSuite(TestAchievementLogic))
    suite.addTest(unittest.makeSuite(TestApi))
    suite.addTest(unittest.makeSuite(TestApiEdgeCases))
    suite.addTest(unittest.makeSuite(TestApp))
    suite.addTest(unittest.makeSuite(AppTestCase))
    suite.addTest(unittest.makeSuite(TestChat))
    suite.addTest(unittest.makeSuite(TestChatApi))
    suite.addTest(unittest.makeSuite(TestChatModel))
    suite.addTest(unittest.makeSuite(TestCollaborativeEditing))
    suite.addTest(unittest.makeSuite(TestCommentApi))
    suite.addTest(unittest.makeSuite(TestContentManagement))
    suite.addTest(unittest.makeSuite(TestDiscoverPage))
    suite.addTest(unittest.makeSuite(TestEventRendering))
    suite.addTest(unittest.makeSuite(TestFileSharing))
    suite.addTest(unittest.makeSuite(TestFriendPostNotifications))
    suite.addTest(unittest.makeSuite(TestGroupModel))
    suite.addTest(unittest.makeSuite(TestLikeNotifications))
    # suite.addTest(unittest.makeSuite(TestLiveActivityFeed))
    suite.addTest(unittest.makeSuite(TestUserModel))
    suite.addTest(unittest.makeSuite(TestPostModel))
    suite.addTest(unittest.makeSuite(TestFriendshipModel))
    suite.addTest(unittest.makeSuite(TestUserBlockModel))
    suite.addTest(unittest.makeSuite(TestSeriesModel))
    suite.addTest(unittest.makeSuite(TestEventRSVPModel))
    suite.addTest(unittest.makeSuite(TestPollVoteModel))
    suite.addTest(unittest.makeSuite(TestOnThisDay))
    suite.addTest(unittest.makeSuite(TestPersonalizedFeedApi))
    suite.addTest(unittest.makeSuite(TestPollApi))
    # suite.addTest(unittest.makeSuite(TestRealtimePostNotifications))
    suite.addTest(unittest.makeSuite(TestRecommendationApi))
    suite.addTest(unittest.makeSuite(TestRecommendations))
    suite.addTest(unittest.makeSuite(TestSanity))
    suite.addTest(unittest.makeSuite(TestSeriesFeature))
    suite.addTest(unittest.makeSuite(TestTrendingHashtags))
    suite.addTest(unittest.makeSuite(TestUserFeedApi))
    suite.addTest(unittest.makeSuite(TestUserInteractions))
    suite.addTest(unittest.makeSuite(TestUserModelIsolated))
    suite.addTest(unittest.makeSuite(TestUserStatsApi))
    suite.addTest(unittest.makeSuite(TestUserStatus))
    suite.addTest(unittest.makeSuite(TestUtils))
    suite.addTest(unittest.makeSuite(TestViews))

    # Run the tests
    runner = unittest.TextTestRunner()
    runner.run(suite)
