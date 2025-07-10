# AGENTS.md

This document provides guidelines for agents working on the Flask Social App codebase.

## Application Overview

The Flask Social App is a feature-rich social media application built with Python and Flask. It includes functionalities such as:

- User authentication (registration, login, logout)
- User profiles with profile pictures, bios, and activity feeds
- Friendship system (sending, accepting, rejecting requests, friend lists)
- Content creation (blog posts, comments, image uploads)
- Real-time features (live activity feeds, real-time comment updates, real-time direct messaging, real-time group chat)
- Social interactions (liking posts, post reactions, sharing posts, bookmarking posts)
- Event management (creating events, RSVPing)
- User groups with real-time chat
- Polls
- Private messaging
- File sharing
- Content series (grouping blog posts)
- Recommendations (users, posts, groups, events, polls, hashtags)
- "On This Day" feature (revisiting past content)
- Content moderation (flagging, moderator dashboard)
- RESTful API for programmatic access
- Server-Sent Events (SSE) for real-time communication updates. (Chat may use WebSockets independently if Flask-SocketIO is fully removed)

The application uses a Flask backend, SQLAlchemy for database interactions, and Jinja2 for templating.

## Best Practices for Agents

### 1. Code Style and Conventions

- **Follow PEP 8**: Adhere to the Python Enhancement Proposal 8 (PEP 8) style guide for Python code. Use tools like `autopep8` or `black` for automatic formatting.
- **Consistency**: Maintain consistency with the existing codebase in terms of naming conventions, variable declarations, and overall structure.
- **Readability**: Write clear, concise, and well-commented code. Use meaningful variable and function names.
- **Modularity**: Break down complex logic into smaller, reusable functions or modules.
- **Flask Blueprints**: Organize routes and views using Flask Blueprints for better structure, especially for distinct features.
- **Database Migrations**: Use Alembic for database schema migrations. Ensure migrations are reversible and tested.
- **Error Handling**: Implement robust error handling. Use specific exception types and provide informative error messages.
- **Security**:
    - Sanitize all user inputs to prevent XSS, SQL injection, and other vulnerabilities.
    - Use Flask-Login for managing user sessions securely.
    - Be mindful of CSRF protection, especially for forms.
    - Store sensitive information like API keys and database credentials securely (e.g., using environment variables or a config file not committed to the repository).

### 2. Testing Guidelines

- **Unit Tests**: Write unit tests for all new functions, classes, and significant pieces of logic. Aim for high test coverage.
    - Focus on testing individual components in isolation.
    - Use the `unittest` or `pytest` framework. The existing tests primarily use `unittest`.
    - Mock external dependencies (like database calls, external APIs) where appropriate.
- **Integration Tests**: Write integration tests to verify interactions between different components of the application (e.g., API endpoints interacting with database models).
- **End-to-End Tests**: Consider end-to-end tests for critical user flows, though these can be more complex to maintain.
- **Test Location**: Keep tests in the `tests/` directory, mirroring the structure of the application code.
- **Running Tests**: Ensure all tests pass before submitting any changes. Familiarize yourself with how to run the test suite (typically `python -m unittest discover tests` or similar).
- **Test Naming**: Follow consistent naming conventions for test files (e.g., `test_feature.py`) and test methods (e.g., `test_specific_behavior`).

### 3. Commit Message Guidelines

Follow the conventional commit message format:

```
feat: Add user profile bio editing

- Implement the functionality for users to edit their profile bio.
- Add a new route `/profile/edit_bio` (POST).
- Update the user profile template to include an edit button and form.
- Add unit tests for the bio editing logic.
```

