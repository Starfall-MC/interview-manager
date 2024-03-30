FROM python:3.11-bookworm

WORKDIR /
ENTRYPOINT ["python3", "main.py"]

COPY requirements.txt /
RUN pip3 install --no-cache -r /requirements.txt

RUN mkdir commands
COPY main.py /
COPY common.py /
COPY commands/* ./commands
# Add other files here...
