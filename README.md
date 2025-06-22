# Flask App

This is a basic Flask application.

## Setup

1. Clone the repository:
   ```bash
   git clone <repository_url>
   ```
2. Navigate to the project directory:
   ```bash
   cd <project_directory>
   ```
3. Create a virtual environment:
   ```bash
   python -m venv venv
   ```
4. Activate the virtual environment:
   - On Windows:
     ```bash
     venv\Scripts\activate
     ```
   - On macOS and Linux:
     ```bash
     source venv/bin/activate
     ```
5. Install the dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Running the App

1. Run the Flask development server:
   ```bash
   python app.py
   ```
2. Open your web browser and go to `http://127.0.0.1:5000/` to see the app in action.

## Features

### Friendship System

The application now includes a friendship system, allowing users to connect with each other.

*   **Functionality:**
    *   Users can send friend requests to other users.
    *   Users can view, accept, or reject incoming friend requests.
    *   Users have a friends list, visible on their profile and on a dedicated friends page.
    *   Users can remove existing friends.

*   **Models:**
    *   A `Friendship` model (`friendship` table) was introduced to manage the relationships, storing the sender (`user_id`), receiver (`friend_id`), status (`pending`, `accepted`, `rejected`), and `timestamp` of the request/friendship.
    *   The `User` model was updated with `sent_friend_requests` and `received_friend_requests` relationships to `Friendship`, and a helper method `get_friends()` to retrieve a user's accepted friends.

*   **Key API Endpoints & UI Integration:**
    *   **Sending a Request:**
        *   `POST /user/<target_user_id>/send_friend_request`: Button available on other users' profiles if not already friends or request pending.
    *   **Managing Received Requests:**
        *   `GET /friend_requests`: Dedicated page accessible from the navigation bar (for logged-in users) listing all pending incoming requests.
        *   `POST /friend_request/<request_id>/accept`: "Accept" button on the "Friend Requests" page and directly on the sender's profile if a request is pending.
        *   `POST /friend_request/<request_id>/reject`: "Reject" button on the "Friend Requests" page and directly on the sender's profile if a request is pending.
    *   **Managing Existing Friends:**
        *   `POST /user/<friend_user_id>/remove_friend`: "Remove Friend" button on a friend's profile page and on the current user's own friends list page.
    *   **Viewing Friends:**
        *   `GET /user/<username>/friends`: Publicly accessible page listing a user's friends. Also linked from user profiles.
    *   **Profile Page Integration:** User profiles dynamically display the current friendship status and relevant action buttons (Send Request, Accept/Reject, Remove Friend, View Pending Status).

### User Activity Feed

The application now tracks and displays user activities, providing insight into recent actions within the platform.

*   **Functionality**:
    *   Tracks user actions such as creating new posts, adding comments to posts, creating new events, and liking posts.
    *   Each user has a dedicated activity feed page that shows their recent activities in chronological order (newest first).
    *   Activities listed in the feed include a description of the action, a preview of the content (e.g., post title, comment snippet, liked post preview), and a direct link to the relevant content (e.g., the post or event page).
*   **Access**:
    *   A link to "View Activity Feed" is available on each user's profile page (`/user/<username>`), allowing logged-in users to view the activity of others.
*   **Models**:
    *   A `UserActivity` model was introduced to store activity records, including `user_id`, `activity_type`, `related_id` (e.g., post ID, event ID), `content_preview`, `link`, and `timestamp`.
    *   The `User` model has an `activities` relationship to easily fetch all activities for a user.

### Live Activity Feed

The application features a real-time Live Activity Feed, providing users with immediate updates on their friends' activities within the platform.

*   **Functionality**:
    *   Displays a continuously updating stream of recent actions performed by a user's friends.
    *   Supported activities include new posts, comments on posts, likes on posts, and new friendships formed (when a friend request is accepted by one of the user's friends, or when the user's friend accepts a request).
*   **Benefits**:
    *   Keeps users engaged by showing them what their connections are up to in real-time.
    *   Reduces the need to manually check profiles or refresh pages to see new interactions.
*   **How it Works**:
    *   Utilizes WebSockets via the Flask-SocketIO extension for instant communication between the server and connected clients.
    *   When a user performs a relevant action, the server logs the activity and then broadcasts an event to the friends of that user.
    *   Client-side JavaScript listens for these events and dynamically prepends new activity items to the feed.
*   **Access**:
    *   Logged-in users can access their personalized Live Activity Feed by navigating to the `/live_feed` URL.
    *   (A direct link in the navigation bar could be added in future enhancements for easier access).

### User Authentication

This application now features a user authentication system.

*   **Login/Logout**: Users can log in with their credentials to access protected parts of the site. A logout option is available to end the session.
*   **Protected Routes**: The following routes require users to be logged in:
    *   To-Do List (`/todo` and `/todo/clear`)
    *   Image Upload (`/gallery/upload`)
    If an unauthenticated user attempts to access these pages, they will be redirected to the login page.
*   **Demo User**: For demonstration purposes, a default user is available:
    *   **Username**: `demo`
    *   **Password**: `password123`
*   **Navigation**: The navigation bar will dynamically show "Login" or "Logout" links based on the current user's session status. When logged in, it will also display the username.

### User Registration

*   **Route**: `/register`
*   **Functionality**:
    *   Users can create a new account by providing a unique username and a password.
    *   The system checks if a username already exists to prevent duplicates.
    *   Upon successful registration, users are redirected to the login page (`/login`) to sign in with their new credentials.
    *   The "Register" link is available in the navigation bar only for users who are not logged in.

### Enhanced To-Do List

The application features a robust, user-specific To-Do list backed by a database, allowing users to manage their tasks effectively. Access to the To-Do list requires users to be logged in.

*   **Route:** `/todo`
*   **Core Functionalities:**
    *   **Task Creation**: Users can create new tasks by providing a description. Optional fields include a due date and a priority level (Low, Medium, High).
    *   **Task Display**: Each task displays its description, due date (if set), priority (if set), and completion status.
    *   **Mark as Complete/Incomplete**: Tasks can be toggled between "Pending" and "Done". Completed tasks are visually differentiated (e.g., strikethrough).
    *   **Task Editing**: Existing tasks can be modified. Users can update the task description, due date, and priority through an edit form.
    *   **Task Deletion**: Users can delete individual tasks.
    *   **Clear All Tasks**: A feature to delete all tasks belonging to the logged-in user is available via the `/todo/clear` route.
*   **Sorting**:
    *   The To-Do list can be sorted by various criteria:
        *   Due Date (ascending or descending)
        *   Priority (ascending or descending, logically ordering High > Medium > Low)
        *   Completion Status (ascending or descending)
    *   Sorting options are available as links on the `/todo` page.
*   **User-Specific**: All tasks are private and associated with the logged-in user.

### Image Gallery

The application now includes a dynamic image gallery to showcase more Flask functionalities.

*   **Purpose:** Allows users to upload images and view them in a gallery format.
*   **Flask Functionalities Demonstrated:**
    *   **File Uploads:** Handling multipart/form-data requests for image uploads.
    *   **File Validation:** Checking for allowed file extensions.
    *   **Secure Filenames:** Using `werkzeug.utils.secure_filename` to sanitize filenames.
    *   **Static File Serving (Dynamic):** Serving uploaded images from a designated `uploads` folder using `send_from_directory`.
    *   **Dynamic Routing:** Using routes like `/uploads/<filename>` to serve specific files.
    *   **Templating:** Displaying images dynamically in `gallery.html` using loops and conditional statements.
    *   **Flash Messaging:** Providing user feedback for upload success or errors.
    *   **Configuration:** Using `app.config` for settings like `UPLOAD_FOLDER` and `ALLOWED_EXTENSIONS`.

*   **Routes & Usage:**
    *   **/gallery/upload**:
        *   `GET`: Displays a form to choose and upload an image.
        *   `POST`: Processes the uploaded image. Validates and saves it if it's an allowed type (PNG, JPG, JPEG, GIF). Shows success or error messages.
    *   **/gallery**:
        *   `GET`: Displays all successfully uploaded images in a grid. If no images are present, it shows a message.
    *   **/uploads/&lt;filename&gt;**:
        *   `GET`: Serves the actual image file. This URL is used in `<img>` tags in the gallery.

*   **Storage:**
    *   Uploaded images are stored in the `uploads/` directory in the project root. This directory is included in `.gitignore`.

### Blog Feature

This application now includes a fully functional blog where users can share their thoughts. This feature demonstrates common patterns in web applications like CRUD operations and content management.

*   **Purpose**: Allows authenticated users to create, edit, and delete their own blog posts. All visitors can read blog posts.
*   **Flask Functionalities Demonstrated**:
    *   **CRUD Operations**: Full Create, Read, Update, and Delete lifecycle for blog posts.
    *   **Dynamic Routing**: Using route parameters like `/blog/post/<int:post_id>` to display specific content.
    *   **User Authentication & Authorization**:
        *   Creating, editing, and deleting posts require users to be logged in.
        *   Users can only edit or delete posts they have authored.
    *   **Templating**: Several new templates (`blog.html`, `create_post.html`, `view_post.html`, `edit_post.html`) extend `base.html` to provide views for blog functionalities.
    *   **Form Handling**: Processing form submissions for creating and editing posts.
    *   **Session Management**: Tracking the logged-in user to associate posts with authors and for authorization checks.
    *   **In-Memory Data Storage**: Blog posts are stored in a Python list of dictionaries within the application for simplicity.

