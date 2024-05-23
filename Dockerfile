FROM python:3.11

WORKDIR /usr/src/app

COPY requirements.txt .

RUN pip install -r requirements.txt

COPY ./app.py .
COPY ./tracing.py .
COPY ./ibmapi.txt .

CMD ["ddtrace-run", "python", "app.py"]