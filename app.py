from flask import Flask, render_template, flash, request, redirect, url_for, session, logging
# from data import Posts
from flask_mysqldb import MySQL
from wtforms import Form, StringField, TextAreaField, PasswordField, validators, DateField
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
                if user_dob is not None:
                    todays_date = user_dob.today()
                    # print(user_dob,"   ", todays_date)
                    if(user_dob.month == todays_date.month and user_dob.day == todays_date.day):
                        #for email
                        server = smtplib.SMTP('smtp.gmail.com',587)
                        server.starttls()
                        server.login("whypeoplehackme@gmail.com","testaccountforme")
                        msg = "happy B'day bro"
                        server.sendmail("whypeoplehackme@gmail.com",data['email'],msg) #just put data['email'] in 2nd argument for sending wish to the user
                        server.quit()

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
        # print(posts)
        result = len(posts)
        print("posts came from redis")
    else:
        # Create cursor
        cur = mysql.connection.cursor()

        # Get articles
        # result = cur.execute("SELECT * FROM posts")
        result1 = cur.execute("select id from users where username = %s", [session['username']]);
        requested_id = cur.fetchone()['id']

        query = "select * from posts inner join (select username from (select t2.follower_id from (select following_id from friends where follower_id="  + str(requested_id) + ") as t1 inner join friends as t2 on t2.follower_id=t1.following_id union select id from users where username='" + session['username'] + "') as t3 inner join users on users.id=t3.follower_id) as t4 on posts.author = t4.username";

        # print(query)

        # print(query)
        result = cur.execute(query)

        posts = cur.fetchall()

        # print(posts)
        r_server.set('cached_posts',posts)
        r_server.expire("cached_posts",5)
        print("posts came from db")

        cur.close()


    cur = mysql.connection.cursor()

    result1 = cur.execute("select id from users where username = %s", [session['username']]);
    requested_id = cur.fetchone()['id']

    #need to perfrom a check first whether that user exist first or not
    # result1 = cur.execute("select use from users where username = %s", [username]);
    # requester_id = cur.fetchone()['id']

    query = "select username from users inner join (select t1.follower_id from (SELECT follower_id from friends where following_id = " + str(requested_id) + ") as t1"\
    + " left join" + " (select following_id from friends where follower_id = " + str(requested_id) + ") as t2 on t1.follower_id = t2.following_id where t2.following_id is NULL) as t3 on t3.follower_id = users.id"
    # print(query)
    result1 = cur.execute(query)

    requests = cur.fetchall()

    if result > 0:
        return render_template('dashboard.html', posts=posts, requests = requests)
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

        # Populate post form fields
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
    # dateofbirth = StringField('Dob', [validators.Length(min=9, max=20)])
    dateofbirth = DateField('Dob', format='%Y-%m-%d')


@app.route('/edit_bday', methods=['GET', 'POST'])
@is_logged_in
def edit_bday():
    # Create cursor
    cur = mysql.connection.cursor()

    # Execute
    result = cur.execute("select dob from users where username = %s", [session['username']])
    if(result > 0):
        dob = cur.fetchone()
        form = DobForm(request.form)
        form.dateofbirth.data = dob['dob']
        flash('you can edit your dob', 'success')

        if request.method == 'POST' and form.validate():
            dateofb = request.form['dateofbirth']
            # print(dateofb)

            # Create Cursor
            cur = mysql.connection.cursor()
            app.logger.info(dateofb)
            # Execute
            result = cur.execute ("UPDATE users SET dob=%s WHERE username=%s",(dateofb,session['username']))

            # Commit to DB
            mysql.connection.commit()

            #Close connection
            cur.close()
            flash('dob updated successfully','success')

            return redirect(url_for('dashboard'))
    else:
        flash('You cannot edit someone else dob','danger')

    # Commit to DB
    mysql.connection.commit()

    #Close connection
    cur.close()

    return render_template('edit_bday.html', form=form)
    # return "feature yet to be implemented"

@app.route('/profile/<username>', methods=['GET','POST'])
@is_logged_in
def profile(username):
    #create cursor
    cur = mysql.connection.cursor()

    # execute
    result = cur.execute("Select username from users where username=%s", [username])
    if result <= 0:
        flash("That user does not exist","danger")
        return redirect(url_for('dashboard'))
    else:
        # return "Welcome" + username
        profile = cur.fetchone()
        return render_template('profile.html', profile = profile )

    mysql.connection.commit()
    cur.close()

