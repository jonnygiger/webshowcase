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
2. Open your web browser and go to `http://1.0.0.1:5000/` to see the app in action.

## Features

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