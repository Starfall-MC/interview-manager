import os
import traceback
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

async def periodically_send_list(app):
    while 1:
        try:
            db: aiosqlite.Connection = app.ctx.db
            waiting_for_verdicts = []
            async with db.execute("SELECT id, user_id, approve_token FROM interview WHERE status=?", (InterviewStatus.WAITING_FOR_VERDICT, )) as cursor:
                async for row in cursor:
                    waiting_for_verdicts.append(f'- <@{row[1]}>: https://interview.starfallmc.space/{row[0]}/{row[2]}')

            if waiting_for_verdicts:
                content = f"@everyone These {len(waiting_for_verdicts)} interviews are waiting for verdicts:\n" + '\n'.join(waiting_for_verdicts)
                await db.execute("INSERT INTO modmail (content) VALUES (?)", (content,))
        except:
            traceback.print_exc()
            await asyncio.sleep(5)
            continue
        await asyncio.sleep(12 * 60 * 60)

app.add_task(periodically_send_list)

if __name__ == '__main__':
    # db = asyncio.run(create_tables())
    # app.ctx.db = db
    app.run('0.0.0.0', 80, access_log=True)