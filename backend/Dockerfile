FROM python:3.11-bookworm

WORKDIR /
ENTRYPOINT ["python3", "main.py"]

COPY requirements.txt /
RUN pip3 install --no-cache -r /requirements.txt

COPY main.py /
# Add other files here...
