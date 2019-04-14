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
    __table_args__ = (db.UniqueConstraint('date', 'period', 'room_id'),) # must be a tuple
    # contraint -> unique in date, period and room_id
    ID = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    period = db.Column(db.Integer, nullable=False)
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

def booking_cancel(ID, user, admin=False):
    booking = Booking.query.filter_by(ID=ID).first()
    if booking is None:
        return False, -1
    if not (booking.person == user or admin):
        return False, -1
    db.session.delete(booking)
    return _db_commit(), booking.room_id

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
    return {
        'room_id': room_id,
        'timetable': data,
        'today': week['today'].isoformat(),
        'room_data': room_get(room_id),
        'week_num': week['start'].isocalendar()[1]
    }
    # return {"days": week['days'], "today": week['today'].isoformat(), "bookings": bookings, "week_offset": week_offset }

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
                    "description": room.description,
                    "color_index": room.color_index,
                    "description_html": markdown(room.description)
                }
            for room in rooms
    ]
    rooms.sort(key = lambda x: x['title'].lower())
    return rooms