*   **Routes & Usage**:
    *   `/blog`: (GET) Displays a list of all blog posts, with the newest posts appearing first.
    *   `/blog/create`: (GET/POST)
        *   Requires login.
        *   `GET`: Shows a form to write a new blog post.
        *   `POST`: Submits the new blog post.
    *   `/blog/post/<int:post_id>`: (GET) Displays the full content of a specific blog post.
    *   `/blog/edit/<int:post_id>`: (GET/POST)
        *   Requires login and that the logged-in user is the author of the post.
        *   `GET`: Shows a form pre-filled with the post's title and content for editing.
        *   `POST`: Updates the specified blog post.
    *   `/blog/delete/<int:post_id>`: (POST)
        *   Requires login and that the logged-in user is the author of the post.
        *   Deletes the specified blog post after a confirmation.

### User Profile Page

This feature provides a dedicated page for each user, showcasing their activity and contributions to the application.

*   **Purpose**: To display user-specific information, including their blog posts and uploaded images, creating a personalized space for each user.
*   **Route**: `/user/<username>` (e.g., `/user/demo`)
*   **Information Displayed**:
    *   **Username**: The name of the user whose profile is being viewed.
    *   **User's Blog Posts**:
        *   A list of blog posts authored by the user.
        *   Each post title links to the full post view (`/blog/post/<id>`).
        *   The timestamp of when the post was created is also displayed.
        *   If the user has not created any posts, a message like "This user has not created any posts yet." is shown.
    *   **User's Uploaded Images**:
        *   A gallery of images uploaded by the user.
        *   Images are displayed in a grid format.
        *   If the user has not uploaded any images, a message like "This user has not uploaded any images yet." is shown.
*   **Flask Functionalities Demonstrated**:
    *   **Dynamic Content Generation**: The content of the profile page is dynamically generated based on the `username` parameter in the URL and the associated user data.
    *   **Data Aggregation**: Information (blog posts, uploaded images) is filtered and aggregated specifically for the viewed user.
    *   **User-Specific Views**: Enhances the application by providing views tailored to individual users, improving personalization.
    *   **Data Structures for User Association**: User data (like associated image filenames and blog post IDs) is managed within the `users` dictionary in `app.py`.

### Profile Pictures

Users can now personalize their profiles by uploading a profile picture.

*   **Functionality**:
    *   Allows logged-in users to upload an image file (PNG, JPG, JPEG, GIF) to be used as their profile picture.
    *   Uploaded pictures are displayed on the user's profile page.
    *   The user's profile picture (or a default image if none is uploaded) helps identify them, and is visible on their profile page. A link to "Change Profile Picture" is available on their own profile page.
*   **Usage**:
    *   To upload or change a profile picture, navigate to your "My Profile" page (link available in the navigation bar when logged in).
    *   Click the "Change Profile Picture" button.
    *   Alternatively, a direct link "Change Profile Picture" is available in the navigation bar for logged-in users.
    *   On the upload page, choose an image file and submit.
*   **Storage**: Profile pictures are stored in the `static/profile_pics/` directory. The specific path for each user is saved in the database.

### User Profile Management

The application provides comprehensive user profiles with options for personalization and management.

*   **Viewing Profiles**:
    *   Each user has a public profile page accessible via `/user/<username>`.
    *   This page displays user-specific information, creating a personalized space.
*   **Information Displayed**:
    *   **Username**: The primary identifier.
    *   **Email**: The user's registered email address (visible on their own profile, potentially to others based on privacy settings - currently displayed).
    *   **Bio**: A short biography or description that the user can set.
    *   **Profile Picture**: The user's uploaded avatar. A default image is shown if none is uploaded.
    *   **Created Posts**: A list of blog posts authored by the user, with links to each post.
    *   **Organized Events**: A list of events organized by the user, with links to each event.
    *   **Shared Posts**: Posts from other users that this user has shared on their own profile.
    *   **Gallery Images**: Images uploaded by the user to their personal gallery.
    *   **Joined Groups**: A list of groups the user is a member of.
*   **Editing Profiles**:
    *   Logged-in users can edit their own profile information via the `/profile/edit` route, accessible from their profile page.
    *   **Editable Fields**:
        *   Username (must be unique)
        *   Email (must be unique)
        *   Bio
    *   Changes are validated (e.g., for uniqueness of username/email) before being saved.

### User Status / Mood Updates

Users can share their current status or mood with a short message and/or an emoji.

*   **Functionality**:
    *   Users can set a status update consisting of a text message (up to 280 characters) and/or a single emoji.
    *   The latest status update is displayed prominently on their profile page, including when the status was set.
    *   This feature is available only to logged-in users.
    *   The form to set or update the status is conveniently located on the user's own profile page.
*   **Implementation**:
    *   A `UserStatus` model (`user_status` table) stores the status updates, linking to the `User` model and including fields for `status_text`, `emoji`, and a `timestamp`.
    *   A new route `/set_status` (POST) handles the creation of new status updates.
    *   The `User` model has a helper method `get_current_status()` to retrieve the most recent status for display.

### User Achievements/Badges

To make the platform more engaging, a User Achievements/Badges system has been implemented. Users can earn badges for performing various actions and reaching certain milestones.

*   **How it Works**:
    *   Achievements are automatically awarded when a user's actions meet predefined criteria (e.g., number of posts created, friends made, comments written).
    *   The system periodically checks for new achievements earned by users after relevant actions.

*   **Viewing Achievements**:
    *   **User Profile**: Earned achievements are displayed as badges on each user's profile page (`/user/<username>`). Hovering over a badge shows its description and award date.
    *   **Dedicated Achievements Page**: Users can view a more detailed list of their achievements, as well as all available achievements in the system (marked as earned or not earned), on their personal achievements page, accessible via a link on their profile or by navigating to `/user/<username>/achievements`.

*   **Example Achievements**:
    Some of the achievements you can earn include:
    *   **First Post**: For creating your first blog post.
    *   **Say What?!**: For posting your first comment.
    *   **Post Prolific**: For publishing 10 blog posts.
    *   **Master Communicator**: For writing 25 insightful comments.
    *   **Friendly**: For making your first friend.
    *   **Well-Connected**: For building a network of 5 friends.
    *   **Event Enthusiast**: For organizing your first event.
    *   **Pollster**: For creating your first poll.
    *   **Opinion Leader**: For voting in 5 different polls.
    *   **Rising Star**: For receiving 10 likes across all your posts.
    *   **Community Contributor**: For joining your first group.
    *   **Bookworm**: For bookmarking 5 posts.

    Explore the platform to discover all available achievements!

### Blog Post Comments

To enhance interactivity, users can now add comments to blog posts.

*   **Purpose**: Allows users to share their thoughts and engage in discussions on specific blog posts.
*   **Functionality**:
    *   **Adding Comments**: Authenticated (logged-in) users can submit comments via a form on each blog post's page (`/blog/post/<int:post_id>`). Comment content cannot be empty.
    *   **Viewing Comments**: All visitors can see comments displayed below the blog post content. Each comment shows the author's username, the timestamp of submission, and the content itself.
    *   **Authentication**: Only logged-in users can add comments. Non-logged-in users will see a prompt to log in.
*   **Route Involved**:
    *   `/blog/post/<int:post_id>/comment` (POST): Endpoint for processing and saving new comments.
*   **Flask Functionalities Demonstrated**:
    *   Managing one-to-many relationships (a post can have multiple comments).
    *   Handling nested resource creation (comments under posts).
    *   Further application of user authentication for content submission.
    *   Dynamic rendering of user-contributed content.

### Real-Time Comment Notifications

To further enhance interactivity, the blog now features real-time comment notifications.

*   **Instant Updates**: When a user submits a comment on a blog post, other users currently viewing the same post will see the new comment appear instantly on their page without needing to manually refresh.
*   **Technology**: This is implemented using Flask-SocketIO, enabling bidirectional real-time communication between the server and clients (browsers).
*   **Enhanced Engagement**: This feature makes discussions more dynamic and engaging, as users can see new contributions as they happen.

### Author Comment Notifications

*   **Targeted Alerts**: Post authors receive instant, targeted notifications when another user comments on one of their posts. This ensures authors are promptly informed of new interactions with their content.
*   **Implementation**: This is also powered by Flask-SocketIO, delivering notifications to the author's specific user channel.
*   **User Experience**: Authors are notified via a browser alert when viewing their post and a new comment arrives from someone else.

### Live Blog Post Updates (SSE)

To further enhance the interactivity of blog posts, the application now supports live updates directly on the post page using Server-Sent Events (SSE).

