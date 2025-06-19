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

## Private Messaging

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

### In-App Notifications

To keep users informed about recent activity on the platform, an in-app notification system has been implemented.

*   **Purpose**: Alerts users to new content such as new blog posts, upcoming events, or recently created polls.
*   **How it Works**: A background task runs periodically (e.g., every minute) to scan for new content. When new items are found, notifications are generated.
*   **Accessing Notifications**: Logged-in users can find a "Notifications" link in the navigation bar, which leads to a page displaying all recent activity alerts, sorted by time.
*   **Flask Functionalities Demonstrated**:
    *   Integration with `APScheduler` for background task scheduling.
    *   Dynamic generation of user-facing alerts based on application events.
    *   New routes and templates for displaying notifications.

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
