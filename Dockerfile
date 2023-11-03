FROM python:3.10-alpine

WORKDIR /project

COPY ./app .

RUN pip install -r requirements.txt && mkdir "swagger"

EXPOSE 8000

CMD python3 manage.py collectstatic --noinput && \
    python3 manage.py makemigrations && \
    python3 manage.py migrate --run-syncdb && \
    pytest && \
    python3 manage.py spectacular --color --file ./swagger/schema.yml && \
    gunicorn project_orders.wsgi -b 0.0.0.0:8000
