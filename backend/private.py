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
import mcrcon
import copy

from database import InterviewStatus

token = os.getenv('DISCORD_TOKEN')

def get_secret_prop(name):
    return open(f'/secrets/{name}').read().strip()


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

    # Check if there are any interviews for the same person where the status is one of the completed ones.
    has_old_interviews = False
    async with db.execute("SELECT status FROM interview WHERE user_id=?", (user_id,)) as cursor:
        async for row in cursor:
            if row[0] in InterviewStatus.list_CANNOT_BE_CHANGED:
                has_old_interviews = True
                break

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
    return sanic.json({'state': 'new', 'edit_url': f'https://interview.starfallmc.space/{channel_id}/{edit_token}', 'has_old_interviews': has_old_interviews})

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
            verdict = json.loads(row[2])
            entries.append({'channel_id': row[0], 'user_id': row[1], 'reason': verdict['reason'], 'offer_try_again': verdict.get('offer_try_again', False), 'token': row[3]})
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

    # If there is a known Minecraft username for this user, and there is also such a row in the ideal whitelist,
    # then remove such from the ideal whitelist.
    name = None
    async with db.execute("SELECT mc_name FROM minecraft_usernames WHERE discord_id=?", (id,)) as cursor:
        async for row in cursor:
            name = row[0]
            break
    
    is_in_whitelist = False
    if name is not None:
        async with db.execute("SELECT 1 FROM minecraft_whitelist_target WHERE mc_name=?", (name,)) as cursor:
            async for row in cursor:
                is_in_whitelist = True
    
    if is_in_whitelist:
        await db.execute("DELETE FROM minecraft_whitelist_target WHERE mc_name=?", (name,))
        content = f"The user <@{id}>, which just left, has Minecraft name `{name}`, and it was removed from the ideal Minecraft whitelist. Run `/reify` to apply it immediately, or wait up to 60 minutes."
        await db.execute("INSERT INTO modmail (content) VALUES (?)", (content,))

    await db.commit()
    return resp_json('ok')

@bp.post("/status/full-members")
async def sync_member_list(request: Request) -> HTTPResponse:
    db: aiosqlite.Connection = request.app.ctx.db

    member_ids = set(request.json)

    # If there are any Minecraft names in the ideal whitelist, which are associated with Discord IDs,
    # and these Discord IDs are not members,
    # then delete them from the whitelist.

    existing_whitelists = dict()
    async with db.execute("SELECT discord_id, minecraft_whitelist_target.mc_name FROM minecraft_whitelist_target NATURAL JOIN minecraft_usernames") as cursor:
        async for row in cursor:
            existing_whitelists[row[0]] = row[1]
    
    current_whitelisted_ids = set(existing_whitelists.keys())
    gone_member_ids = current_whitelisted_ids - member_ids
    gone_member_ids = list(gone_member_ids)

    for id in gone_member_ids:
        await db.execute("DELETE FROM minecraft_whitelist_target WHERE mc_name=?", (existing_whitelists[id],))
    
    if len(gone_member_ids)!=0:
        content = f"The following {len(gone_member_ids)} members disappeared while we weren't looking, so they are now removed from the ideal whitelist:\n"
        for id in gone_member_ids:
            content += f'- <@{id}> `{existing_whitelists[id]}`\n'
        
        content += 'Run `/reify` now to apply the change immediately, or wait up to 60 minutes.'
        await db.execute("INSERT INTO modmail (content) VALUES (?)", (content,))

    await db.commit()
    return resp_json('ok')


@bp.get("/interviews/by-user/<id:int>")
async def interviews_by_user(request: Request, id: int) -> HTTPResponse:
    db: aiosqlite.Connection = request.app.ctx.db
    
    # Read all the interviews which were involving this user.
    interviews = []
    async with db.execute("SELECT id, approve_token FROM interview WHERE user_id=?", (id,)) as cursor:
        async for row in cursor:
            interviews.append({'id': row[0], 'url': f'https://interview.starfallmc.space/{row[0]}/{row[1]}'})
    
    return resp_json(interviews)