- **Type**: Use a prefix like `feat` (new feature), `fix` (bug fix), `docs` (documentation), `style` (code style changes), `refactor` (code refactoring), `test` (adding or modifying tests), `chore` (build process, tooling).
- **Subject Line**: Keep it concise (around 50 characters). Use the imperative mood (e.g., "Add feature" not "Added feature" or "Adds feature").
- **Body (Optional but Recommended)**: Provide more details about the changes. Explain *what* was changed and *why*. Break down the changes into bullet points if necessary.
- **Reference Issues**: If the commit addresses a specific issue, reference it in the commit message (e.g., "Closes #123").

### 4. Branching Strategy

- **Main Branch**: The `main` (or `master`) branch should always represent a stable, production-ready state. Direct commits to `main` are generally discouraged.
- **Feature Branches**: Create a new branch for each new feature or bug fix.
    - Branch off from the latest `main` branch.
    - Use descriptive branch names (e.g., `feat/user-profile-editing`, `fix/login-bug`).
- **Pull Requests (PRs)**: Once a feature or fix is complete (including tests), open a Pull Request to merge the feature branch into `main`.
    - Ensure the PR title and description are clear and follow similar guidelines to commit messages.
    - Reference any related issues.

### 5. Code Review Process

- **Request Reviews**: Request reviews from at least one other agent before merging a PR.
- **Constructive Feedback**: Provide and receive feedback constructively. Focus on the code and adherence to guidelines.
- **Address Comments**: Address all review comments and ensure discussions are resolved before merging.
- **Automated Checks**: Ensure any automated checks (linters, tests in CI/CD pipeline) pass before merging.
- **Merge Strategy**: Use squash merges or rebase and merge to keep the `main` branch history clean, depending on team preference.

### 6. API Design (for API-related changes)

- **RESTful Principles**: Adhere to RESTful design principles for API endpoints.
- **Clear Naming**: Use clear and consistent naming for endpoints and resources.
- **HTTP Methods**: Use appropriate HTTP methods (GET, POST, PUT, DELETE, etc.).
- **Status Codes**: Return appropriate HTTP status codes (200, 201, 400, 401, 403, 404, 500, etc.).
- **JSON Payloads**: Use JSON for request and response payloads.
- **Versioning**: Consider API versioning if making breaking changes (e.g., `/api/v1/resource`).
- **Authentication**: Secure API endpoints appropriately, typically using JWT or OAuth.
- **Documentation**: Document API endpoints (e.g., using Swagger/OpenAPI or in the README/API documentation file). The existing README has a good start on this.

### 7. Real-time Features (Server-Sent Events & WebSockets for Chat)

- **Event Naming**: Use clear and consistent names for SSE event types. For WebSocket messages, define a clear message structure.
- **Stream/Channel Management**: For SSE, use distinct event stream URLs for different resources (e.g., `/post-stream/<post_id>`, `/chat-stream/<room_id>`). For WebSockets, manage channels or rooms appropriately if used for chat.
- **Payloads**: Keep data payloads concise and relevant for both SSE and WebSocket messages.
- **Error Handling**: Implement error handling for SSE connections and WebSocket communications on both client and server sides.
- **Security**: Be mindful of authentication and authorization for accessing SSE streams and sending/receiving WebSocket messages.
- **Documentation**: Document SSE event types and their payloads, and any WebSocket message formats, as seen in the README.

### 8. Dependency Management

- **`requirements.txt`**: Keep the `requirements.txt` file up-to-date with all project dependencies.
- **Virtual Environments**: Always use a virtual environment (`venv`) for development to isolate project dependencies.
- **Updating Dependencies**: Be cautious when updating dependencies. Test thoroughly to ensure no breaking changes are introduced.

### 9. Keeping Up-to-Date

- Regularly pull the latest changes from the `main` branch into your feature branches to avoid large merge conflicts:
  ```bash
  git checkout main
  git pull origin main
  git checkout your-feature-branch
  git merge main
  ```
  Or, preferably, use rebase:
  ```bash
  git checkout main
  git pull origin main
  git checkout your-feature-branch
  git rebase main
  ```

By following these guidelines, we can ensure the codebase remains maintainable, scalable, and of high quality.