*   **Purpose**: This feature provides real-time updates for new comments and post edits directly on an individual blog post page, eliminating the need for users to manually refresh the page to see the latest activity.
*   **Technology**: It utilizes Server-Sent Events (SSE), a standard web technology for enabling efficient, one-way communication from the server to the client (browser).
*   **User Benefits**:
    *   **Enhanced Interactivity**: Users see new comments and changes to the post content as they happen.
    *   **Immediate Feedback**: Discussions feel more dynamic with comments appearing in real-time.
    *   **Improved Awareness**: Users are immediately aware of content edits made by the post author.

### Post Liking

Users can now interact with blog posts by liking or unliking them, providing a simple way to show appreciation or engagement.

*   **Functionality**:
    *   Authenticated (logged-in) users can "like" a blog post. If they have already liked a post, they can "unlike" it.
    *   Users can only like a specific post once. Attempting to like an already liked post will not change the like count. Similarly, unliking is only possible if the post was previously liked by the user.
    *   The total number of likes for each post is displayed on the main blog listing page (`/blog`) and on the individual post view page (`/blog/post/<int:post_id>`).
*   **User Interface**:
    *   On the individual post page, logged-in users will see a "Like" button. If they have already liked the post, this button will change to "Unlike".
    *   Users who are not logged in can see the like counts but will not see the Like/Unlike buttons.
*   **Routes for Like/Unlike Actions**:
    *   `/blog/post/<int:post_id>/like` (POST): Allows a logged-in user to like a specific post.
    *   `/blog/post/<int:post_id>/unlike` (POST): Allows a logged-in user to unlike a post they had previously liked.
*   **Flask Functionalities Demonstrated**:
    *   Further practice with user session management and authentication checks.
    *   Updating data models (incrementing/decrementing like counts, tracking user likes).
    *   Conditional rendering in Jinja templates to display different buttons ("Like" or "Unlike") based on application state.
    *   Handling POST requests for actions that modify data.

### Real-time Like Notifications
*   **Real-time Like Notifications**: When a user's post is liked by another user, the author of the post receives an instant notification. This is implemented using SocketIO for real-time communication and also creates a persistent notification in their notification list.

### Post Reactions

Users can now express a wider range of sentiments on blog posts using emoji reactions.

*   **Functionality**:
    *   Authenticated users can react to any blog post by selecting an emoji (e.g., 👍, ❤️, 🎉, 😂, 🤔).
    *   Clicking an emoji button below the post will add that reaction.
    *   If a user has already reacted to a post:
        *   Clicking the *same* emoji again will remove their reaction (toggle off).
        *   Clicking a *different* emoji will change their existing reaction to the new one.
    *   Users can only have one active emoji reaction per post.
*   **Display**:
    *   The individual post page (`/blog/post/<int:post_id>`) displays the available emoji reaction buttons for logged-in users.
    *   The page also shows a summary of all reactions on the post, displaying each emoji and the count of users who reacted with it (e.g., 👍 (5) ❤️ (3)).
*   **User Interface**:
    *   Reaction buttons are clearly visible on the post page.
    *   The user's currently selected emoji reaction (if any) is highlighted.
*   **Route for Reactions**:
    *   `/post/<int:post_id>/react` (POST): Allows a logged-in user to add, change, or remove their reaction to a specific post.

### Hashtags
- Users can add comma-separated hashtags to their posts (e.g., `python, flask, webdev`).
- Hashtags are displayed with each post and are clickable.
- Clicking a hashtag navigates to a dedicated page showing all posts associated with that tag, making it easy to discover related content.

### Blog Post Rating and Review System

Enhancing user interaction and feedback, users can now rate blog posts (1-5 stars) and write textual reviews.

*   **Purpose**: Allows users to provide detailed feedback and ratings on blog posts, helping others gauge post quality and fostering a more interactive community.
*   **Functionality Details**:
    *   **Review Submission**: Logged-in users can submit a rating (1 to 5 stars) and a textual review for any blog post.
    *   **Self-Review Restriction**: Users are prevented from reviewing their own blog posts.
    *   **Single Review Per Post**: Each user can submit only one review per blog post to ensure fairness.
    *   **Average Rating Display**:
        *   The calculated average rating for a post is displayed prominently on its individual view page (`/blog/post/<int:post_id>`).
        *   The average rating and review count are also shown for each post on the main blog listing page (`/blog`).
    *   **Review Visibility**: All submitted reviews, including the reviewer's username, their given rating, the review text, and the submission timestamp, are displayed on the individual post page.
*   **Route Involved**:
    *   `POST /blog/post/<int:post_id>/review`: Endpoint for submitting a new review for a specific blog post.
*   **Flask Functionalities Demonstrated**:
    *   Reinforces concepts of form handling (for rating and review text) and data validation (e.g., rating range, non-empty review text).
    *   Extends user session management for authorizing review submissions and tracking review authorship.
    *   Demonstrates dynamic calculation and display of aggregate data (average ratings).
    *   Further practice in managing and displaying user-generated content.

### Private Messaging

This application now supports private messaging between registered users, allowing for direct, one-on-one communication.

*   **Purpose**: Enables users to send and receive private messages, fostering a more interactive and personal experience on the platform.
*   **Authentication**: This feature is exclusively available to logged-in users. Users must be authenticated to send messages, view their inbox, and participate in conversations.

*   **Flask Functionalities Demonstrated**:
    *   **User-to-User Interaction**: Manages direct communication and data relationships between different users.
    *   **Dynamic Content Generation**: The inbox and conversation views are dynamically generated based on the logged-in user's messages.
    *   **Form Handling**: Uses forms for composing and sending messages.
    *   **Session Management**: Leverages user sessions to identify the sender and receiver, and to authorize access to messages.
    *   **Data Persistence**: Messages are stored in-memory (similar to blog posts and comments) and include sender, receiver, content, timestamp, and a read status.
    *   **Conditional Logic**: Used extensively in templates and views to display appropriate information (e.g., unread message counts, user-specific conversation views).

*   **Routes & Usage**:
    *   `/messages/inbox`: (GET)
        *   Requires login.
        *   Displays the logged-in user's message inbox.
        *   Lists all conversations the user is part of, ordered by the most recent message.
        *   For each conversation, it shows the other user, a snippet of the last message, the timestamp of the last message, and a count of unread messages in that conversation.
        *   Each conversation entry links to the full conversation view.
    *   `/messages/conversation/<username>`: (GET)
        *   Requires login.
        *   Displays the full message history between the logged-in user and the specified `<username>`.
        *   Messages are displayed in chronological order.
        *   When a user opens a conversation, any unread messages they received in that conversation are automatically marked as "read".
        *   Includes a reply form at the bottom to quickly send another message to the conversation partner.
    *   `/messages/send/<receiver_username>`: (GET/POST)
        *   Requires login.
        *   `GET`: Displays a form to compose a new message to `<receiver_username>`. This is typically accessed via the "Send Message" button on a user's profile or the reply form in a conversation.
        *   `POST`: Processes the submitted message content and sends it to `<receiver_username>`. Redirects to the conversation view with that user upon successful sending.
    *   `/user/<username>`:
        *   User profile pages now feature a "Send Message" button if the viewer is logged in and is not viewing their own profile. This button links directly to the `/messages/send/<username>` route for the profile owner.

### Real-Time Direct Messaging

Enhancing the private communication capabilities, the application now supports real-time direct messaging between users.

*   **Functionality**:
    *   Users can send direct messages to other registered users.
    *   Conversations update instantly without requiring a page reload, showing new messages as they arrive.
    *   The user's inbox also dynamically updates to reflect new messages and unread counts, ensuring users are always aware of new communications.
*   **Technology Stack**: This feature is powered by Flask, Flask-SocketIO for real-time bidirectional communication, and SQLAlchemy for database interactions with the `Message` model.
*   **User Experience**: Provides a seamless and interactive messaging experience, similar to modern chat applications.

### User Notifications (Real-time via SSE)

To keep users immediately informed of important social interactions, the application now features a real-time notification system built with Server-Sent Events (SSE). This system delivers non-intrusive toast notifications directly to the user's active browser session for the following events:

*   **Friend Request Received**: When another user sends you a friend request, you'll receive an instant notification. The alert includes the sender's username and a direct link to their profile, allowing for quick interaction.
*   **Friend Request Accepted (New Follower)**: When a user accepts your friend request, you'll be notified immediately that they are now following you. This notification also includes the new follower's username and a link to their profile.

This SSE-based system complements other real-time features, providing lightweight, unidirectional updates from the server for timely alerts. The client-side JavaScript listens for these specific events and displays the information in a temporary toast message on the screen.

### Real-time Friend Post Notifications
*   **Instant Alerts**: Users receive immediate toast notifications when a friend they are connected with creates a new blog post. This allows for timely discovery of content shared by friends.
*   **Dedicated Activity Page**: A "Friend Activity" page (`/friend_post_notifications`) provides a chronological history of these notifications. Users can view details, link directly to the friend's post, and manage the read status of each notification (mark as read individually or mark all as read).
*   **Technology**: Leverages Flask-SocketIO for real-time event emission and client-side JavaScript to display these toast notifications dynamically.

### User-to-User File Sharing

Allows users to securely share files directly with other registered users.

