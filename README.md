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