@bp.get("/minecraft/discord-to-name/<id:int>")
async def minecraft_discord_to_name(request: Request, id: int) -> HTTPResponse:
    db: aiosqlite.Connection = request.app.ctx.db

    # Get which MC username this user has
    async with db.execute("SELECT mc_name FROM minecraft_usernames WHERE discord_id=?", (id,)) as cursor:
        answer = None
        async for row in cursor:
            answer = row
        
    if answer is None:
        return resp_json({'status': 'missing'})
    else:
        return resp_json({'status': 'ok', 'name': row[0]})

@bp.get("/minecraft/name-to-discord/<name:str>")
async def minecraft_name_to_discord(request: Request, name: str) -> HTTPResponse:
    db: aiosqlite.Connection = request.app.ctx.db

    # Get which MC username this user has
    async with db.execute("SELECT discord_id FROM minecraft_usernames WHERE mc_name=?", (name,)) as cursor:
        answer = None
        async for row in cursor:
            answer = row
        
    if answer is None:
        return resp_json({'status': 'missing'})
    else:
        return resp_json({'status': 'ok', 'id': row[0]})


@bp.post("/minecraft/discord-to-name/<id:int>")
async def minecraft_alter_name(request: Request, id: int) -> HTTPResponse:
    db: aiosqlite.Connection = request.app.ctx.db

    new_name = request.json['name']

    # Get the old value in the MC username table
    async with db.execute("SELECT mc_name FROM minecraft_usernames WHERE discord_id=?", (id,)) as cursor:
        old_name = None
        async for row in cursor:
            old_name = row[0]
    
    if old_name is None:
        await db.execute("INSERT INTO minecraft_usernames (discord_id, mc_name) VALUES (?,?)", (id, new_name))
        await db.commit()
        return resp_json({'status': 'ok', 'old_name': None, 'new_name': new_name, 'did_update_whitelist': False})
    else:
        try:
            await db.execute("UPDATE minecraft_usernames SET mc_name=? WHERE discord_id=?", (new_name, id))
        except aiosqlite.IntegrityError:
            return resp_json({'status': 'err', 'reason': 'name_collision_in_usernames'})

        # Check if the whitelist target list needs updating.
        existing_whitelist = False
        async with db.execute("SELECT 1 FROM minecraft_whitelist_target WHERE mc_name=?", (old_name,)) as cursor:
            async for _row in cursor:
                existing_whitelist = True
        
        if existing_whitelist:
            try:
                await db.execute("UPDATE minecraft_whitelist_target SET mc_name=? WHERE mc_name=?", (new_name, old_name))
            except aiosqlite.IntegrityError:
                return resp_json({'status': 'err', 'reason': 'name_collision_in_whitelist'})
        
        await db.commit()
        return resp_json({'status': 'ok', 'old_name': old_name, 'new_name': new_name, 'did_update_whitelist': existing_whitelist})

async def apply_spelling(db: aiosqlite.Connection, correct_spelling: str):
    db.execute("UPDATE minecraft_whitelist_target SET mc_name=? WHERE mc_name=? COLLATE NOCASE", (correct_spelling, correct_spelling))
    db.execute("UPDATE minecraft_usernames SET mc_name=? WHERE mc_name=? COLLATE NOCASE", (correct_spelling, correct_spelling))

