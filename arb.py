from datetime import date as Date
from functools import wraps
from imaplib import IMAP4_SSL
from os.path import dirname, exists, join, realpath, isfile, isdir
from os import listdir, mkdir, remove, rmdir
from sys import exit
from urllib.parse import unquote

from flask import (
        Flask,
        request,
        session, 
        redirect,
        render_template,
        url_for
        )
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import InvalidRequestError
from qrcode import make as make_qrcode

try:
    from config import (
            username,
            password,
            secret_key,
            allowed_domain,
            imap_host,
            imap_port
    )
except:
    print('please check config.py')
    exit(1)

app = Flask(__name__)
app.secret_key = secret_key

PATH = dirname(realpath(__file__))
DB_PATH = join(PATH, 'arb.sqlite3')

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + DB_PATH
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class Room(db.Model):
    ID = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(), nullable=False)
    location = db.Column(db.String())
    description = db.Column(db.String())
    bookings = db.relationship('Booking', backref='Booking', lazy=True)

class Booking(db.Model):
    __table_args__ = (db.UniqueConstraint('date', 'period', 'room_id'),) # must be a tuple
    # contraint -> unique in date, period and room_id
    ID = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    period = db.Column(db.Integer, nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey('room.ID'), nullable=False)
    person = db.Column(db.String(), nullable=False)

def book(person, room_id, iso_date, period):
    db.session.add(
            Booking(
                person=person,
                room_id=room_id,
                date = Date.fromisoformat(iso_date),
                period=period
                )
            )
    try:
        db.session.commit()
        return True
    except InvalidRequestError:
        return False

def imap_auth(username, password):
    username = username.lower()
    if not username.endswith(allowed_domain):
        return False
    with IMAP4_SSL(host=imap_host, port=imap_port) as M:
        try:
            M.login(username, password)
            return True
        except:
            return False

# ----- SESSION
def admin_only(wrapped):
    @wraps(wrapped)
    def _request(*args, **kwargs):
        if 'admin' in session:
            return wrapped(*args, **kwargs)
        else:
            return redirect(url_for('login'))
    return _request

def logged_in(wrapped):
    @wraps(wrapped)
    def _request(*args, **kwargs):
        if 'user' in session:
            return wrapped(*args, **kwargs)
        else:
            return redirect(url_for('login'))
    return _request

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = request.form['username']
        pw = request.form['password']
        if request.form['username'] == username and request.form['password'] == password:
            session.permanent = True
            # ADMIN!
            session['admin'] = user
            return redirect(url_for('admin'))
        elif imap_auth(username=user,password=pw):
            session.permanent = True
            session['user'] = user.lower()
            return redirect(url_for('home'))
    return '''
        <!DOCTYPE html>
        <html>
            <head>
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
            </head>
            <body>
                <form action="" method="post">
                    <p><input type=text name=username placeholder="username">
                    <p><input type=password name=password placeholder="password">
                    <p><input type=submit value=Login>
                </form>
            </body>
        </html>
    '''

@app.route('/logout')
def logout():
    if 'admin' in session:
        session.pop('admin', None)
    else:
        session.pop('user', None)
    return redirect(url_for('home'))

@app.route('/')
def home():
    return 'home'

@logged_in
@app.route('/show/<ID>')
def show_room(ID):
    return 'showing {}'.format(ID)

@logged_in
@app.route('/book/<ID>', methods=['POST'])
def book_room(ID):
    period = request.form.get('period')
    iso_date = request.form.get('iso_date')
    person = session['user']
    if book(person=person, room_id=ID, iso_date=iso_date, period=period):
        return 'booked {}!'.format(ID)
    return 'not booked {}'.format(ID)

@admin_only
@app.route('/admin')
def admin():
    return 'admin'

@admin_only
@app.route('/admin/room')
def room_list():
    return 'rooms'

@admin_only
@app.route('/admin/room/add', methods=['PUT'])
def room_add():
    return 'add rooms'

@admin_only
@app.route('/admin/room/del/<ID>')
def room_del(ID):
    return 'delete {}'.format(ID)

@admin_only
@app.route('/admin/room/get/<ID>')
def room_get(ID):
    return 'room {}'.format(ID)

@admin_only
@app.route('/admin/roomt/edit/<ID>')
def room_edit(ID):
    return 'edit {}'.format(ID)

# we may need this:
def qr():
    url_quoted = request.args.get('url')
    qr_content = unquote(url_quoted)
    output = BytesIO()
    qr = qrcode.make(qr_content)
    qr.save(output, format="PNG")
    output.seek(0)
    return send_file(output, mimetype="image/png")
