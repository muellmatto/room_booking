from datetime import (
        date as Date,
        timedelta
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import and_
from sqlalchemy.exc import IntegrityError
from markdown import markdown

db = SQLAlchemy()

# DB Model
class Room(db.Model):
    ID = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(), nullable=False)
    location = db.Column(db.String(), default='')
    description = db.Column(db.String(), default='')
    color_index = db.Column(db.Integer, default=0)
    bookings = db.relationship('Booking', backref='Booking', lazy=True, cascade='all, delete-orphan')

class Booking(db.Model):
    __table_args__ = (db.UniqueConstraint('date', 'room_id'),) # must be a tuple
    # contraint -> unique in date and room_id
    ID = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey('room.ID'), nullable=False)
    person = db.Column(db.String(), nullable=False)

def _db_commit():
    try:
        db.session.commit()
        return True
    except IntegrityError:
        db.session.rollback()
        return False

# DB controller
def booking_book(person, room_id, year, week):
    target_date = Date.fromisocalendar(year=year, week=week, day=1)
    new_booking = Booking(
        person=person,
        room_id=room_id,
        date = target_date
    )
    db.session.add(new_booking)
    return _db_commit()

def booking_cancel(ID, user, admin=False):
    booking = Booking.query.filter_by(ID=ID).first()
    if booking is None:
        return False, -1
    if not (booking.person == user or admin):
        return False, -1
    db.session.delete(booking)
    return _db_commit(), booking.room_id


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
                'room_id': b.room_id,
                'person': b.person
            }
    for b in booking]
    return booking

def get_upcoming_bookings():
    today = Date.today()
    current_week = today.isocalendar().week
    current_year = today.isocalendar().year
    start_date = Date.fromisocalendar(year=current_year, week=current_week, day=1)
    bookings = []
    for booking in Booking.query.filter(
            Booking.date.between(start_date, start_date+timedelta(weeks=6))
        ):
        bookings.append({
            "person": booking.person,
            "date": booking.date,
            "room": Room.query.get(booking.room_id).title
        })
    return bookings[:]


def get_calendar_data(room_id, week_offset=0):
    NUM_WEEKS = 6
    today = Date.today()
    current_week = today.isocalendar().week
    current_year = today.isocalendar().year
    start_date = Date.fromisocalendar(year=current_year, week=current_week, day=1)
    start_date += timedelta(weeks=week_offset*NUM_WEEKS)
    calendar = [ 
            {
                'year': (start_date + timedelta(weeks=i)).isocalendar().year, 
                'week': (start_date + timedelta(weeks=i)).isocalendar().week, 
                'first_date_of_week': (start_date + timedelta(weeks=i)).isoformat(), 
                'last_date_of_week': (start_date + timedelta(weeks=i, days=4)).isoformat(), 
                'booked': {},
            } 
    for i in range(NUM_WEEKS)]

    print ("wek")
    for b in _booking_get(room_id, start_date, start_date+timedelta(weeks=NUM_WEEKS)):
        print(b)
        for i, week in enumerate(calendar):
            if b['date'] == week['first_date_of_week']:
                calendar[i]['booked'] = b

    return {
        'room_id': room_id,
        'calendar': calendar,
        'offset': week_offset,
        'room_data': room_get(room_id)
    }

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
            "color_index": room.color_index,
            "description": room.description,
    }
    return room

def room_getall():
    rooms = Room.query.all()
    rooms = [
                {
                    "ID": room.ID,
                    "title": room.title,
                    "location": room.location,
                    "description": room.description,
                    "color_index": room.color_index,
                    "description_html": markdown(room.description),
                }
            for room in rooms
    ]
    rooms.sort(key = lambda x: x['title'].lower())
    return rooms

