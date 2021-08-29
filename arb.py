from functools import wraps
from hashlib import sha3_512
from imaplib import IMAP4_SSL
from io import BytesIO
import json
from math import floor
from os import mkdir
from os.path import (
        dirname,
        isdir,
        isfile,
        join,
        realpath
        )
from sys import exit
from urllib.parse import unquote

from flask import (
        Flask,
        flash,
        jsonify,
        request,
        session, 
        redirect,
        send_file,
        render_template,
        url_for
        )
from flask_socketio import SocketIO, send
from qrcode import make as make_qrcode

from models import (
        db,
        get_calendar_data,
        get_upcoming_bookings,
        booking_book,
        booking_cancel,
        room_getall,
        room_edit,
        room_delete,
        room_add,
        user_add,
        user_edit,
        user_delete,
        user_get,
        user_getall
        )



try:
    from config.config import (
            secret_key,
            allowed_domain,
            imap_host,
            imap_port,
            production_url,
            salt
    )
except:
    print('please check config.py')
    exit(1)


app = Flask(__name__)
app.secret_key = secret_key

PATH = dirname(realpath(__file__))
DB_PATH = join(PATH, 'db', 'arb.sqlite3')
NUM_COLORS = 5

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + DB_PATH
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

socketio = SocketIO(app, cors_allowed_origins = '*')

# init db models
db.init_app(app)

if not isdir(join(PATH, 'db')):
    mkdir(join(PATH, 'db'))

if not isfile(DB_PATH):
    with app.app_context():
        db.create_all()

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
            return redirect(url_for('login', path=request.path))
    return arb_request

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = user_get(username)
        if user:
            # user exists
            if user.check_password(password):
                # login successful!
                session['user'] = user.username.lower()
                if user.is_admin:
                    # user is admin!
                    session['admin'] = user.username.lower()
                return redirect(url_for('home'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    if 'admin' in session:
        session.pop('admin', None)
    if 'user' in session:
        session.pop('user', None)
    return redirect(url_for('home'))

@app.route('/')
@logged_in
def home():
    return redirect(url_for('view_rooms')) 

@app.route('/rooms')
@logged_in
def view_rooms():
    admin = 'admin' in session
    return render_template('rooms_view.html', admin=admin)

@app.route('/room/<ID>')
@logged_in
def view_room(ID):
    user = session['user']
    admin = 'admin' in session
    return render_template('room_view.html', ID=ID, user=user, admin=admin)

@app.route('/rest/room')
@logged_in
def rest_rooms():
    return jsonify(room_getall())

@app.route('/rest/room/<int:room_id>/week_offset/<week_offset>', methods=['GET'])
@logged_in
def rest_room_booking(room_id,week_offset):
    week_offset = int(week_offset)
    return jsonify(get_calendar_data(room_id=room_id, week_offset=week_offset))

@app.route('/rest/room/<ID>', methods=['POST'])
@logged_in
def book_room(ID):
    j = request.get_json()
    year = j['year']
    week = j['week']
    person = session['user']
    if booking_book(person=person, room_id=ID, year=year, week=week):
        socketio.emit('update', {'room_id': ID}, json=True)
        return jsonify(True)
    return jsonify(False)

@app.route('/rest/room/<ID>', methods=['DELETE'])
@logged_in
def cancel_room(ID):
    user = session['user']
    admin = 'admin' in session
    success, room_id = booking_cancel(ID, user, admin)
    if success:
        socketio.emit('update', {'room_id': room_id}, json=True)
        return jsonify(True)
    return jsonify(False)

def socket_emit_room_data(room_id, week_offset):
    week_offset = int(week_offset)
    socketio.emit(
            'room_data',
            get_calendar_data(
                room_id = room_id,
                week_offset = week_offset
            ),
            json = True
    )



@socketio.on('get_data')
@logged_in
def socket_get_data(room_id, week_offset):
    socket_emit_room_data(room_id, week_offset)

@socketio.on('cancel')
@logged_in
def socket_cancel(booking_id, room_id, week_offset):
    user = session['user']
    admin = 'admin' in session
    success, room_id = booking_cancel(booking_id, user, admin)
    socket_emit_room_data(room_id, week_offset)

@socketio.on('update')
@logged_in
def socket_update(room_id, year, week, week_offset):
    user = session['user']
    if booking_book(user=user, room_id=room_id, year=year, week=week):
        socket_emit_room_data(room_id, week_offset)

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
    return render_template('admin.html', rooms=room_getall(), NUM_COLORS = NUM_COLORS)


@app.route("/bookings", methods=['GET'])
@admin_only
def bookings():
    return render_template("bookings.html", bookings=get_upcoming_bookings())


@app.route('/users', methods=['GET', 'POST'])
@admin_only
def users():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        full_name = request.form.get('full_name')
        info = request.form.get('info')
        is_admin = "is_admin" in request.form
        success = user_add(
            username=username,
            password=password,
            full_name=full_name,
            info=info,
            is_admin=is_admin
        )
        if success:
            flash(f'{username} wurde erstellt')
        else:
            flash(f'admin oder user mit dem Namen {username} existiert bereits')
    users, admins = [], []
    for user in user_getall():
        if user.is_admin:
            admins.append(user)
        else:
            users.append(user)
    return render_template('users.html', admins=admins, users=users)

@app.route('/user/<username>', methods=['GET', 'POST'])
@admin_only
def user(username):
    user = user_get(username)
    if not user:
        return redirect(url_for('users'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        full_name = request.form.get('full_name')
        info = request.form.get('info')
        is_admin = "is_admin" in request.form
        user_edit(username=username, password=password, info=info, full_name=full_name, is_admin=is_admin)
    return render_template('user.html', user=user)

@app.route('/delete_user/<username>', methods=['POST'])
@admin_only
def delete_user(username):
    if user_delete(username):
        flash(f'{username} wurde gelöscht')
    else:
        flash(f'{username} konnte nicht gelöscht werden')
    return redirect(url_for('users'))

@app.route('/admin/qr/<int:room_id>')
@admin_only
def qr(room_id):
    qr_content = 'https://{}{}'.format(production_url, url_for('view_room', ID=room_id))
    output = BytesIO()
    qr = make_qrcode(qr_content)
    qr.save(output, format="PNG")
    output.seek(0)
    return send_file(output, mimetype="image/png")

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=8000, debug=True)
