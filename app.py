from flask import Flask, render_template, flash, request, redirect, url_for, session, logging
# from data import Posts
from flask_mysqldb import MySQL
from wtforms import Form, StringField, TextAreaField, PasswordField, validators
from passlib.hash import sha256_crypt
from functools import wraps
import redis
import datetime
import smtplib

r_server = redis.Redis('localhost')

app = Flask(__name__)

# Config MySQL
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = 'mysqlpass'
app.config['MYSQL_DB'] = 'buzzinga'
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'

#init MySQL
mysql = MySQL(app)

# Posts = Posts()

@app.route('/')
def index():
    return render_template('home.html')

@app.route('/about')
def about():
    return render_template('about.html')

# Check if user logged in
def is_logged_in(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if 'logged_in' in session:
            return f(*args, **kwargs)
        else:
            flash('Unauthorized access', 'danger')
            return redirect(url_for('login'))
    return wrap

@app.route('/feed')
@is_logged_in
def feed():
    # Create cursor
    cur = mysql.connection.cursor()

    # Get articles
    result = cur.execute("SELECT * FROM posts")

    posts = cur.fetchall()

    if result > 0:
        return render_template('feed.html', posts=posts)
    else:
        msg = 'No Posts Found'
        return render_template('feed.html', msg=msg)
    # Close connection
    cur.close()

@app.route('/post/<string:id>')
@is_logged_in
def post(id):
    # Create cursor
    cur = mysql.connection.cursor()

    # Get articles
    result = cur.execute("SELECT * FROM posts where id = %s", [id])

    post = cur.fetchone()
    return render_template('post.html', post = post )

class RegisterForm(Form):
    name = StringField('Name', [validators.Length(min=1, max=50)])
    username = StringField('Username', [validators.Length(min=4, max=25)])
    email = StringField('Email', [validators.Length(min=6, max=50)])
    password = PasswordField('Password', [
    validators.DataRequired(),
    validators.EqualTo('confirm', message='Passwords do not match')
    ])
    confirm = PasswordField('Confirm Password')

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm(request.form)
    if request.method == 'POST' and form.validate():
        name = form.name.data
        email = form.email.data
        username = form.username.data
        password = sha256_crypt.encrypt(str(form.password.data))

        # Create cursor
        cur = mysql.connection.cursor()

        cur.execute("INSERT INTO users(name,email,username,password) values(%s, %s, %s, %s)", (name, email, username, password))

        #commit to db
        mysql.connection.commit()

        #close connection
        cur.close()

        flash("your account is registered please log in", "Success wow")
        return redirect(url_for('login'))

    return render_template('register.html', form=form)

# User login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # Get Form Fields
        username = request.form['username']
        password_candidate = request.form['password']

        # Create cursor
        cur = mysql.connection.cursor()

        # Get user by username
        result = cur.execute("SELECT * FROM users WHERE username = %s", [username])

        if result > 0:
            # Get stored hash
            data = cur.fetchone()
            password = data['password']

            # Compare Passwords
            if sha256_crypt.verify(password_candidate, password):
                # Passed
                session['logged_in'] = True
                session['username'] = username
                app.logger.info('Password matched')

                user_dob = data['dob']
                todays_date = user_dob.today()
                print(user_dob,"   ", todays_date)
                if(user_dob.month == todays_date.month and user_dob.day == todays_date.day):
                    # #for email
                    # server = smtplib.SMTP('smtp.gmail.com',587)
                    # server.starttls()
                    # server.login("@gmail.com","pass")
                    # msg = "hi bro"
                    # server.sendmail("@gmail.com","@iiitd.ac.in",msg)
                    # server.quit()

                flash('You are now logged in', 'success')
                return redirect(url_for('dashboard'))
            else:
                app.logger.info('password not matched')
                error = 'Invalid login'
                return render_template('login.html', error=error)
            # Close connection
            cur.close()
        else:
            error = 'Username not found'
            return render_template('login.html', error=error)

    return render_template('login.html')

#logout
@app.route('/logout')
@is_logged_in
def logout():
    session.clear()
    flash('You are now logged out', 'success')
    return redirect(url_for('login'))

# Dashboard
@app.route('/dashboard')
@is_logged_in
def dashboard():

    v = r_server.get('cached_posts')
    if v:
        posts = eval(v)
        result = len(posts)
        print("posts came from redis")
    else:
        # Create cursor
        cur = mysql.connection.cursor()

        # Get articles
        result = cur.execute("SELECT * FROM posts")

        posts = cur.fetchall()

        r_server.set('cached_posts',posts)
        r_server.expire("cached_posts",10)
        print("posts came from db")


    if result > 0:
        return render_template('dashboard.html', posts=posts)
    else:
        msg = 'No Posts Found'
        return render_template('dashboard.html', msg=msg)
    # Close connection
    cur.close()

class PostForm(Form):
    title = StringField('Title', [validators.Length(min=1, max=200)])
    body = TextAreaField('Body', [validators.Length(min=5)])



# Add a new post
@app.route('/add_post', methods=['GET', 'POST'])
@is_logged_in
def add_post():
    form = PostForm(request.form)
    if request.method == 'POST' and form.validate():
        title = form.title.data
        body = form.body.data

        # Create Cursor
        cur = mysql.connection.cursor()

        # Execute
        cur.execute("INSERT INTO posts(title, body, author) VALUES(%s, %s, %s)",(title, body, session['username']))

        # Commit to DB
        mysql.connection.commit()

        #Close connection
        cur.close()

        flash('Post Created', 'success')

        return redirect(url_for('dashboard'))

    return render_template('add_post.html', form=form)

# Edit Article
@app.route('/edit_post/<string:id>', methods=['GET', 'POST'])
@is_logged_in
def edit_post(id):
    # Create cursor
    cur = mysql.connection.cursor()

    # Get article by id
    result = cur.execute("SELECT * FROM posts WHERE id = %s and author=%s", [id,session['username']])

    if result <= 0:
        flash('You cannot edit someone\'s else post','danger')
        return redirect(url_for('dashboard'))

    else:
        post = cur.fetchone()
        cur.close()
        # Get form
        form = PostForm(request.form)

        # Populate article form fields
        form.title.data = post['title']
        form.body.data = post['body']

        if request.method == 'POST' and form.validate():
            title = request.form['title']
            body = request.form['body']

            # Create Cursor
            cur = mysql.connection.cursor()
            app.logger.info(title)
            # Execute
            result = cur.execute ("UPDATE posts SET title=%s, body=%s WHERE id=%s",(title, body, id))

            # Commit to DB
            mysql.connection.commit()

            #Close connection
            cur.close()
            flash('Post updated successfully','success')

            return redirect(url_for('dashboard'))

    return render_template('edit_post.html', form=form)

# Delete Article
@app.route('/delete_post/<string:id>', methods=['POST'])
@is_logged_in
def delete_post(id):
    # Create cursor
    cur = mysql.connection.cursor()

    # Execute
    result = cur.execute("DELETE FROM posts WHERE id = %s and author = %s", [id,session['username']])
    if(result > 0):
        flash('Post Deleted', 'success')
    else:
        flash('You cannot delete this post','danger')

    # Commit to DB
    mysql.connection.commit()

    #Close connection
    cur.close()


    return redirect(url_for('dashboard'))


class DobForm(Form):
    title = StringField('Title', [validators.Length(min=9, max=20)])

@app.route('/edit_bday')
@is_logged_in
def edit_bday():
    # Create cursor
    cur = mysql.connection.cursor()

    # Execute
    result = cur.execute("select dob from users where username = %s", [session['username']])
    if(result > 0):
        flash('Post Deleted', 'success')
    else:
        flash('You cannot delete this post','danger')

    # Commit to DB
    mysql.connection.commit()

    #Close connection
    cur.close()

    return render_template('edit_bday.html')
    # return "feature yet to be implemented"

if __name__ == '__main__':
    app.run(debug=True)

app.secret_key='bigabc123'
