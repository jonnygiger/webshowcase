from flask import current_app, url_for
import queue

new_post_sse_queues = []


def broadcast_new_post(post_data):
    """
    Broadcasts new post data to all connected SSE clients.
    This function is moved here to break a circular import between app.py and api.py.
    """
    logger = current_app.logger

    post_data_with_url = post_data.copy()

    if "id" in post_data_with_url:
        try:
            post_data_with_url["url"] = url_for(
                "core.view_post", post_id=post_data_with_url["id"], _external=True
            )
        except Exception as e:
            logger.error(
                f"Error generating URL for post ID {post_data_with_url.get('id')} in broadcast_new_post: {e}. Sending notification without URL."
            )
            if "url" in post_data_with_url:
                del post_data_with_url["url"]
    else:
        logger.warning(
            "Post data missing 'id' field in broadcast_new_post, cannot generate URL for SSE notification. Sending notification without URL."
        )

    if not new_post_sse_queues:
        logger.warning(
            "No SSE queues in new_post_sse_queues to send new post notifications to."
        )
        return

    logger.info(
        f"Broadcasting new post from notifications.py: ID {post_data_with_url.get('id')}, Title: {post_data_with_url.get('title')} to {len(new_post_sse_queues)} clients. URL: {post_data_with_url.get('url', 'N/A')}"
    )
    for q_item in new_post_sse_queues:
        try:
            q_item.put(post_data_with_url)
        except Exception as e:
            logger.error(
                f"Error putting post_data_with_url into a queue in broadcast_new_post: {e}"
            )