*   **Functionality Details**:
    *   **Sending Files**:
        *   Users can initiate a file share from another user's profile page by clicking the "Share File with [username]" button, or by directly navigating to the share page if the recipient's username is known.
        *   An optional message can be attached to the file share.
        *   Supported file types include common documents, images, and archives (e.g., .txt, .pdf, .png, .jpg, .zip, .docx, .xlsx, .pptx).
        *   There is a maximum file size limit (e.g., 16MB).
    *   **Receiving Files**:
        *   Users can view files shared with them in their "File Inbox", accessible from the main navigation bar.
        *   Each file entry in the inbox displays the sender's username, the original filename, the upload timestamp, and any attached message.
        *   New or unread files are visually highlighted in the inbox.
    *   **Downloading Files**:
        *   Files can be downloaded by clicking the "Download" link next to the file in the inbox.
        *   Only the intended recipient and the original sender are authorized to download a shared file.
        *   When a recipient downloads a file, it is automatically marked as "read".
    *   **Deleting Files**:
        *   Users can delete files from their inbox (if they are the receiver).
        *   Users can also delete files they have sent (this action is also performed from their view of the file, typically the inbox if they sent it to themselves, or if a "sent files" view were implemented). The current implementation allows deletion if the user is either sender or receiver.

*   **Routes & Key UI Points**:
    *   `/files/share/<receiver_username>`: Page to initiate sharing a file with a specific user.
    *   `/files/inbox`: Displays all files received by the logged-in user.
    *   `/files/download/<shared_file_id>`: Endpoint for downloading a specific shared file (accessed via links in the inbox).
    *   `/files/delete/<shared_file_id>`: Endpoint for deleting a shared file (accessed via buttons in the inbox).

*   **Technical Notes**:
    *   Files are stored in a dedicated secure folder on the server.
    *   Unique filenames are used internally for stored files to prevent conflicts.

### Polls Feature

This application now includes a "Polls" feature, allowing users to create and participate in polls.

*   **Purpose**: Allows users to create polls with multiple options, vote on polls created by others, and view the results.
*   **Flask Functionalities Demonstrated**:
    *   CRUD operations for polls (Create, Read, Delete - Update is not implemented for simplicity).
    *   Advanced form handling for creating polls with a variable number of options (though currently fixed in template, backend supports dynamic).
    *   User interaction and session management to track votes and ensure vote integrity (one vote per user per poll).
    *   Data aggregation and presentation for displaying poll results, including vote counts and percentages.
    *   Authorization to ensure only poll authors can delete their polls.

*   **Routes & Usage**:
    *   `/polls`: (GET)
        *   Lists all available polls, showing the question, author, and creation date.
        *   Each poll links to its detailed view.
    *   `/polls/create`: (GET/POST)
        *   Requires login.
        *   `GET`: Displays a form for creating a new poll, including fields for the poll question and multiple options.
        *   `POST`: Submits the new poll data. Validates input (question and at least two options required).
    *   `/poll/<int:poll_id>`: (GET)
        *   Displays the poll question, its options, and current results (vote counts and percentages).
        *   If the user is logged in and has not yet voted on this poll, a voting form with radio buttons for options is presented.
        *   If the user is the author of the poll, a "Delete Poll" button is visible.
    *   `/poll/<int:poll_id>/vote`: (POST)
        *   Requires login.
        *   Processes the vote submitted by a user for a specific option in the poll.
        *   Redirects back to the poll view page, which will then show the updated results or a confirmation.
    *   `/poll/<int:poll_id>/delete`: (POST)
        *   Requires login and that the logged-in user is the author of the poll.
        *   Deletes the specified poll and all its associated vote data.
        *   Redirects to the main polls list.
*   **Key Characteristics**:
    *   Users must be logged in to create polls and to vote.
    *   A user can only vote once on any given poll. Attempts to vote multiple times are prevented.
    *   Poll authors have the ability to delete their own polls. Non-authors cannot delete polls.
    *   Poll results are displayed to all users, showing the number of votes for each option and the corresponding percentage of total votes.

### Bookmarking Posts

Users can now bookmark their favorite posts to easily find them later.

*   **Purpose**: Allows users to save a personal collection of posts for quick access.
*   **Functionality**:
    *   **Bookmarking/Unbookmarking**: Logged-in users will find a "Bookmark" button on individual post pages (`/blog/post/<id>`) and in post listings (e.g., main blog page `/blog`, user profile pages `/user/<username>`). If a post is already bookmarked, the button will show "Unbookmark". Clicking the button toggles the bookmark status.
    *   **Viewing Bookmarks**: Logged-in users can view all their bookmarked posts on a dedicated page: `/bookmarks`. Posts are listed by when they were most recently bookmarked.
*   **Key Characteristics**:
    *   Only logged-in users can bookmark posts and view their personal bookmark list.
    *   The bookmark status is specific to each user.

### Share Posts

Users can share posts made by other users (or their own posts) to their profile, optionally adding a personal comment. This helps users highlight content they find interesting to their followers or visitors of their profile page.

*   **Functionality**:
    *   Users can share any existing blog post.
    *   When sharing, users can add an optional comment to provide context or their thoughts on the shared content.
    *   Shared posts, along with any user comments, are displayed on the sharing user's profile page, ordered by when they were shared (most recent first).
    *   Original posts display a count of how many times they have been shared.
    *   Users cannot share the same post multiple times; if attempted, an informational message is shown.

*   **How to Use**:
    *   **Sharing a Post**:
        *   Navigate to a post's individual page (`/blog/post/<id>`) or find a post snippet on the main blog page (`/blog`).
        *   Click the "Share" button associated with the post.
        *   If sharing from the individual post page, a text area will be available to add an optional comment.
        *   If sharing from the main blog page, the post will be shared immediately without a comment field (for quick sharing).
    *   **Viewing Shared Posts**:
        *   Shared posts by a specific user can be viewed on their profile page (`/user/<username>`) under the "Shared Posts" section. Each entry will show the sharer's comment (if any), details of the original post (title, author, snippet), and a link to the original post.
    *   **Share Counts**: The number of times a post has been shared is visible on its individual page and on the main blog listing.

### Event Management

The application now includes an Event Management system, allowing users to organize and participate in events.

*   **Purpose**: Enables users to create events, announce them to the community, and manage RSVPs.
*   **Authentication**: Creating events and RSVPing requires users to be logged in. All users can view event listings and details.

*   **Key Functionalities**:
    *   **Event Creation**: Logged-in users can create new events by providing a title, description, date, time (optional), and location.
    *   **Event Listing**: All users can view a list of upcoming events on the `/events` page, sorted by event date.
    *   **Detailed Event View**: Clicking on an event shows its full details, including description, date, time, location, and organizer.
    *   **RSVP System**: Logged-in users can RSVP to an event with "Attending", "Maybe", or "Not Attending". Their current RSVP status is displayed on the event page.
    *   **RSVP Counts**: The event page displays a summary of how many users have RSVP'd with each status (e.g., "Attending: 5, Maybe: 2, Not Attending: 1").
    *   **Event Deletion**: Event organizers can delete their own events. This action is restricted to the user who created the event.
    *   **User Profile Integration**: Users' profiles display a list of events they have organized.

*   **Routes & Usage**:
    *   `/events`: (GET) Displays a list of all upcoming events.
    *   `/events/create`: (GET/POST)
        *   Requires login.
        *   `GET`: Shows a form to create a new event.
        *   `POST`: Submits the new event details.
    *   `/event/<int:event_id>`: (GET)
        *   Displays detailed information for a specific event, including RSVP counts and options for logged-in users to RSVP.
        *   If the logged-in user is the organizer, a "Delete Event" button is visible.
    *   `/event/<int:event_id>/rsvp`: (POST)
        *   Requires login.
        *   Processes the RSVP submitted by a user for the event.
    *   `/event/<int:event_id>/delete`: (POST)
        *   Requires login and that the logged-in user is the event organizer.
        *   Deletes the specified event and its RSVP data.

### User Groups Feature

To foster community building, the application now supports User Groups. This feature allows users to create, join, and participate in groups centered around common interests or topics.

*   **Purpose**: Enables users to form and manage their own communities within the application, share discussions (future enhancement), and organize members.
*   **Authentication**: Creating, joining, and leaving groups are actions that require users to be logged in. All users (including non-logged-in visitors) can view group lists and individual group pages.

*   **Key Functionalities**:
    *   **Group Creation**: Logged-in users can create new groups by providing a name and an optional description. The user who creates the group automatically becomes its first member and is marked as the creator.
    *   **Group Listing**: A dedicated page displays all available groups, showing their name, description snippet, creator, and current member count.
    *   **Detailed Group View**: Each group has its own page displaying its full description, list of members (with links to their profiles), and who created it.
    *   **Membership Management**:
        *   Logged-in users can join any public group (unless they are already a member).
        *   Members of a group can choose to leave it. (Currently, creators can also leave their groups).
    *   **User Profile Integration**: Each user's profile page now includes a section listing all the groups they are a member of, with direct links to those group pages. A "Creator" badge is shown if the user is the creator of a listed group.

