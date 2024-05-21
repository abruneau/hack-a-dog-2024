FROM python:3.11

WORKDIR /usr/src/app

COPY ./app/requirements.txt ./

RUN pip install -r requirements.txt

COPY ./app .

CMD ["ddtrace-run", "python", "app.py"]
