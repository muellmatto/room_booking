from functools import wraps
from imaplib import IMAP4_SSL
from io import BytesIO
from json import dumps as dump_json
from math import floor
from os.path import dirname, join, realpath
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
        Booking,
        Room,
        get_week_data,
        booking_book,
        booking_cancel,
        room_getall,
        room_edit,
        room_delete,
        room_add
        )

try:
    from config import (
            username,
            password,
            secret_key,
            allowed_domain,
            imap_host,
            imap_port,
            production_url
    )
except:
    print('please check config.py')
    exit(1)

app = Flask(__name__)
app.secret_key = secret_key

PATH = dirname(realpath(__file__))
DB_PATH = join(PATH, 'arb.sqlite3')
NUM_COLORS = 5

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + DB_PATH
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

socketio = SocketIO(app)

# init db models
db.init_app(app)
# session controller
def imap_auth(username, password):
    username = username.lower()
    if not username.endswith(allowed_domain):
        if not '@' in username:
            username = "@".join([username, allowed_domain])
        else:
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
            session['user'] = user
            return redirect(url_for('home'))
        elif imap_auth(username=user,password=pw):
            session.permanent = True
            session['user'] = user.lower()
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
    return jsonify(get_week_data(room_id=room_id, week_offset=week_offset))

@app.route('/rest/room/<ID>', methods=['POST'])
@logged_in
def book_room(ID):
    j = request.get_json()
    period = j['period']
    iso_date = j['iso_date']
    person = session['user']
    if booking_book(person=person, room_id=ID, iso_date=iso_date, period=period):
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
            get_week_data(
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
def socket_update(room_id, iso_date, period, week_offset):
    person = session['user']
    if booking_book(person=person, room_id=room_id, iso_date=iso_date, period=period):
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
    socketio.run(app, host='0.0.0.0', port=8000, debug=False)