*   **Routes & Usage**:
    *   `/groups/create` (GET/POST):
        *   `GET`: Displays the form for creating a new group.
        *   `POST`: Processes the group creation form. Requires login.
    *   `/groups` (GET): Displays a list of all existing groups.
    *   `/group/<int:group_id>` (GET): Displays the detailed page for a specific group, including its members and options to join/leave (if applicable for the logged-in user).
    *   `/group/<int:group_id>/join` (POST): Allows a logged-in user to join the specified group.
    *   `/group/<int:group_id>/leave` (POST): Allows a logged-in user to leave the specified group.

### Real-time Group Chat
*   Allows members of a group to send and receive messages in real-time within the group's page. Messages are stored, and the chat history is loaded upon visiting the group page. This feature is powered by Flask-SocketIO, enabling instant communication and a dynamic chat experience.

### In-App Notifications

To keep users informed about recent activity on the platform, an in-app notification system has been implemented.

*   **Purpose**: Alerts users to new content such as new blog posts, upcoming events, or recently created polls.
*   **How it Works**: A background task runs periodically (e.g., every minute) to scan for new content. When new items are found, notifications are generated.
*   **Accessing Notifications**: Logged-in users can find a "Notifications" link in the navigation bar, which leads to a page displaying all recent activity alerts, sorted by time.

### Content Series

The "Content Series" feature allows users to group multiple blog posts into an ordered collection. This is useful for creating multi-part tutorials, chronological narratives, or any set of posts that benefit from a defined sequence.

*   **Purpose**: To organize related blog posts into a cohesive, ordered series, making it easier for readers to follow along.
*   **Key Functionalities**:
    *   **Creation**: Logged-in users can create a new series by providing a title and an optional description.
    *   **Adding Posts**: Authors can add their own existing blog posts to a series they created.
    *   **Ordering**: Posts within a series maintain a specific order, which can be managed by the series author. (Currently, posts are added to the end, and removing a post re-calculates the order of subsequent posts).
    *   **Editing Series Details**: Authors can update the title and description of their series.
    *   **Removing Posts**: Authors can remove posts from their series. This does not delete the post itself, only its association with the series.
    *   **Deleting Series**: Authors can delete an entire series. This action removes the series and its associations with posts but does not delete the posts themselves.
*   **How to Use**:
    *   **Creating a Series**: A "Create Series" link is available in the navigation bar for logged-in users, leading to the `/series/create` page.
    *   **Viewing a Series**:
        *   Series created by a user are listed on their profile page (`/user/<username>`).
        *   Each series has a dedicated page (`/series/<series_id>`) that displays its title, description, author, and all its posts in their defined order.
    *   **Managing Posts in a Series**:
        *   From the "Edit Series" page (`/series/<series_id>/edit`), accessible to the author via the "View Series" page:
            *   Authors can see a list of posts currently in the series, with options to remove them.
            *   Authors can see a list of their other posts that are not yet in the series, with options to add them.
    *   **Series Navigation on Post Pages**:
        *   When viewing an individual blog post (`/blog/post/<post_id>`), if the post is part of one or more series, these series will be listed with links to their respective view pages.
        *   If a post is viewed with a specific series context (e.g., by clicking through from a series page, via a URL like `/blog/post/<post_id>?series_id=<series_id>`), "Next" and "Previous" navigation links will appear on the post page, allowing the user to navigate to the next or previous post within that specific series.

### Recommendations Feature

To enhance user engagement and content discovery, this application now includes a recommendations feature. Users can discover:

*   **Suggested Users to Follow**: Based on mutual connections (friends of friends) and other social interactions.
*   **Suggested Posts to Read**: Highlighting posts relevant to a user. The system now considers posts that the user's friends have recently liked *or commented on*, prioritizing content with the freshest interactions to provide timely and engaging suggestions.
*   **Suggested Groups to Join**: Pointing out groups that friends are part of or that align with a user's activity.

The recommendations feature has been enhanced to also suggest relevant events and polls:

*   **Event Recommendations**: Discover events you might like! Suggestions are based on:
    *   Events your friends have RSVP'd to as "Attending" or "Maybe".
    *   Events that are generally popular within the community based on RSVP counts.
    *   You won't see events you've already RSVP'd to or those you've organized.

*   **Poll Recommendations**: Find interesting polls to participate in. Suggestions include:
    *   Polls created by your friends.
    *   Popular polls that have garnered a significant number of votes.
    *   You won't be shown polls you've already voted on or those you created yourself.

*   **Recommended Hashtags**: Discover trending or relevant topics.
    *   **Functionality**: Suggests hashtags that might interest the user based on overall popularity within the platform.
    *   **Logic**: Recommendations are derived from the most frequently used hashtags across all posts, carefully filtered to exclude hashtags the current user has already used in their own posts.
    *   **Accessibility**: These hashtag suggestions are displayed on the main `/recommendations` page for logged-in users.

*   **Trending Hashtags on Blog Page**:
    *   **Functionality**: Displays a list of the most popular hashtags, calculated from all posts, directly on the main blog page.
    *   **Discovery**: Allows all users (including those not logged in) to quickly see trending topics and navigate to posts associated with them.
    *   **Accessibility**: Visible in the sidebar of the `/blog` page.

*   **Discovery Feed**:
    *   **Functionality**: A centralized feed designed to help users discover a wide range of new and relevant content. It aggregates various types of recommendations into a single, easily accessible page.
    *   **Content**: The feed includes:
        *   Personalized post suggestions (based on friend activity and user preferences).
        *   Trending posts (popular across the platform).
        *   Recommended groups to join.
        *   Suggested events to attend.
    *   **Benefit**: Provides a comprehensive overview of interesting content and activities, tailored to the user, enhancing their engagement and experience on the platform.
    *   **Access**: Logged-in users can access their Discovery Feed via the "Discovery" link in the main navigation bar.

*   **Trending Posts Page**:
    *   **Functionality**: Displays a dedicated list of posts that are currently popular based on recent user interactions such as likes, comments, and shares.
    *   **Algorithm**: The trending algorithm emphasizes recent activity to ensure the list of trending posts remains fresh and relevant.
    *   **Access**: Accessible to all users (logged-in or not) via the "Trending" link in the main navigation bar.

These new recommendations are available on the main `/recommendations` page. The Discovery Feed provides an alternative, aggregated view.

You can find dedicated recommendations on the `/recommendations` page (accessible when logged in). Additionally, a snippet of user suggestions is displayed on the main blog page to help you connect with others more easily.

#### Enhanced Post Recommendations with Reasons
The personalized feed, particularly for posts displayed on pages like the Discover page, now includes a specific reason why each post is being recommended to the user. This enhancement aims to provide transparency and help users understand the system's choices (e.g., "Liked by a friend," "Trending post," "From a group you joined," "From user you follow," etc.). This involves updates to the backend recommendation generation and how this information is passed to and displayed on the frontend.

### Real-time Collaborative Post Editing

This feature enables multiple users to see live updates when a post is being edited and ensures that only one user can edit a post at a time.

*   **How it Works**:
    *   **Locking Mechanism**: A user must acquire an "edit lock" on a post before they can make changes. This prevents simultaneous edits by different users. The lock is temporary and expires after a set duration (e.g., 15 minutes).
    *   **Real-time Updates**: When the user holding the lock types, their changes are sent to the server and broadcast to all other users viewing or editing the same post. These updates appear live on their screens.
    *   **Lock Status Display**: The UI clearly indicates if a post is locked, who is currently editing it, and when their lock expires.
    *   **API for Locking**: Lock acquisition and release are handled via dedicated RESTful API endpoints.
*   **Technologies Used**:
    *   **Flask-SocketIO**: For real-time bidirectional communication between clients and the server, used for broadcasting content changes and lock status updates.
    *   **Flask-RESTful**: For creating the API endpoints (`/api/posts/<post_id>/lock`) that manage the lifecycle of post locks.
    *   **JavaScript (Client-Side)**: Handles acquiring/releasing locks, sending content changes, and updating the UI based on server events.

### Real-Time Chat

The application now features a real-time chat system, allowing users to communicate instantly in public or private chat rooms.

*   **Functionality**:
    *   **Chat Rooms**: Users can create new chat rooms or join existing public ones.
    *   **Real-Time Messaging**: Messages sent in a room are broadcast instantly to all other participants in that room.
    *   **User Presence**: Users are notified when other users join or leave the chat room they are in.
    *   **Message Persistence**: Chat messages are saved to the database, allowing users to view conversation history.
*   **Access**:
    *   A "Chat" link in the main navigation bar leads to the chat interface (`/chat`).
    *   The chat page displays a list of available chat rooms and the main chat area.
*   **Technology**:
    *   **Flask-SocketIO**: Powers the real-time communication for sending and receiving messages and presence updates.
    *   **SQLAlchemy**: Manages `ChatRoom` and `ChatMessage` models for storing room information and message history.
    *   **RESTful API**: Endpoints under `/api/chat/` allow for listing rooms, creating rooms, and fetching message history for a room.
    *   **JavaScript**: Client-side logic handles SocketIO connections, sending/receiving messages, and dynamically updating the chat UI.

