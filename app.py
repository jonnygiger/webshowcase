from flask import Flask, render_template, request, session, redirect, url_for

app = Flask(__name__)
app.config['SECRET_KEY'] = 'supersecretkey'

@app.route('/')
def hello_world():
    return render_template('index.html')

@app.route('/child')
def child():
    return render_template('child_template.html')

@app.route('/user/<username>')
def user_profile(username):
    return render_template('user.html', username=username)

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

@app.route('/todo/clear')
def clear_todos():
    session.pop('todos', None)
    return redirect(url_for('todo'))

if __name__ == '__main__':
    app.run(debug=True)
