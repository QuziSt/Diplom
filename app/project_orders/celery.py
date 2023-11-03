import os
from celery import Celery


CELERY_BROKER_URL = 'redis://redis:6379/2'
CELERY_RESULT_BACKEND = 'redis://redis:6379/4'

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_orders.settings')

app = Celery('django_celery',
             backend=CELERY_RESULT_BACKEND,
             broker=CELERY_BROKER_URL)


# пикл нужен для django-imagekit cache backend, Celery
app.conf.event_serializer = 'pickle'
app.conf.task_serializer = 'pickle'
app.conf.result_serializer = 'pickle'
app.conf.accept_content = ['application/json', 'application/x-python-serialize']

app.autodiscover_tasks()