### On This Day

This feature allows users to revisit their past posts and events that occurred on the same calendar day in previous years.

*   **Web Page Functionality**:
    *   Logged-in users can access their "On This Day" page by clicking the "On This Day" link in the navigation bar.
    *   The page (`/onthisday`) displays two sections:
        *   **Past Posts**: Lists blog posts created by the user on the current month and day, but from previous years. Each entry shows the post's title (linked to the full post), a content snippet, and the original timestamp.
        *   **Past Events**: Lists events created by the user where the event date (not creation date) matches the current month and day, but from previous years. Each entry shows the event's title (linked to the full event page), a description snippet, and the event's date and time.
    *   If no content is found for the current day in past years, appropriate messages are displayed.

*   **API Endpoint**:
    *   See the `GET /api/onthisday` endpoint documentation under the "RESTful API" section for details on programmatic access.

### Content Moderation

The application includes a content moderation system to help maintain a safe and respectful environment. This feature allows users to report inappropriate content (posts or comments) and for designated moderators to review these reports and take appropriate action.

### Featured Post of the Day
*   **Functionality**: Highlights a selected post on the homepage.
*   **Selection**: Posts can be manually featured by an admin. If no post is manually featured, one is selected automatically (e.g., randomly or by other criteria) to ensure fresh content on the homepage.
*   **Admin Control**: Admins can use the `/admin/feature_post/<post_id>` route (via a POST request) to toggle a specific post's featured status.

*   **Purpose**: To empower the community to identify and flag content that violates community guidelines, and to provide moderators with the tools to manage these reports efficiently.

*   **Flagging Content (User Action)**:
    *   Logged-in users can flag any post or comment that they believe is inappropriate or violates community standards.
    *   Flag buttons are available next to posts and comments.
    *   Users cannot flag their own content.
    *   When flagging, users can optionally provide a reason for their report to give moderators more context.

