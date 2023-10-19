from sanic.response import HTTPResponse, json
from sanic import Blueprint, Request
import sanic
import os
import aiosqlite
import random
import string
import json

token = os.getenv('DISCORD_TOKEN')

bp = Blueprint('private')

@bp.on_request
async def only_discord(request: Request):
    if request.credentials is None: return sanic.text("Only Discord bot can do this", 401)
    if request.credentials.username != 'discord-bot': return sanic.text("Only Discord bot can do this", 403)
    if request.credentials.password != token: return sanic.text("Only Discord bot can do this", 403)

@bp.get("/modmail")
async def pending_modmail(request: Request) -> HTTPResponse:
    entries = []
    db: aiosqlite.Connection = request.app.ctx.db
    async with db.execute("SELECT id, content FROM modmail") as cursor:
        async for row in cursor:
            entries.insert({'id': row[0], 'content': row[1]})
    return json(entries)

@bp.delete("/modmail/<id:int>")
async def del_modmail(request: Request, id: int) -> HTTPResponse:
    db: aiosqlite.Connection = request.app.ctx.db
    await db.execute("DELETE FROM modmail WHERE id=?", (id, ))
    await db.commit()
    return json('ok')

@bp.post('/new')
async def new_interview(request: Request) -> HTTPResponse:
    db: aiosqlite.Connection = request.app.ctx.db


    channel_id = request.json['channel_id']
    user_id = request.json['user_id']
    user_name = request.json['user_name']

    # Check if the interview in this channel exists.
    async with db.execute("SELECT edit_token FROM interview WHERE id=?", (channel_id,)) as cursor:
        async for row in cursor:
            # If here, then there is a matching interview.
            return sanic.json({'state': 'existing', 'edit_url': f'https://interview.starfallmc.space/{channel_id}/{row[0]}'})

    edit_token = ''.join(random.choices(string.ascii_letters, k=16))
    approve_token = ''.join(random.choices(string.ascii_letters, k=16))
    db: aiosqlite.Connection = request.app.ctx.db
    await db.execute("INSERT INTO interview (id, user_id, user_name, edit_token, approve_token, questions_json, answers_json, status) VALUES (?,?,?,?,?,?,?,?)", (
        channel_id,
        user_id,
        user_name,
        edit_token,
        approve_token,
        json.dumps(get_questions()),
        '{}',
        0
    ))
    content = f"The user <@{user_id}> has just created an interview. Moderators can view the progress of this interview at: https://interview.starfallmc.space/{channel_id}/{approve_token}"
    await db.execute("INSERT INTO modmail (content) VALUES (?)", (content,))
    await db.commit()
    return sanic.json({'state': 'new', 'edit_url': f'https://interview.starfallmc.space/{channel_id}/{edit_token}'})

def get_questions():
    questions = []
    for q in open('/config/interview-questions').readlines():
        q = q.strip()
        if '---' not in q:
            questions.append({'id': len(questions), 'body': q, 'constraints': None})
        else:
            q_body, _, desc = q.rpartition('---')
            q = {'id': len(questions), 'body': q_body}
            c = []
            l,r = desc.split('-')
            l = int(l)
            r = int(r)
            if l:
                c.append({'kind':'len_above', 'value': l})
            if r:
                c.append({'kind':'len_below', 'value': r})
            q['constraints'] = c or None
            questions.append(q)
    
    return questions