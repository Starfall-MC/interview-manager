import os
import sanic
import asyncio

from sanic.response import HTTPResponse
from sanic.request import Request

token = os.getenv('DISCORD_TOKEN')

app = sanic.Sanic(__name__)


@app.route("/")
def index(request: Request) -> HTTPResponse:
    return sanic.html("<h1>Hello Sanic!</h1>")


if __name__ == '__main__':
    app.run('0.0.0.0', 80)