*   **Moderator Role**:
    *   The 'moderator' is a special user role with elevated privileges.
    *   Users with this role gain access to the Moderation Dashboard.
    *   (Note: Assignment of the 'moderator' role is typically handled by an administrator through a separate process, e.g., direct database modification or an admin interface, which is outside the scope of this feature's direct implementation).

*   **Moderation Dashboard**:
    *   Accessible via the `/moderation` route (requires moderator privileges).
    *   Lists all content items (posts or comments) that have been flagged by users and are currently in 'pending' status, ordered by when they were flagged.
    *   For each flagged item, the dashboard displays:
        *   Flag ID
        *   Type of content (e.g., 'post', 'comment')
        *   ID of the flagged content
        *   A direct link to view the actual content in context.
        *   The reason provided by the user for flagging (if any).
        *   The username of the user who flagged the content (with a link to their profile).
        *   The timestamp of when the flag was submitted.

*   **Moderator Actions**:
    From the dashboard, moderators can take one of the following actions on a pending flag:
    *   **Approve Flag**: If the moderator deems the flag valid but the content itself does not warrant removal (e.g., a borderline case that needs monitoring, or the flag was for a minor issue already resolved). The flag status is updated to 'approved'. The content remains visible.
    *   **Reject Flag**: If the moderator finds the flag unnecessary or incorrect (e.g., the content is acceptable, or the flag was submitted in error). The flag status is updated to 'rejected'. The content remains visible.
    *   **Remove Content & Reject Flag**: If the moderator agrees that the content is inappropriate and violates guidelines. The actual content (the post or comment) is deleted from the site. The flag status is then updated to 'content_removed_and_rejected'.
    *   For all actions, moderators can optionally add a comment to record their reasoning or decision-making process. This comment is stored with the flag details.

*   **Workflow**:
    1. User flags a post or comment.
    2. The flagged item appears on the Moderation Dashboard.
    3. A moderator reviews the flagged item and the reason.
    4. The moderator chooses an appropriate action (Approve, Reject, or Remove Content & Reject).
    5. The flag's status is updated, and if applicable, the content is removed. The moderator who took the action and the resolution time are recorded.

## RESTful API

This application provides a RESTful API for interacting with its core resources: Users, Posts, and Events.

### Authentication

The API uses JSON Web Tokens (JWT) for authentication. To access protected endpoints, you first need to obtain a token by sending your credentials to the `/api/login` endpoint.

**POST /api/login**

*   **Request:**
    ```json
    {
        "username": "your_username",
        "password": "your_password"
    }
    ```
*   **Response (Success - 200 OK):**
    ```json
    {
        "access_token": "your_jwt_access_token"
    }
    ```
*   **Response (Failure - 401 Unauthorized):**
    ```json
    {
        "message": "Invalid credentials"
    }
    ```

Include the obtained `access_token` in the `Authorization` header as a Bearer token for subsequent requests to protected endpoints:
`Authorization: Bearer <your_jwt_access_token>`

### Users API

*   **GET /api/users**
    *   Description: Retrieves a list of all users.
    *   Authentication: Not required.
    *   Response:
        ```json
        {
            "users": [
                {
                    "id": 1,
                    "username": "demo",
                    "uploaded_images": null
                }
                // ... other users
            ]
        }
        ```

## SocketIO Events Documentation

This section outlines the key SocketIO events used for real-time features within the application.

### Real-time Editing SocketIO Events

These events facilitate the collaborative editing feature for posts.

**Server-to-Client Events (Listen for these on the client):**

*   **`post_lock_acquired`**
    *   **Room**: `post_<post_id>` (Broadcast to all clients viewing/editing the specific post)
    *   **Payload**:
        ```json
        {
            "post_id": 123,
            "user_id": 1,
            "username": "testuser",
            "expires_at": "YYYY-MM-DDTHH:MM:SS.ffffff" // ISO format UTC timestamp
        }
        ```
    *   **Description**: Sent when a user successfully acquires an editing lock on a post. Clients should use this to update their UI (e.g., disable editing for others, show who has the lock).

*   **`post_lock_released`**
    *   **Room**: `post_<post_id>`
    *   **Payload**:
        ```json
        {
            "post_id": 123,
            "released_by_user_id": 1, // User who released it, or null if system (e.g., expired)
            "username": "testuser" // Username of user who released, or "System (Expired)"
        }
        ```
    *   **Description**: Sent when a lock on a post is released (either manually or due to expiration). Clients should update their UI to show the post is now available for editing.

*   **`post_content_updated`**
    *   **Room**: `post_<post_id>`
    *   **Payload**:
        ```json
        {
            "post_id": 123,
            "new_content": "The updated content of the post...",
            "last_edited": "YYYY-MM-DDTHH:MM:SS.ffffff", // ISO format UTC timestamp of the edit
            "edited_by_user_id": 1,
            "edited_by_username": "testuser"
        }
        ```
    *   **Description**: Broadcast when the content of a post is updated by the user holding the lock. Clients should update the displayed post content in real-time.

*   **`edit_error`** (Emitted to a specific client, not a room)
    *   **Recipient**: Sender of an `edit_post_content` event that failed.
    *   **Payload**:
        ```json
        { "message": "Error description (e.g., 'You do not hold the lock for this post.')" }
        ```
    *   **Description**: Sent to a client if their attempt to edit content (via `edit_post_content`) fails due to server-side validation (e.g., not holding the lock, lock expired).

*   **`edit_success`** (Emitted to a specific client, not a room)
    *   **Recipient**: Sender of a successfully processed `edit_post_content` event.
    *   **Payload**:
        ```json
        {
            "message": "Content updated successfully.",
            "post_id": 123
        }
        ```
    *   **Description**: Confirms to the editing client that their content change was received and processed by the server.

**Client-to-Server Events (Emit these from the client):**

*   **`join_room`**
    *   **Payload**: `{'room': 'post_<post_id>'}`
    *   **Description**: Client sends this event when they start viewing/editing a specific post to join the dedicated SocketIO room for that post. This allows them to receive targeted updates. (This is a general event, its usage for post editing is noted here).

*   **`edit_post_content`**
    *   **Payload**:
        ```json
        {
            "post_id": 123,
            "new_content": "User's typed content..."
        }
        ```
    *   **Description**: Sent by the client when a user (who holds the lock) modifies the content of the post in the editor. This event is typically debounced to avoid excessive emissions.

*   **GET /api/users/<user_id>**
    *   Description: Retrieves a specific user by ID.
    *   Authentication: Not required.
    *   Response:
        ```json
        {
            "user": {
                "id": 1,
                "username": "demo",
                "uploaded_images": null
            }
        }
        ```

### Post Locking API

*   **POST /api/posts/<int:post_id>/lock**
    *   **Description**: Acquires an exclusive lock for editing a post.
    *   **Authentication**: Required (JWT Bearer Token).
    *   **Response (Success 200 OK)**: JSON object with lock details.
        ```json
        {
            "message": "Post locked successfully.",
            "lock_details": {
                "post_id": 123,
                "locked_by_user_id": 1,
                "locked_by_username": "testuser",
                "locked_at": "YYYY-MM-DDTHH:MM:SS.ffffff",
                "expires_at": "YYYY-MM-DDTHH:MM:SS.ffffff"
            }
        }
        ```
    *   **Response (Error 401 Unauthorized)**: If token is missing or invalid.
        ```json
        { "msg": "Missing Authorization Header" }
        ```
    *   **Response (Error 404 Not Found)**: If the post does not exist.
        ```json
        { "message": "Post not found" }
        ```
    *   **Response (Error 409 Conflict)**: If the post is already actively locked by another user.
        ```json
        {
            "message": "Post is currently locked by another user.",
            "locked_by_username": "otheruser",
            "expires_at": "YYYY-MM-DDTHH:MM:SS.ffffff"
        }
        ```

*   **DELETE /api/posts/<int:post_id>/lock**
    *   **Description**: Releases an existing lock on a post.
    *   **Authentication**: Required (JWT Bearer Token). User must be the lock owner.
    *   **Response (Success 200 OK)**:
        ```json
        { "message": "Post unlocked successfully." }
        ```
    *   **Response (Error 401 Unauthorized)**: If token is missing or invalid.
    *   **Response (Error 403 Forbidden)**: If the user trying to release the lock is not the owner.
        ```json
        {
            "message": "You are not authorized to unlock this post as it is locked by another user.",
            "locked_by_username": "current_lock_owner"
        }
        ```
    *   **Response (Error 404 Not Found)**: If the post does not exist or no active lock is found for the post.
        ```json
        { "message": "Post not found" }
        ```
        or
        ```json
        { "message": "Post is not currently locked." }
        ```

### Series API

*   **GET /api/series**
    *   Description: Retrieves a list of all content series.
    *   Authentication: Not required.
    *   Response (Example):
        ```json
        {
            "series": [
                {
                    "id": 1,
                    "title": "My Flask Tutorial Series",
                    "description": "A series of posts about Flask.",
                    "author_username": "testuser1",
                    "created_at": "2023-01-15T10:00:00",
                    "updated_at": "2023-01-16T11:00:00",
                    "posts": [
                        {
                            "id": 10,
                            "title": "Flask Intro",
                            "author_username": "testuser1"
                        },
                        {
                            "id": 12,
                            "title": "Flask Blueprints",
                            "author_username": "testuser1"
                        }
                    ]
                }
                // ... other series
            ]
        }
        ```

*   **GET /api/series/<series_id>**
    *   Description: Retrieves a specific content series by ID, including its ordered posts.
    *   Authentication: Not required.
    *   Response (Example):
        ```json
        {
            "series": {
                "id": 1,
                "title": "My Flask Tutorial Series",
                "description": "A series of posts about Flask.",
                "author_username": "testuser1",
                "created_at": "2023-01-15T10:00:00",
                "updated_at": "2023-01-16T11:00:00",
                "posts": [
                    {
                        "id": 10,
                        "title": "Flask Intro",
                        "author_username": "testuser1"
                    },
                    {
                        "id": 12,
                        "title": "Flask Blueprints",
                        "author_username": "testuser1"
                    }
                ]
            }
        }
        ```

### "On This Day" API

*   **GET /api/onthisday**
    *   **Description:** Retrieves posts and events created by the authenticated user that occurred on the current month and day in previous years.
    *   **Authentication:** Required (JWT Token). The token should be passed in the `Authorization` header as a Bearer token (e.g., `Authorization: Bearer <YOUR_JWT_TOKEN>`).
    *   **Successful Response (200 OK):**
        ```json
        {
          "on_this_day_posts": [
            {
              "id": 1,
              "title": "My Throwback Post",
              "content": "Content of the post from a past year.",
              "timestamp": "2022-10-26T10:00:00",
              "last_edited": null,
              "user_id": 123,
              "author_username": "testuser",
              "hashtags": "#throwback",
              "is_featured": false,
              "featured_at": null
            }
          ],
          "on_this_day_events": [
            {
              "id": 1,
              "title": "Past Event",
              "description": "Details of an event from a past year.",
              "date": "2022-10-26",
              "time": "14:00",
              "location": "Some Location",
              "created_at": "2022-10-20T14:30:00",
              "user_id": 123,
              "organizer_username": "testuser"
            }
          ]
        }
        ```
        *(Note: The exact fields returned for posts and events depend on their respective `to_dict()` methods in `models.py`.)*
    *   **Error Responses:**
        *   `401 Unauthorized`: If the JWT token is missing or invalid.
            ```json
            {
                "msg": "Missing Authorization Header"
            }
            ```

### Trending Hashtags API

*   **GET /api/trending_hashtags**
    *   Description: Retrieves a list of currently trending hashtags, ordered by rank.
    *   Authentication: Not required.
    *   Response (Success - 200 OK):
        ```json
        {
            "trending_hashtags": [
                {
                    "id": 1,
                    "hashtag": "flaskdev",
                    "score": 25.5,
                    "rank": 1,
                    "calculated_at": "2023-11-01T10:00:00Z"
                },
                {
                    "id": 2,
                    "hashtag": "python",
                    "score": 18.2,
                    "rank": 2,
                    "calculated_at": "2023-11-01T10:00:00Z"
                }
                // ... other trending hashtags
            ]
        }
        ```

### Content Recommendations API

*   **GET /api/recommendations**
    *   **Description:** Retrieves personalized content recommendations for a given user.
    *   **Authentication:** Not required.
    *   **Query Parameters:**
        *   `user_id` (integer, required): The ID of the user for whom to fetch recommendations.
    *   **Success Response (200 OK):**
        *   **Content-Type:** `application/json`
        *   **Body:** A JSON object containing the user's ID and various lists of suggested content.
        *   **Example:**
            ```json
            {
                "user_id": 1,
                "suggested_posts": [
                    {"id": 101, "title": "A Great Post", "author_username": "user2", "content": "...", "timestamp": "...", "user_id": 2, "hashtags": null, "is_featured": false, "featured_at": null}
                ],
                "suggested_groups": [
                    {"id": 5, "name": "Cool Group", "description": "...", "creator_id": 3, "created_at": "...", "creator_username": "user3"}
                ],
                "suggested_events": [
                    {"id": 12, "title": "Upcoming Event", "description": "...", "date": "...", "time": "...", "location": "...", "created_at": "...", "user_id": 2, "organizer_username": "user2"}
                ],
                "suggested_users_to_follow": [
                    {"id": 4, "username": "user4", "email": "user4@example.com", "profile_picture": null, "bio": "...", "uploaded_images": null}
                ],
                "suggested_polls_to_vote": [
                    {"id": 7, "question": "Favorite Color?", "user_id": 2, "created_at": "...", "author_username": "user2", "options": [{"id": 15, "text": "Blue", "vote_count": 0}, {"id": 16, "text": "Red", "vote_count": 0}]}
                ]
            }
            ```
    *   **Error Responses:**
        *   **400 Bad Request:** If `user_id` is missing or invalid.
            ```json
            {
                "message": {
                    "user_id": "User ID is required and must be an integer."
                }
            }
            ```
            *(Note: The exact message for a missing parameter might be "Missing required parameter in the query string" or similar, depending on Flask-RESTful configuration.)*
        *   **404 Not Found:** If the specified `user_id` does not exist.
            ```json
            {
                "message": "User not found"
            }
            ```

*   **GET /api/users/<user_id>/feed**
    *   **Description:** Retrieves a personalized feed of posts for the specified user. The feed is curated based on the user's activity, connections (friends, groups), and trending content. Each post in the feed now includes a `recommendation_reason` string, explaining why the post was suggested.
    *   **Authentication:** Not required.
    *   **Path Parameters:**
        *   `user_id` (integer): The ID of the user for whom to retrieve the feed.
    *   **Success Response (200 OK):**
        *   **Content-Type:** `application/json`
        *   **Body:** A JSON object containing a `feed_posts` array. Each object in this array represents a post and includes standard post fields along with a `recommendation_reason`.
        *   **Example:**
            ```json
            {
                "feed_posts": [
                    {
                        "id": 123,
                        "title": "A Great Post",
                        "content": "This is the content of the post...",
                        "author_username": "friend_user",
                        "timestamp": "YYYY-MM-DDTHH:MM:SS",
                        "recommendation_reason": "Liked by your friend John Doe."
                    },
                    {
                        "id": 124,
                        "title": "Another Interesting Article",
                        "content": "Details about another article...",
                        "author_username": "another_user",
                        "timestamp": "YYYY-MM-DDTHH:MM:SS",
                        "recommendation_reason": "Trending in your groups."
                    }
                    // ... more post objects
                ]
            }
            ```
    *   **Error Responses:**
        *   **404 Not Found:** If the specified `user_id` does not exist.
            ```json
            {
                "message": "User <user_id> not found"
            }
            ```
            *(The exact message might vary slightly based on Flask-RESTful's error handling for `get_or_404`)*

*   **GET /api/personalized-feed**
    *   **Description:** Provides a personalized feed of content (posts, events, polls) for the authenticated user, sorted by recency. (This is a more general feed, typically for the logged-in user identified by JWT).
    *   **Authentication:** Required. Expects a JWT Bearer token in the `Authorization` header.
        *   Example: `Authorization: Bearer <your_jwt_access_token>`
    *   **Success Response (200 OK):**
        *   **Content-Type:** `application/json`
        *   **Body:** A JSON array named `feed_items`. Each item in the array represents a piece of content and includes at least:
            *   `type`: String - Identifies the type of content (e.g., "post", "event", "poll").
            *   `timestamp`: String - ISO 8601 formatted timestamp. This is used to sort the feed, with the most recent items appearing first. For posts, this is the post's creation/update time. For events and polls, this is their creation time.
            *   `id`: Integer - The unique ID of the content item.
        *   **Post Item Structure (`type: "post"`)**:
            *   `title`: String - The title of the post.
            *   `content`: String - The main content of the post.
            *   `author_username`: String - Username of the post's author.
            *   `reason`: String - A brief explanation of why this post is recommended (e.g., "Liked by a friend", "Trending").
            *   *(Other standard post fields may be present)*
        *   **Event Item Structure (`type: "event"`)**:
            *   `title`: String - The title of the event.
            *   `description`: String - Description of the event.
            *   `date`: String - The date of the event (e.g., "YYYY-MM-DD").
            *   `time`: String - The time of the event (e.g., "HH:MM").
            *   `location`: String - The location of the event.
            *   `organizer_username`: String - Username of the event's organizer.
            *   *(Other standard event fields may be present)*
        *   **Poll Item Structure (`type: "poll"`)**:
            *   `question`: String - The main question of the poll.
            *   `creator_username`: String - Username of the poll's creator.
            *   `options`: Array of objects - Each object represents a poll option and contains:
                *   `id`: Integer - ID of the option.
                *   `text`: String - Text of the option.
                *   `vote_count`: Integer - Number of votes this option has received.
            *   *(Other standard poll fields may be present)*
        *   **Example `feed_items` Array:**
            ```json
            {
                "feed_items": [
                    {
                        "type": "post",
                        "id": 123,
                        "timestamp": "2024-03-15T10:30:00Z",
                        "title": "Exploring New APIs",
                        "content": "A deep dive into new API development techniques...",
                        "author_username": "jane_doe",
                        "reason": "Liked by your friend John."
                    },
                    {
                        "type": "event",
                        "id": 78,
                        "timestamp": "2024-03-14T15:00:00Z",
                        "title": "Tech Meetup Vol. 5",
                        "description": "Join us for the latest in tech.",
                        "date": "2024-03-20",
                        "time": "18:00",
                        "location": "Community Hall",
                        "organizer_username": "tech_guru"
                    },
                    {
                        "type": "poll",
                        "id": 45,
                        "timestamp": "2024-03-13T09:00:00Z",
                        "question": "What's your favorite programming language?",
                        "creator_username": "code_master",
                        "options": [
                            {"id": 101, "text": "Python", "vote_count": 55},
                            {"id": 102, "text": "JavaScript", "vote_count": 40}
                        ]
                    }
                ]
            }
            ```
    *   **Error Responses:**
        *   **401 Unauthorized:** If the JWT token is missing, invalid, or expired.
            ```json
            {
                "msg": "Missing Authorization Header" // Or other JWT-related error messages
            }
            ```

### Posts API

*   **GET /api/posts**
    *   Description: Retrieves a list of all posts.
    *   Authentication: Not required.
    *   Response:
        ```json
        {
            "posts": [
                {
                    "id": 1,
                    "title": "My First Post",
                    "content": "This is the content of my first post.",
                    "timestamp": "2023-10-27T10:00:00",
                    "last_edited": null,
                    "user_id": 1,
                    "author_username": "demo"
                }
                // ... other posts
            ]
        }
        ```

*   **GET /api/posts/<post_id>**
    *   Description: Retrieves a specific post by ID.
    *   Authentication: Not required.
    *   Response (Example):
        ```json
        {
            "post": {
                "id": 1,
                "title": "My First Post",
                // ... other fields
            }
        }
        ```

*   **POST /api/posts**
    *   Description: Creates a new post.
    *   Authentication: Required (JWT Bearer Token).
    *   Request Body:
        ```json
        {
            "title": "New API Post",
            "content": "Content for the new post from API."
        }
        ```
    *   Response (Success - 201 Created):
        ```json
        {
            "message": "Post created successfully",
            "post": {
                "id": 2,
                "title": "New API Post",
                "content": "Content for the new post from API.",
                // ... other fields
            }
        }
        ```

*   **PUT /api/posts/<post_id>**
    *   Description: Updates an existing post. Only the author of the post can update it.
    *   Authentication: Required (JWT Bearer Token).
    *   Request Body:
        ```json
        {
            "title": "Updated Post Title",
            "content": "Updated content."
        }
        ```
    *   Response (Success - 200 OK):
        ```json
        {
            "message": "Post updated successfully",
            "post": {
                "id": 1,
                "title": "Updated Post Title",
                "content": "Updated content."
                // ... other fields
            }
        }
        ```

*   **DELETE /api/posts/<post_id>**
    *   Description: Deletes a post. Only the author of the post can delete it.
    *   Authentication: Required (JWT Bearer Token).
    *   Response (Success - 200 OK):
        ```json
        {
            "message": "Post deleted successfully"
        }
        ```

### "On This Day" API

*   **GET /api/onthisday**
    *   **Description:** Retrieves posts and events created by the authenticated user that occurred on the current month and day in previous years.
    *   **Authentication:** Required (JWT Token). The token should be passed in the `Authorization` header as a Bearer token (e.g., `Authorization: Bearer <YOUR_JWT_TOKEN>`).
    *   **Successful Response (200 OK):**
        A JSON object containing two lists: `on_this_day_posts` and `on_this_day_events`.
        ```json
        {
          "on_this_day_posts": [
            {
              "id": 101,
              "title": "My Throwback Post Title",
              "content": "Content of the post from a past year...",
              "timestamp": "2022-10-26T10:30:00",
              "author_username": "current_user",
              // ... other post fields ...
            }
          ],
          "on_this_day_events": [
            {
              "id": 55,
              "title": "Annual Past Event",
              "description": "Details of an event that happened on this day in a previous year...",
              "date": "2021-10-26",
              "time": "15:00",
              "organizer_username": "current_user",
              // ... other event fields ...
            }
          ]
        }
        ```
        *(Note: The exact fields returned for posts and events depend on their respective `to_dict()` methods in `models.py`.)*
    *   **Error Responses:**
        *   `401 Unauthorized`: If the JWT token is missing or invalid.
            ```json
            {
                "msg": "Missing Authorization Header" // Or other JWT error messages like "Token has expired"
            }
            ```

*   **POST /api/posts/{post_id}/comments**
    *   **Description:** Adds a new comment to a specific post.
    *   **Authentication:** Required (JWT Bearer token in Authorization header).
    *   **Path Parameters:**
        *   `post_id` (integer): The ID of the post to comment on.
    *   **Request Body:** JSON object with:
        *   `content` (string, required): The text content of the comment.
    *   **Example Request:**
        ```json
        {
            "content": "This is a great post!"
        }
        ```
    *   **Success Response (201 Created):**
        ```json
        {
            "message": "Comment created successfully",
            "comment": {
                "id": 123,
                "content": "This is a great post!",
                "user_id": 1,
                "author_username": "testuser",
                "post_id": 1,
                "timestamp": "YYYY-MM-DDTHH:MM:SS.ffffff"
            }
        }
        ```
    *   **Error Responses:**
        *   `400 Bad Request`: If 'content' is missing.
            ```json
            {
                "message": "Comment content cannot be blank"
            }
            ```
        *   `401 Unauthorized`: If JWT token is missing or invalid.
        *   `404 Not Found`: If the post or user (from token) is not found.
            ```json
            {
                "message": "Post not found"
            }
            ```
            or
            ```json
            {
                "message": "User not found"
            }
            ```

### Events API

*   **GET /api/events**
    *   Description: Retrieves a list of all events.
    *   Authentication: Not required.
    *   Response (Example):
        ```json
        {
            "events": [
                {
                    "id": 1,
                    "title": "Community Meetup",
                    "description": "Annual community gathering.",
                    "date": "2023-11-15",
                    "time": "18:00",
                    "location": "Community Hall",
                    "created_at": "2023-10-20T14:30:00",
                    "user_id": 1,
                    "organizer_username": "demo"
                }
                // ... other events
            ]
        }
        ```

*   **GET /api/events/<event_id>**
    *   Description: Retrieves a specific event by ID.
    *   Authentication: Not required.
    *   Response (Example):
        ```json
        {
            "event": {
                "id": 1,
                "title": "Community Meetup",
                // ... other fields
            }
        }
        ```

*   **POST /api/events**
    *   Description: Creates a new event.
    *   Authentication: Required (JWT Bearer Token).
    *   Request Body:
        ```json
        {
            "title": "New Tech Talk",
            "description": "A talk on new technologies.",
            "date": "2023-12-01",
            "time": "19:00",
            "location": "Online"
        }
        ```
    *   Response (Success - 201 Created):
        ```json
        {
            "message": "Event created successfully",
            "event": {
                "id": 2,
                "title": "New Tech Talk",
                // ... other fields
            }
        }
        ```
