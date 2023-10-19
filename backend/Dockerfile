FROM python:3.11-bookworm

WORKDIR /app
ENTRYPOINT ["python3", "main.py"]

COPY requirements.txt .
RUN pip3 install --no-cache -r ./requirements.txt

ADD main.py .
ADD database.py .
ADD private.py .
ADD public.py .
ADD templates/ templates/
RUN ["sanic", "main.py"]