from datetime import (
        date as Date,
        timedelta
)
from functools import wraps
from imaplib import IMAP4_SSL
from math import floor
from os.path import dirname, exists, join, realpath, isfile, isdir
from os import listdir, mkdir, remove, rmdir
from sys import exit
from urllib.parse import unquote

from flask import (
        Flask,
        flash,
        jsonify,
        request,
        session, 
        redirect,
        render_template,
        url_for
        )
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import and_
from sqlalchemy.exc import IntegrityError
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

# DB Model
class Room(db.Model):
    ID = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(), nullable=False)
    location = db.Column(db.String(), default='')
    description = db.Column(db.String(), default='')
    bookings = db.relationship('Booking', backref='Booking', lazy=True, cascade='all, delete-orphan')

class Booking(db.Model):
    __table_args__ = (db.UniqueConstraint('date', 'period', 'room_id'),) # must be a tuple
    # contraint -> unique in date, period and room_id
    ID = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    period = db.Column(db.Integer, nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey('room.ID'), nullable=False)
    person = db.Column(db.String(), nullable=False)

#
def _db_commit():
    try:
        db.session.commit()
        return True
    except IntegrityError:
        db.session.rollback()
        return False

# DB controller
def booking_book(person, room_id, iso_date, period):
    y,m,d = map(int,iso_date.split('-')) 
    db.session.add(
            Booking(
                person=person,
                room_id=room_id,
                date = Date(y,m,d),
                period=period
                )
            )
    return _db_commit()

def booking_cancel(ID, user):
    booking = Booking.query.filter_by(ID=ID).first()
    if booking is None:
        return False
    if not booking.person == user:
        return False
    db.session.delete(booking)
    return _db_commit()

def _booking_cancel(person, room_id, iso_date, period):
    y,m,d = map(int,iso_date.split('-')) 
    booking = Booking.query.filter_by(
            room_id=room_id,
            date=Date(y,m,d),
            person=person,
            period=period
    ).first()
    if booking is None:
        return False
    db.session.remove(booking)
    db.session.commit()
    return True

def _get_week_range(offset=0):
    today = Date.today()
    start_day = today - timedelta(today.isoweekday()-1 - offset*7)
    end_day = today - timedelta(today.isoweekday()-7 - offset*7)
    days = [(start_day + timedelta(i)).isoformat() for i in range(7)]
    return {"today": today, "start": start_day, "end": end_day, "days": days}

def _booking_get(room_id, start, end):
    booking = Booking.query.filter(
            and_(
                Booking.date.between(start, end),
                Booking.room_id == room_id
                )
            ).all()
    booking = [
            {
                'ID': b.ID,
                'date': b.date.isoformat(),
                'day_num': b.date.isoweekday(),
                'period': b.period,
                'room_id': b.room_id,
                'person': b.person
            }
    for b in booking]
    return booking

def get_week_data(room_id, week_offset=0):
    week = _get_week_range(week_offset)                
    # bookings = _booking_get(room_id, week['start'], week['end'])
    # week['bookings'] = bookings
    data = [ 
            {
                'day_num': i+1,
                'date': day,
                'periods' : [ {} for _ in range(11)]
            } 
    for i,day in enumerate(week['days'])]
    for b in _booking_get(room_id, week['start'], week['end']):
        day_num = b['day_num'] - 1 # list index begins with 0
        period = b['period'] - 1 # ...
        data[day_num]['periods'][period] = b
    return {'timetable': data, 'today': week['today'].isoformat(), 'name': room_get(room_id)['title'], 'week_num': week['start'].isocalendar()[1] }
    # return {"days": week['days'], "today": week['today'].isoformat(), "bookings": bookings, "week_offset": week_offset }

def booking_getall():
    bookings = Booking.query.all()
    return bookings

def room_edit(form_dict):
    ID = form_dict.pop('room_id')
    room = Room.query.filter_by(ID=ID).first()
    for key, value in form_dict.items():
        setattr(room, key, value)
    db.session.add(room)
    return _db_commit()

def room_delete(ID):
    room = Room.query.filter_by(ID=ID).first()
    if room is None:
        return False
    db.session.delete(room)
    return _db_commit()

def room_add(name):
    db.session.add(Room(title=name))
    db.session.commit()

def room_get(ID=None):
    if ID is None:
        return room_getall()
    room = Room.query.filter_by(ID=ID).first()
    room = {
            "ID": room.ID,
            "title": room.title,
            "location": room.location,
            "description": room.description
    }
    return room

def room_getall():
    rooms = Room.query.all()
    rooms = [
                {
                    "ID": room.ID,
                    "title": room.title,
                    "location": room.location,
                    "description": room.description
                }
            for room in rooms
    ]
    return rooms

# session controller
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
    def arb_request(*args, **kwargs):
        if 'user' in session:
            return wrapped(*args, **kwargs)
        else:
            return redirect(url_for('login'))
    return arb_request

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
@logged_in
def home():
    return redirect(url_for('view_rooms')) 

@app.route('/rooms')
@logged_in
def view_rooms():
    return render_template('rooms_view.html')

@app.route('/room/<ID>')
@logged_in
def view_room(ID):
    user = session['user']
    return render_template('room_view.html', ID=ID, user=user)

@app.route('/rest/room')
@logged_in
def rest_rooms():
    return jsonify(room_getall())

@app.route('/rest/room/<int:room_id>/week_offset/<week_offset>', methods=['GET'])
@logged_in
def rest_room_booking(room_id,week_offset):
    week_offset = int(week_offset)
    return jsonify(get_week_data(room_id=room_id, week_offset=week_offset))

@app.route('/rest/room/<ID>', methods=['POST'])
@logged_in
def book_room(ID):
    j = request.get_json()
    period = j['period']
    iso_date = j['iso_date']
    person = session['user']
    if booking_book(person=person, room_id=ID, iso_date=iso_date, period=period):
        return jsonify(True)
    return jsonify(False)

@app.route('/rest/room/<ID>', methods=['DELETE'])
@logged_in
def cancel_room(ID):
    user = session['user']
    return jsonify(booking_cancel(ID, user))

@app.route('/admin', methods=['GET', 'POST'])
@admin_only
def admin():
    if request.method == 'POST':
        form = dict(request.form)
        action = form.pop('action', None)
        if action == 'edit':
            success = room_edit(form_dict=form)
        elif action == 'delete':
            room_id = form.pop('room_id')
            success = room_delete(room_id)
            if success:
                flash('gelöscht')
            else:
                flash('Raum wurde nicht gelöscht.')
        elif action == 'create':
            title = form.pop('title')
            success = room_add(title)
    return render_template('admin.html', rooms=room_getall())

# we may need this:
@app.route('/admin/qr')
@admin_only
def qr():
    url_quoted = request.args.get('url')
    qr_content = unquote(url_quoted)
    output = BytesIO()
    qr = qrcode.make(qr_content)
    qr.save(output, format="PNG")
    output.seek(0)
    return send_file(output, mimetype="image/png")

if __name__ == '__main__':
    app.run(host='localhost', port=8000, debug=True)