async def reify_mc_whitelist(db: aiosqlite.Connection) -> list:
    # Get the current active whitelist and the ideal whitelist

    ideal = []
    async with db.execute("SELECT mc_name FROM minecraft_whitelist_target") as cursor:
        async for row in cursor:
            ideal.append(row[0])

    ideal_cmp = set(map(lambda x: x.lower(), ideal))


    with mcrcon.MCRcon(get_secret_prop('rcon_host'), get_secret_prop('rcon_password'), port=int(get_secret_prop('rcon_port'))) as mcr:
        resp = mcr.command("/whitelist list").strip().lower()

    # There are 123 whitelisted player(s): a, b, c
    
    resp = resp.split('player(s):')[1]
    actual = list(map(lambda x: x.strip(), resp.split(',')))
    actual_cmp = set(map(lambda x: x.lower(), actual))

    to_apply = []

    for item in ideal:
        if item.lower() not in actual_cmp:
            to_apply.append((item, '+'))
    
    for item in actual:
        if item.lower() not in ideal_cmp:
            to_apply.append((item, '-'))
        
        await apply_spelling(db, item)
    
    await db.commit()

    with mcrcon.MCRcon(get_secret_prop('rcon_host'), get_secret_prop('rcon_password'), port=int(get_secret_prop('rcon_port'))) as mcr:
        for name, action in to_apply:
            if action == '+':
                resp = mcr.command(f'whitelist add {name}')
                if resp.lower().strip() not in [f'added {name.lower()} to the whitelist', 'player is already whitelisted']:
                    content = f'<@495297618763579402> Error while reifying whitelist: `+ {name}` returned `{resp}`'
                    await db.execute("INSERT INTO modmail (content) VALUES (?)", (content,))
                    await db.commit()
            else:
                resp = mcr.command(f'whitelist remove {name}')
                if resp.lower().strip() not in [f'removed {name.lower()} from the whitelist', 'player is not whitelisted']:
                    content = f'<@495297618763579402> Error while reifying whitelist: `- {name}` returned `{resp}`'
                    await db.execute("INSERT INTO modmail (content) VALUES (?)", (content,))
                    await db.commit()

    if to_apply:
        reify_actions = ', '.join(map(lambda x: f'`{x[1]} {x[0]}`', to_apply))
        content = f"Whitelist reification caused these commands: {reify_actions}"
        await db.execute("INSERT INTO modmail (content) VALUES (?)", (content,))
        await db.commit()
    
    return to_apply


@bp.post("/minecraft/ideal-whitelist/reify")
async def reify_mc_whitelist_from_web(request: Request) -> HTTPResponse:
    db: aiosqlite.Connection = request.app.ctx.db

    to_apply = await reify_mc_whitelist(db)

    return resp_json(to_apply)


@bp.put("/minecraft/ideal-whitelist/<name:str>")
async def add_to_ideal(request: Request, name: str) -> HTTPResponse:
    db: aiosqlite.Connection = request.app.ctx.db

    try:
        await db.execute("INSERT INTO minecraft_whitelist_target VALUES (?)", (name,))
    except aiosqlite.IntegrityError:
        return resp_json({'status': 'already'})

    return resp_json({'status': 'ok'})

@bp.delete("/minecraft/ideal-whitelist/<name:str>")
async def del_from_ideal(request: Request, name: str) -> HTTPResponse:
    db: aiosqlite.Connection = request.app.ctx.db

    # Check if it's already there
    is_there = False
    async with db.execute("SELECT 1 FROM minecraft_whitelist_target WHERE mc_name=?", (name,)) as cursor:
        async for _row in cursor:
            is_there = True

    if not is_there:
        return resp_json({'status': 'already'})

    await db.execute("DELETE FROM minecraft_whitelist_target WHERE mc_name=?", (name,))
    return resp_json({'status': 'ok'})

