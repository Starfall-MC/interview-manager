import os
import sanic
import asyncio
from database import *

from sanic.response import HTTPResponse
from sanic.request import Request

from private import bp as private_bp
from public import bp as public_bp

from sanic_session import Session, InMemorySessionInterface
from sanic_jinja2 import SanicJinja2


app = sanic.Sanic(__name__)
app.blueprint(private_bp)
app.blueprint(public_bp)

session = Session(app, interface=InMemorySessionInterface())

jinja = SanicJinja2(app, session=session)

@app.before_server_start
async def connect_db(app, _):
    app.ctx.db = await create_tables()
    app.ctx.jinja = jinja

if __name__ == '__main__':
    # db = asyncio.run(create_tables())
    # app.ctx.db = db
    app.run('0.0.0.0', 80)