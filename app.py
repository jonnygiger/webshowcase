import os
from flask import Flask, render_template, request, session, redirect, url_for, flash, send_from_directory
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = 'supersecretkey'
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'uploads')
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}

# User storage
users = {
    "demo": generate_password_hash("password123")
}

# Ensure the upload folder exists
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# Decorator for requiring login
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            flash('You need to be logged in to access this page.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def hello_world():
    return render_template('index.html')

@app.route('/child')
def child():
    return render_template('child_template.html')

@app.route('/user/<username>')
def user_profile(username):
    return render_template('user.html', username=username)

@login_required
@app.route('/todo', methods=['GET', 'POST'])
def todo():
    if 'todos' not in session:
        session['todos'] = []

    if request.method == 'POST':
        task = request.form['task']
        session['todos'].append(task)
        session.modified = True
        return redirect(url_for('todo'))

    return render_template('todo.html', todos=session.get('todos', []))

@login_required
@app.route('/todo/clear')
def clear_todos():
    session.pop('todos', None)
    return redirect(url_for('todo'))

@login_required
@app.route('/gallery/upload', methods=['GET', 'POST'])
def upload_image():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part', 'error')
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            flash('No selected file', 'error')
            return redirect(request.url)
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            flash('Image successfully uploaded!', 'success')
            return redirect(url_for('gallery')) # Redirect to gallery page
        else:
            flash('Allowed image types are png, jpg, jpeg, gif', 'error')
            return redirect(request.url)
    return render_template('upload_image.html')

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/gallery')
def gallery():
    image_files = []
    if os.path.exists(app.config['UPLOAD_FOLDER']):
        for filename in os.listdir(app.config['UPLOAD_FOLDER']):
            if allowed_file(filename): # Use the existing allowed_file function
                image_files.append(filename)
    return render_template('gallery.html', images=image_files)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password_candidate = request.form['password']

        if username in users and check_password_hash(users.get(username), password_candidate):
            session['logged_in'] = True
            session['username'] = username
            flash('You are now logged in!', 'success')
            return redirect(url_for('hello_world')) # Or a dashboard page if you create one
        else:
            flash('Invalid login.', 'danger')
            return render_template('login.html')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    session.pop('username', None)
    flash('You are now logged out.', 'success')
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
