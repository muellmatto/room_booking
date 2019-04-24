FROM python:3.7-alpine

RUN mkdir /app
RUN mkdir /app/static
RUN mkdir /app/templates
ADD arb.py /app
ADD config.py /app
ADD LICENSE /app
ADD models.py /app
ADD requirements.txt /app
ADD static /app/static
ADD templates /app/templates

WORKDIR /app

RUN apk add --no-cache --virtual .build-deps gcc jpeg-dev zlib-dev  musl-dev
RUN pip install -r requirements.txt
RUN apk del .build-deps gcc jpeg-dev zlib-dev musl-dev

RUN python -c "from arb import app, db ; app.app_context().push(); db.create_all()"

CMD ["python", "arb.py"]