def is_already_friend(requester_id,requested_id,cur):
    result1 = cur.execute('select * from friends where follower_id=' + str(requester_id) + " and following_id=" + str(requested_id))
    print(result1)
    # print(cur.fetchone())
    if(result1 >0):
        result2 = cur.execute('select * from friends where follower_id=' + str(requested_id) + " and following_id=" + str(requester_id))
        print(result2)
        # print(cur.fetchone())
        if(result2 >0):
            print("here")
            return 1 # 1 = already a friend
        return 2 # 2 = you already sent friend request
    else:
        return 0 # not already a friend

def already_got_request(requester_id,requested_id,cur):
    result1 = cur.execute('select * from friends where follower_id=' + str(requested_id) + " and following_id=" + str(requester_id))
    if(result1 >0):
        return 1 # already got friend request from person,  but you did not accept
    else:
        return 0 # did not already get friend request



# Sending request
@app.route('/send_request/<string:username>', methods=['POST'])
@is_logged_in
def send_request(username):
    # Create cursor
    cur = mysql.connection.cursor()

    result = cur.execute("select id from users where username = %s", [session['username']]);
    requester_id = cur.fetchone()['id']
    #need to perfrom a check first whether that user exist first or not
    result = cur.execute("select id from users where username = %s", [username]);
    requested_id = cur.fetchone()['id']

    if(requester_id == requested_id):
        flash('you cannot send friend request to yourself','danger')
        mysql.connection.commit()
        cur.close()
        return redirect(url_for('dashboard'))

    elif( is_already_friend(requester_id,requested_id,cur) == 1 ):
        flash('you two are already friends','success')
        mysql.connection.commit()
        cur.close()
        return redirect(url_for('dashboard'))
    elif( is_already_friend(requester_id,requested_id,cur) == 2 ):
        flash('friend request already sent', 'danger')
        mysql.connection.commit()
        cur.close()
        return redirect(url_for('dashboard'))
    else:
        if( already_got_request(requester_id,requested_id,cur)==1 ):
            flash('Already got friend request from person, but you did not accept', 'danger')
            mysql.connection.commit()
            cur.close()
            return redirect(url_for('dashboard'))


    # print(requester_id, "  :  ", requested_id)

    # Execute
    result = cur.execute("insert into friends (follower_id, following_id) values (" + str(requester_id) + "," + str(requested_id) + ")" )
    if(result > 0):
        flash('friend request sent successfully', 'success')
    else:
        flash('You cannot send request to this user','danger')

    # Commit to DB
    mysql.connection.commit()

    #Close connection
    cur.close()

    return redirect(url_for('dashboard'))


# Accept Request
@app.route('/accept_request/<string:username>', methods=['POST'])
@is_logged_in
def accept_request(username):
    # Create cursor
    cur = mysql.connection.cursor()

    result = cur.execute("select id from users where username = %s", [session['username']]);
    requested_id = cur.fetchone()['id']
    #need to perfrom a check first whether that user exist first or not
    result = cur.execute("select id from users where username = %s", [username]);
    requester_id = cur.fetchone()['id']

    # Execute
    result = cur.execute( "insert into friends (follower_id, following_id) values (" + str(requested_id) + "," + str(requester_id) + ")" )
    if(result > 0):
        flash('Request Accepted', 'success')
    else:
        flash('You cannot accept this request','danger')

    # Commit to DB
    mysql.connection.commit()

    #Close connection
    cur.close()


    return redirect(url_for('dashboard'))


# Reject Request
@app.route('/reject_request/<string:username>', methods=['POST'])
@is_logged_in
def reject_request(username):

    # Create cursor
    cur = mysql.connection.cursor()

    result = cur.execute("select id from users where username = %s", [session['username']]);
    requested_id = cur.fetchone()['id']
    #need to perfrom a check first whether that user exist first or not
    result = cur.execute("select id from users where username = %s", [username]);
    requester_id = cur.fetchone()['id']

    # Execute
    result = cur.execute("DELETE FROM friends WHERE follower_id = " + str(requester_id) + " and following_id = " + str(requested_id))
    if(result > 0):
        flash('Rejected Request', 'success')
    else:
        flash('You cannot reject this request :P','danger')

    # Commit to DB
    mysql.connection.commit()

    #Close connection
    cur.close()


    return redirect(url_for('dashboard'))



if __name__ == '__main__':
    app.run(debug=True)

app.secret_key='bigabc123'
