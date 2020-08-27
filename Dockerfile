FROM python:3.8


RUN mkdir /app
RUN mkdir /app/static
RUN mkdir /app/templates
VOLUME /app/config
VOLUME /app/db

ADD arb.py /app
ADD config/config.py.docker /app/config/config.py
ADD LICENSE /app
ADD models.py /app
ADD requirements.txt /app
ADD static /app/static
ADD templates /app/templates


WORKDIR /app
RUN pip install -r requirements.txt

RUN python -c "from arb import app, db ; app.app_context().push(); db.create_all()"

EXPOSE 8000




CMD ["python", "arb.py"]
