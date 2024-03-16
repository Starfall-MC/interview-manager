import re
from sanic.response import HTTPResponse, json as resp_json
from sanic import Blueprint, Request
import sanic
import os
import aiosqlite
import random
import string
import json
import time

from database import InterviewStatus

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
            entries.append({'id': row[0], 'content': row[1]})
    return resp_json(entries)

@bp.delete("/modmail/<id:int>")
async def del_modmail(request: Request, id: int) -> HTTPResponse:
    db: aiosqlite.Connection = request.app.ctx.db
    await db.execute("DELETE FROM modmail WHERE id=?", (id, ))
    await db.commit()
    return resp_json('ok')

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
    await db.execute("INSERT INTO interview (id, user_id, user_name, edit_token, approve_token, questions_json, answers_json, status, status_changed_at_unix_time) VALUES (?,?,?,?,?,?,?,?,?)", (
        channel_id,
        user_id,
        user_name,
        edit_token,
        approve_token,
        json.dumps(get_questions()),
        '{}',
        0,
        int(time.time())
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
            questions.append({'id': str(len(questions)), 'body': q, 'kind': 'text', 'constraints': None})
        else:
            q_body, _, desc = q.rpartition('---')
            desc = desc.strip()
            q = {'id': str(len(questions)), 'body': q_body}
            if re.match(r'^\d*-\d*$', desc):
                q['kind'] = 'text'
                c = []
                l,r = desc.split('-')
                l = int(l or '0')
                r = int(r or '0')
                if l:
                    c.append({'kind':'len_above', 'value': l})
                if r:
                    c.append({'kind':'len_below', 'value': r})
                q['constraints'] = c or None
                questions.append(q)
            elif re.match(r'^(:?\(\.\) .+?)+$', desc):
                q['kind'] = 'radio'
                opts = []
                for entry in desc.split('(.)'):
                    if not entry: continue
                    opts.append({
                        'id': str(len(opts)),
                        'name': entry,
                    })
                q['options'] = opts
                questions.append(q)

            elif re.match(r'^(:?\[\.\] .+?)+$', desc):
                q['kind'] = 'check'
                opts = []
                for entry in desc.split('[.]'):
                    if not entry: continue
                    opts.append({
                        'id': str(len(opts)),
                        'name': entry,
                    })
                q['options'] = opts
                questions.append(q)
            elif 'MINECRAFTNAME' in desc:
                q['kind'] = 'text'
                q['constraints'] = [{'kind': 'minecraftname'}]
                questions.append(q)
            elif 'SECTION' in desc:
                q['kind'] = 'section'
                questions.append(q)


    return questions

@bp.get("/pending/accept")
async def pending_accepts(request: Request) -> HTTPResponse:
    entries = []
    db: aiosqlite.Connection = request.app.ctx.db
    async with db.execute("SELECT id, user_id, approve_token, status FROM interview WHERE status=? OR status=?", (InterviewStatus.VERDICT_ACCEPT_ROLE_NOT_APPLIED_MC_NOT_APPLIED, InterviewStatus.VERDICT_ACCEPT_ROLE_NOT_APPLIED_MC_APPLIED)) as cursor:
        async for row in cursor:
            entries.append({'channel_id': row[0], 'user_id': row[1], 'token': row[2], 'minecraft_ok': row[3] == InterviewStatus.VERDICT_ACCEPT_ROLE_NOT_APPLIED_MC_APPLIED})
    return resp_json(entries)

@bp.delete("/pending/accept/<id:int>")
async def del_pending_accept(request: Request, id: int) -> HTTPResponse:
    db: aiosqlite.Connection = request.app.ctx.db
    await db.execute("UPDATE interview SET status=? WHERE id=? AND status=?", (InterviewStatus.VERDICT_ACCEPT_ROLE_APPLIED_MC_NOT_APPLIED, id, InterviewStatus.VERDICT_ACCEPT_ROLE_NOT_APPLIED_MC_NOT_APPLIED))
    await db.execute("UPDATE interview SET status=? WHERE id=? AND status=?", (InterviewStatus.VERDICT_ACCEPT_ROLE_APPLIED_MC_APPLIED, id, InterviewStatus.VERDICT_ACCEPT_ROLE_NOT_APPLIED_MC_APPLIED))
    await db.commit()
    return resp_json('ok')

@bp.get("/pending/notify")
async def pending_notifies(request: Request) -> HTTPResponse:
    entries = []
    db: aiosqlite.Connection = request.app.ctx.db
    async with db.execute("SELECT id, user_id FROM completion_notification WHERE is_sent=0",) as cursor:
        async for row in cursor:
            entries.append({'channel_id': row[0], 'user_id': row[1]})
    return resp_json(entries)

@bp.delete("/pending/notify/<id:int>")
async def del_pending_notify(request: Request, id: int) -> HTTPResponse:
    db: aiosqlite.Connection = request.app.ctx.db
    await db.execute("DELETE FROM completion_notification WHERE id=?", (id,))
    await db.commit()
    return resp_json('ok')


@bp.get("/pending/reject")
async def pending_rejects(request: Request) -> HTTPResponse:
    entries = []
    db: aiosqlite.Connection = request.app.ctx.db
    async with db.execute("SELECT id, user_id, verdict, approve_token FROM interview WHERE status=?", (InterviewStatus.VERDICT_REJECT_NOT_SENT,)) as cursor:
        async for row in cursor:
            entries.append({'channel_id': row[0], 'user_id': row[1], 'reason': json.loads(row[2])['reason'], 'token': row[3]})
    return resp_json(entries)

@bp.delete("/pending/reject/<id:int>")
async def del_pending_reject(request: Request, id: int) -> HTTPResponse:
    db: aiosqlite.Connection = request.app.ctx.db
    await db.execute("UPDATE interview SET status=? WHERE id=? AND status=?", (InterviewStatus.VERDICT_REJECT_SENT, id, InterviewStatus.VERDICT_REJECT_NOT_SENT))
    await db.commit()
    return resp_json('ok')


@bp.delete("/status/channel/<id:int>")
async def del_by_channel(request: Request, id: int) -> HTTPResponse:
    db: aiosqlite.Connection = request.app.ctx.db

    # "Send" all notifications corresponding to this channel
    await db.execute("UPDATE completion_notification SET is_sent=1 WHERE id=?", (id,))


    async with db.execute("SELECT id, user_id, approve_token FROM interview WHERE (status=? OR status=?) AND id=?", (InterviewStatus.WAITING_FOR_VERDICT, InterviewStatus.WAITING_FOR_USER_TO_SUBMIT, id)) as cursor:
        async for row in cursor:
            # Reject sent, because if it is not sent then the frontend will try to send it to a missing channel.
            await db.execute("UPDATE interview SET status=?, verdict=? WHERE id=?", (InterviewStatus.VERDICT_REJECT_SENT, json.dumps({'accept': False, 'reason': '[AUTOMATED] Interview channel disappeared'}), row[0]))
            content = f"Interview for user <@{row[1]}> is now automatedly rejected because the channel that started it disappeared. You can view the final state of the interview: https://interview.starfallmc.space/{row[0]}/{row[2]}"
            await db.execute("INSERT INTO modmail (content) VALUES (?)", (content,))
            await db.commit()

    async with db.execute("SELECT id, user_id, approve_token, status FROM interview WHERE (status=? OR status=? OR status=?) AND id=?", (InterviewStatus.VERDICT_REJECT_NOT_SENT, InterviewStatus.VERDICT_ACCEPT_ROLE_NOT_APPLIED_MC_NOT_APPLIED, InterviewStatus.VERDICT_ACCEPT_ROLE_NOT_APPLIED_MC_APPLIED, id)) as cursor:
        async for row in cursor:
            translation = {
                InterviewStatus.VERDICT_REJECT_NOT_SENT: InterviewStatus.VERDICT_REJECT_SENT,
                InterviewStatus.VERDICT_ACCEPT_ROLE_NOT_APPLIED_MC_NOT_APPLIED: InterviewStatus.VERDICT_ACCEPT_ROLE_APPLIED_MC_NOT_APPLIED,
                InterviewStatus.VERDICT_ACCEPT_ROLE_NOT_APPLIED_MC_APPLIED: InterviewStatus.VERDICT_ACCEPT_ROLE_APPLIED_MC_APPLIED,
            }
            await db.execute("UPDATE interview SET status=?, verdict=? WHERE id=?", (translation[row[3]], json.dumps({'accept': False, 'reason': '[AUTOMATED] Interview channel disappeared'}), row[0]))
            content = f"@everyone Interview for user <@{row[1]}> was waiting for Discord status propagation, but the channel for it disappeared. Please apply any changes needed manually. You can view the state of the interview: https://interview.starfallmc.space/{row[0]}/{row[2]}"
            await db.execute("INSERT INTO modmail (content) VALUES (?)", (content,))
            await db.commit()

    await db.commit()

    return resp_json('ok')

@bp.delete("/status/member/<id:int>")
async def del_by_member(request: Request, id: int) -> HTTPResponse:
    db: aiosqlite.Connection = request.app.ctx.db

    # "Send" all notifications corresponding to this member
    await db.execute("UPDATE completion_notification SET is_sent=1 WHERE user_id=?", (id,))

    async with db.execute("SELECT id, user_id, approve_token FROM interview WHERE (status=? OR status=?) AND user_id=?", (InterviewStatus.WAITING_FOR_VERDICT, InterviewStatus.WAITING_FOR_USER_TO_SUBMIT, id)) as cursor:
        async for row in cursor:
            # Reject is set to not sent, because sending reject does not require user to exist.
            await db.execute("UPDATE interview SET status=?, verdict=? WHERE id=?", (InterviewStatus.VERDICT_REJECT_NOT_SENT, json.dumps({'accept': False, 'reason': '[AUTOMATED] Discord member disappeared'}), row[0]))
            content = f"Interview for user <@{row[1]}> is now automatedly rejected because the user that started it disappeared. You can view the final state of the interview: https://interview.starfallmc.space/{row[0]}/{row[2]}"
            await db.execute("INSERT INTO modmail (content) VALUES (?)", (content,))
            await db.commit()

    await db.commit()
    return resp_json('ok')
