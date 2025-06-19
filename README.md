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

### To-Do List

This application includes a simple To-Do list feature that demonstrates Flask's session handling and form processing capabilities.

*   **Route:** `/todo`
*   **Functionality:**
    *   View your current list of tasks.
    *   Add new tasks to the list using the provided form.
    *   Tasks are stored in your browser session.
*   **Clear Tasks:**
    *   **Route:** `/todo/clear`
    *   **Functionality:** Clears all tasks from your current session.

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