async def migrate_interview(db: aiosqlite.Connection, old_id: int, new_id: int) -> HTTPResponse:
    # Fetch the old and new interview
    old = None
    async with db.execute("SELECT * FROM interview WHERE id=?", (old_id,)) as cursor:
        cursor.row_factory = aiosqlite.Row
        async for row in cursor:
            old = row

    new = None
    async with db.execute("SELECT * FROM interview WHERE id=?", (new_id,)) as cursor:
        cursor.row_factory = aiosqlite.Row
        async for row in cursor:
            new = row

    if old is None:
        return resp_json({'status': 'err', 'reason': 'missing_old_interview'})
    
    if new is None:
        return resp_json({'status': 'err', 'reason': 'missing_new_interview'})
    
    # If the old interview has no verdict yet, cannot proceed
    if old['verdict'] is None:
        return resp_json({'status': 'err', 'reason': 'old_interview_no_verdict'})
    
    # If the new interview has been sent, cannot proceed
    if new['status'] != InterviewStatus.WAITING_FOR_USER_TO_SUBMIT:
        return resp_json({'status': 'err', 'reason': 'new_interview_already_sent'})
    
    # If the two interviews have different owners, cannot proceed
    if old['user_id'] != new['user_id']:
        return resp_json({'status': 'err', 'reason': 'owner_not_same'})

    # For every old question and answer, we need to find a matching new question,
    # then set the answer.
    old_questions = json.loads(old['questions_json'])
    new_questions = json.loads(new['questions_json'])
    old_answers = json.loads(old['answers_json'])
    new_answers = json.loads(new['answers_json'])

    # For every old question, find a new question that matches it in every aspect except for the ID.
    missing_old_questions = 0
    old_new_mapping = dict()
    for old_question in old_questions:
        old_question = copy.deepcopy(old_question)
        old_id = old_question['id']
        old_question.pop('id')
        found_id = None
        for new_question in new_questions:
            new_question = copy.deepcopy(new_question)
            new_question_id = new_question['id']
            new_question.pop('id')
            if old_question == new_question:
                found_id = new_question_id
                break

        if found_id is not None:
            old_new_mapping[old_id] = found_id
        else:
            missing_old_questions += 1
    
    # Rewrite the answer IDs corresponding to the mapping
    for old_id, new_id in old_new_mapping.items():
        new_answers[new_id] = old_answers.get(old_id)

    # Update the new interview
    await db.execute("UPDATE interview SET answers_json=? WHERE id=?", (json.dumps(new_answers), new['id']))
    msg = f"Interview https://interview.starfallmc.space/{new['id']}/{new['approve_token']} migrated from interview https://interview.starfallmc.space/{old['id']}/{old['approve_token']}: {missing_old_questions} old questions were missing, and {len(old_new_mapping)} were able to be copied."
    await db.execute("INSERT INTO modmail (content) VALUES (?)", (msg,))
    await db.commit()

    return resp_json({'status': 'ok', 'missing_migrations': missing_old_questions, 'ok_migrations': len(old_new_mapping)})

@bp.post("/interview/migrate")
async def migrate_interviews(request: Request) -> HTTPResponse:
    db: aiosqlite.Connection = request.app.ctx.db
    old_id = request.json['old_id']
    new_id = request.json['new_id']
    old_edit_token = request.json['old_edit_token']

    if old_id == new_id:
        return resp_json({'status': 'err', 'reason': 'same_id'})

    # Check if the old interview exists and has the given edit token
    async with db.execute("SELECT 1 FROM interview WHERE id=? AND edit_token=?", (old_id, old_edit_token)) as cursor:
        is_old_ok = False
        async for _row in cursor:
            is_old_ok = True
        
        if not is_old_ok:
            return resp_json({'status': 'err', 'reason': 'old_interview_invalid'})

    # Check if the new interview exists and has not been sent yet
    async with db.execute("SELECT 1 FROM interview WHERE id=? AND status=?", (new_id, InterviewStatus.WAITING_FOR_USER_TO_SUBMIT)) as cursor:
        is_status_ok = False
        async for _row in cursor:
            is_status_ok = True
        
        if not is_status_ok:
            return resp_json({'status': 'err', 'reason': 'new_interview_already_sent'})
    
    return await migrate_interview(db, old_id, new_id)
