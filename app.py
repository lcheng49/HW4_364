# An application in Flask where you can log in and create user accounts to save Gif collections
# SI 364 - F18 - HW4

# TODO 364: Check out the included file giphy_api_key.py and follow the instructions in TODOs there before proceeding to view functions.

# TODO 364: All templates you need are provided and should not be edited. However, you will need to inspect the templates that exist in order to make sure you send them the right data!

# Import statements
import os
import requests
import json
from giphy_api_key import api_key
from flask import Flask, render_template, session, redirect, request, url_for, flash
from flask_script import Manager, Shell
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, FileField, PasswordField, BooleanField, SelectMultipleField, ValidationError
from wtforms.validators import Required, Length, Email, Regexp, EqualTo
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate, MigrateCommand
from werkzeug.security import generate_password_hash, check_password_hash

# Imports for login management
from flask_login import LoginManager, login_required, logout_user, login_user, UserMixin, current_user
from werkzeug.security import generate_password_hash, check_password_hash

# Application configurations
app = Flask(__name__)
app.debug = True
app.use_reloader = True
app.config['SECRET_KEY'] = 'hardtoguessstring'
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get('DATABASE_URL') or "postgresql://localhost/lukchengHW4db" # TODO 364: You should edit this to correspond to the database name YOURUNIQNAMEHW4db and create the database of that name (with whatever your uniqname is; for example, my database would be jczettaHW4db). You may also need to edit the database URL further if your computer requires a password for you to run this.
app.config['SQLALCHEMY_COMMIT_ON_TEARDOWN'] = True
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# App addition setups
manager = Manager(app)
db = SQLAlchemy(app)
migrate = Migrate(app, db)
manager.add_command('db', MigrateCommand)

# Login configurations setup
login_manager = LoginManager()
login_manager.session_protection = 'strong'
login_manager.login_view = 'login'
login_manager.init_app(app) # set up login manager

########################
######## Models ########
########################

## Association tables
# NOTE - 364: You may want to complete the models tasks below BEFORE returning to build the association tables! That will making doing this much easier.
# NOTE: Remember that setting up association tables in this course always has the same structure! Just make sure you refer to the correct tables and columns!

tags = db.Table('tags', db.Column('searchTerms_id', db.Integer, db.ForeignKey('searchTerms.id')), db.Column('gif_id', db.Integer, db.ForeignKey('gifs.id')))
user_collection = db.Table('user_collection',db.Column('user_id', db.Integer, db.ForeignKey('gifs.id')),db.Column('collection_id',db.Integer, db.ForeignKey('personalGifCollection.id')))

## User-related Models

# Special model for users to log in
class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(255), unique=True, index=True)
    email = db.Column(db.String(64), unique=True, index=True)
    password_hash = db.Column(db.String(128))
    PersonalGifCollection = db.relationship('PersonalGifCollection', backref = "User")

    @property
    def password(self):
        raise AttributeError('password is not a readable attribute')

    @password.setter
    def password(self, password):
        self.password_hash = generate_password_hash(password)

    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)

## DB load function
## Necessary for behind the scenes login manager that comes with flask_login capabilities! Won't run without this.
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id)) # returns User object or None

# TODO 364: Read through all the models tasks before beginning them so you have an understanding of what the database structure should be like. Consider thinking about it as a whole and drawing it out before you write this code.

# Model to store gifs
class Gif(db.Model):
    __tablename__ = 'gifs'
    id = db.Column(db.Integer, primary_key = True)
    title = db.Column(db.String(128))
    embedURL = db.Column(db.String(256))

    def __repr__(self):
        return "{}: {}".format(self.title, self.embedURL)

# Model to store a personal gif collection
class PersonalGifCollection(db.Model):
    __tablename__ = "personalGifCollection"
    id = db.Column(db.Integer, primary_key = True)
    name = db.Column(db.String(255))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    gifs = db.relationship('Gif', secondary=user_collection, backref=db.backref('personalGifCollections', lazy = 'dynamic'), lazy = 'dynamic') #fix

class SearchTerm(db.Model):
    __tablename__ = 'searchTerms'
    id = db.Column(db.Integer, primary_key=True)
    term = db.Column(db.String(32), unique = True)
    gifs = db.relationship('Gif', secondary=tags, backref = db.backref('searchTerms', lazy='dynamic'), lazy = 'dynamic')

    def __repr__(self):
        return "{}".format(self.term)


########################
######## Forms #########
########################

# Provided
class RegistrationForm(FlaskForm):
    email = StringField('Email:', validators=[Required(),Length(1,64),Email()])
    username = StringField('Username:',validators=[Required(),Length(1,64),Regexp('^[A-Za-z][A-Za-z0-9_.]*$',0,'Usernames must have only letters, numbers, dots or underscores')])
    password = PasswordField('Password:',validators=[Required(),EqualTo('password2',message="Passwords must match")])
    password2 = PasswordField("Confirm Password:",validators=[Required()])
    submit = SubmitField('Register User')

    #Additional checking methods for the form
    def validate_email(self,field):
        if User.query.filter_by(email=field.data).first():
            raise ValidationError('Email already registered.')

    def validate_username(self,field):
        if User.query.filter_by(username=field.data).first():
            raise ValidationError('Username already taken')

# Provided
class LoginForm(FlaskForm):
    email = StringField('Email', validators=[Required(), Length(1,64), Email()])
    password = PasswordField('Password', validators=[Required()])
    remember_me = BooleanField('Keep me logged in')
    submit = SubmitField('Log In')

# TODO 364: The following forms for searching for gifs and creating collections are provided and should not be edited. You SHOULD examine them so you understand what data they pass along and can investigate as you build your view functions in TODOs below.
class GifSearchForm(FlaskForm):
    search = StringField("Enter a term to search GIFs", validators=[Required()])
    submit = SubmitField('Submit')

class CollectionCreateForm(FlaskForm):
    name = StringField('Collection Name',validators=[Required()])
    gif_picks = SelectMultipleField('GIFs to include')
    submit = SubmitField("Create Collection")

########################
### Helper functions ###
########################

def get_gifs_from_giphy(search_string):
    """ Returns data from Giphy API with up to 5 gifs corresponding to the search input"""
    baseurl = "https://api.giphy.com/v1/gifs/search?q=" + search_string + "&api_key=" + api_key + "&limit=5"
    res = json.loads(requests.get(baseurl).text)
    return res['data']

# Provided
def get_gif_by_id(id):
    """Should return gif object or None"""
    g = Gif.query.filter_by(id=id).first()
    return g

def get_or_create_gif(title, url):
    """Always returns a Gif instance"""
    g = Gif.query.filter_by(title = title).first()
    if g:
        return g
    else:
        temp = Gif(title=title, embedURL = url)
        db.session.add(temp)
        db.session.commit()
        return temp

def get_or_create_search_term(term):
    """Always returns a SearchTerm instance"""
    sTerm = SearchTerm.query.filter_by(term = term).first()
    if sTerm:
        return sTerm
    else:
        sTerm = SearchTerm(term = term)
        gifList = get_gifs_from_giphy(term)
        for x in gifList:
            temp = get_or_create_gif(x['title'], x['embed_url'])
            sTerm.gifs.append(temp)
        db.session.add(sTerm)
        db.session.commit()
        return sTerm

def get_or_create_collection(name, current_user, gif_list=[]):
    """Always returns a PersonalGifCollection instance"""
    collect = PersonalGifCollection.query.filter_by(name = name, user_id = current_user.id).first()
    if collect:
        return collect
    else:
        new_collect = PersonalGifCollection(name = name, user_id = current_user.id, gifs = [])
        for x in gif_list:
            new_collect.gifs.append(x)
        db.session.add(new_collect)
        db.session.commit()
        return new_collect

########################
#### View functions ####
########################

## Error handling routes
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500


## Login-related routes - provided
@app.route('/login',methods=["GET","POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user is not None and user.verify_password(form.password.data):
            login_user(user, form.remember_me.data)
            return redirect(request.args.get('next') or url_for('index'))
        flash('Invalid username or password.')
    return render_template('login.html',form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out')
    return redirect(url_for('index'))

@app.route('/register',methods=["GET","POST"])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(email=form.email.data,username=form.username.data,password=form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('You can now log in!')
        return redirect(url_for('login'))
    return render_template('register.html',form=form)

@app.route('/secret')
@login_required
def secret():
    return "Only authenticated users can do this! Try to log in or contact the site admin."

## Other routes
@app.route('/', methods=['GET', 'POST'])
def index():
    form = GifSearchForm()
    if form.validate_on_submit():
        sTerm = get_or_create_search_term(form.search.data)
        return redirect(url_for('search_results',search_term=sTerm))
    return render_template('index.html',form=form)

# Provided
@app.route('/gifs_searched/<search_term>')
def search_results(search_term):
    term = SearchTerm.query.filter_by(term=search_term).first()
    relevant_gifs = term.gifs.all()
    return render_template('searched_gifs.html',gifs=relevant_gifs,term=term)

@app.route('/search_terms')
def search_terms():
    sTerm = SearchTerm.query.all()
    return render_template('search_terms.html', all_terms = sTerm)

# Provided
@app.route('/all_gifs')
def all_gifs():
    gifs = Gif.query.all()
    return render_template('all_gifs.html',all_gifs=gifs)

@app.route('/create_collection',methods=["GET","POST"])
@login_required
def create_collection():
    form = CollectionCreateForm()
    gifs = Gif.query.all()
    choices = [(g.id, g.title) for g in gifs]
    form.gif_picks.choices = choices
    if request.method == 'POST':
        get_or_create_collection(form.name.data, current_user, [get_gif_by_id(int(id)) for id in form.gif_picks.data])
        return redirect(url_for('collections'))
    return render_template('create_collection.html', form = form)

@app.route('/collections',methods=["GET","POST"])
@login_required
def collections():
    collect = PersonalGifCollection.query.filter_by(user_id = current_user.id)
    return render_template('collections.html', collections = collect)

# Provided
@app.route('/collection/<id_num>')
def single_collection(id_num):
    id_num = int(id_num)
    collection = PersonalGifCollection.query.filter_by(id=id_num).first()
    gifs = collection.gifs.all()
    return render_template('collection.html',collection=collection, gifs=gifs)

if __name__ == '__main__':
    db.create_all()
    manager.run()
