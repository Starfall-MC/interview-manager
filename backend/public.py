import datetime
import time
import traceback
from sanic.response import HTTPResponse, html, json as json_resp
from sanic import Blueprint, Request
import sanic
import sanic_jinja2
import aiosqlite
import json
import mojang
import mcrcon
import asyncio
from database import InterviewStatus


bp = Blueprint('public')

def get_secret_prop(name):
    return open(f'/secrets/{name}').read().strip()


@bp.get('/')
def index(request: Request) -> HTTPResponse:
    return html("<h1>Hello Sanic!</h1>")

@bp.get('/<interview_id:int>/<token>')
async def render_interview(request: Request, interview_id: int, token) -> HTTPResponse:
    jinja: sanic_jinja2.SanicJinja2 = request.app.ctx.jinja
    db: aiosqlite.Connection = request.app.ctx.db

    data = None
    async with db.execute("SELECT id, user_id, user_name, edit_token, approve_token, questions_json, answers_json, verdict, status, status_changed_at_unix_time FROM interview WHERE id=?", (interview_id,)) as cursor:
        async for row in cursor:
            data = row
    
    if data is None:
        return jinja.render('form-404.html', request, 404)
    
    edit_token = data[3]
    approve_token = data[4]
    if token not in [edit_token, approve_token]:
        return jinja.render('form-404.html', request, 404)

    questions = json.loads(data[5])
    answers = json.loads(data[6])
    verdict = json.loads(data[7] or 'null')
    status = data[8]
    
    latest_change = int(data[9])
    latest_change = datetime.datetime.fromtimestamp(latest_change)


    if token == approve_token:
        can_set_verdict = (status == InterviewStatus.WAITING_FOR_VERDICT)
        why_no_verdict = f'Unknown reason (status = {status})'
        if status == InterviewStatus.WAITING_FOR_USER_TO_SUBMIT:
            why_no_verdict = 'The user has not submitted the interview yet'
        elif status == InterviewStatus.VERDICT_ACCEPT_ROLE_APPLIED_MC_NOT_APPLIED:
            why_no_verdict = 'This interview has already been accepted, Minecraft not whitelisted (because of error), and the user is now granted the role on the server'
        elif status == InterviewStatus.VERDICT_ACCEPT_ROLE_NOT_APPLIED_MC_NOT_APPLIED:
            why_no_verdict = 'This interview has already been accepted, Minecraft not whitelisted (because of error), waiting for Discord bot to apply role...'
        elif status == InterviewStatus.VERDICT_REJECT_NOT_SENT:
            why_no_verdict = 'This interview has already been rejected, waiting for Discord bot to send rejection message...'
        elif status == InterviewStatus.VERDICT_REJECT_SENT:
            why_no_verdict = 'This interview has already been rejected, and the Discord bot has already sent rejection message'
        elif status == InterviewStatus.VERDICT_ACCEPT_ROLE_NOT_APPLIED_MC_APPLIED:
            why_no_verdict = 'This interview has already been accepted, Minecraft is whitelisted, waiting for Discord bot to apply role...'
        elif status == InterviewStatus.VERDICT_ACCEPT_ROLE_APPLIED_MC_APPLIED:
            why_no_verdict = 'This interview has already been accepted, Minecraft is whitelisted, and the user is now granted the role on the server'
        return jinja.render('view-act.html', request, questions=questions, answers=answers, verdict=verdict,
                            latest_change=latest_change, can_set_verdict=can_set_verdict, why_no_verdict=why_no_verdict)

    else: # token == edit_token
        if status == InterviewStatus.WAITING_FOR_USER_TO_SUBMIT:
            return jinja.render('edit.html', request, questions=questions, answers=answers, validity=dict(), latest_change=latest_change)
        else:
            return jinja.render('view.html', request, questions=questions, answers=answers, verdict=verdict, latest_change=latest_change)


@bp.post('/<interview_id:int>/<token>')
async def post_interview(request: Request, interview_id: int, token) -> HTTPResponse:
    jinja: sanic_jinja2.SanicJinja2 = request.app.ctx.jinja
    db: aiosqlite.Connection = request.app.ctx.db

    data = None
    async with db.execute("SELECT id, user_id, user_name, edit_token, approve_token, questions_json, answers_json, verdict, status FROM interview WHERE id=?", (interview_id,)) as cursor:
        async for row in cursor:
            data = row
    

    if data is None:
        return jinja.render('form-404.html', request, 404)
    
    user_id = data[1]

    edit_token = data[3]
    approve_token = data[4]
    status = data[8]
    questions = json.loads(data[5])
    answers = json.loads(data[6])

    if token == edit_token:
        if status != InterviewStatus.WAITING_FOR_USER_TO_SUBMIT:
            return html("You have tried submitting a form when it was already submitted. Please open this page again to see the current state of the form.")

        answers = {}
        validity = dict()
        for question in questions:
            answers[question['id']] = answer = request.form.get(f'question-{question["id"]}', '')
            
            # Run validations
            for constraint in question.get('constraints') or []:
                if constraint['kind'] == 'len_above':
                    if len(answer) < constraint['value']:
                        validity[question['id']] = validity.get(question['id'], []) + [f"The answer to this must be {constraint['value']} letters or longer"]
                elif constraint['kind'] == 'len_below':
                    if len(answer) > constraint['value']:
                        validity[question['id']] = validity.get(question['id'], []) + [f"The answer to this must be {constraint['value']} letters or shorter"]
                elif constraint['kind'] == 'minecraftname':
                    if not answer:
                        validity[question['id']] = validity.get(question['id'], []) + [f"Minecraft usernames must not be empty"]
                        continue
                    if not answer.isascii():
                        validity[question['id']] = validity.get(question['id'], []) + [f"Minecraft usernames must be ASCII-only (Latin letters and numbers)"]
                        continue

                    api = mojang.API()
                    loop = asyncio.get_event_loop()
                    try:
                        await loop.run_in_executor(None, lambda: api.get_uuid(answer))
                    except Exception as e:
                        validity[question['id']] = validity.get(question['id'], []) + [f"Mojang's auth server could not find this username: {e}"]
                else:
                    print("!! Unknown constraint kind:", constraint)
            if question['kind'] == 'radio':
                if not answer:
                    validity[question['id']] = validity.get(question['id'], []) + 'You must choose one of these options.'
            if question['kind'] == 'check':
                del answers[question['id']]
                for option in question['options']:
                    if request.form.get(f'question-{question["id"]}-{option["id"]}'):
                        answers[question['id'] + '-' + option['id']] = True
                    else:
                        answers[question['id'] + '-' + option['id']] = False


        # Validations run and answers built
        if not validity:
            new_status = InterviewStatus.WAITING_FOR_VERDICT
            content = f"@everyone The user <@{user_id}> has sent in their responses. Please set the verdict now: https://interview.starfallmc.space/{interview_id}/{approve_token}"
            await db.execute("INSERT INTO modmail (content) VALUES (?)", (content,))
            await db.execute('INSERT INTO completion_notification (id, user_id) VALUES (?,?)', (interview_id, user_id))
            await db.commit()
        else:
            new_status = InterviewStatus.WAITING_FOR_USER_TO_SUBMIT


        await db.execute("UPDATE interview SET status=?, status_changed_at_unix_time=?, answers_json=? WHERE id=?", (new_status, int(time.time()), json.dumps(answers), interview_id))
        await db.commit()
        if not validity:
            return sanic.redirect(request.path)
        else:
            return jinja.render('edit.html', request, questions=questions, answers=answers, validity=validity)

    elif token == approve_token:
        if status != InterviewStatus.WAITING_FOR_VERDICT:
            return html(f"This interview is not waiting for verdict (status = {status}), so you cannot set a verdict now")
        action = request.form.get('action')
        if action not in ['accept', 'reject']: return html(f"Invalid form action: {action}")
        if action == 'reject':
            reason = request.form.get('verdict', '').strip()
            if not reason:
                return html("Rejection verdict cannot be empty")
        else:
            reason = None  # No need for reason for accepting
        

        if action == 'accept':
            # Find the minecraft username question: kind=text and constraints has minecraftname
            mc_username = None
            for q in questions:
                if mc_username: break
                if q['kind'] == 'text':
                    for c in q.get('constraints') or []:
                        if mc_username: break
                        if c['kind'] == 'minecraftname':
                            # Found the question, now get the answer
                            mc_username = answers[q['id']]

            if mc_username:
                def whitelist_in_minecraft():
                    with mcrcon.MCRcon(get_secret_prop('rcon_host'), get_secret_prop('rcon_password'), port=int(get_secret_prop('rcon_port'))) as mcr:
                        resp = mcr.command(f"/whitelist add {mc_username}").strip().lower()
                        if resp not in [f'Added {mc_username} to the whitelist'.lower(), 'Player is already whitelisted'.lower()]:
                            raise ValueError(f"Unexpected response to whitelist command: {repr(resp)}")
                        mcr.command(f"/say A moderator has just accepted an interview: {mc_username} is now whitelisted")

                loop = asyncio.get_event_loop()
                try:
                    try:
                        await db.execute("INSERT INTO minecraft_usernames (discord_id, mc_name) VALUES (?,?)", (user_id, mc_username))
                    except aiosqlite.IntegrityError:
                        await db.execute("UPDATE minecraft_usernames SET mc_name=? WHERE discord_id=?", (mc_username, user_id))
                    await db.execute("INSERT INTO minecraft_whitelist_target VALUES (?)", (mc_username,))
                    await db.commit()
                    whitelist_in_minecraft() # Cannot run this in executor because it uses signal, which can only be used in main thread
                    new_status = InterviewStatus.VERDICT_ACCEPT_ROLE_NOT_APPLIED_MC_APPLIED
                    status_word = 'ACCEPTED and Minecraft whitelist OK'
                    verdict = {'accept': True, 'reason': None}

                except Exception as e:
                    traceback.print_exc()
                    new_status = InterviewStatus.VERDICT_ACCEPT_ROLE_NOT_APPLIED_MC_NOT_APPLIED
                    status_word = 'ACCEPTED, but Minecraft whitelist ERROR @everyone: ' + str(e)
                    verdict = {'accept': True, 'reason': None}
            else:
                # There is no mc username, so nothing to do
                new_status = InterviewStatus.VERDICT_ACCEPT_ROLE_NOT_APPLIED_MC_APPLIED  # applied, because not-applied means error
                status_word = 'ACCEPTED with no Minecraft action needed'
                verdict = {'accept': True, 'reason': None}
        else:
            new_status = InterviewStatus.VERDICT_REJECT_NOT_SENT
            status_word = f'REJECTED with reason: `{reason}`'
            verdict = {'accept': False, 'reason': reason}

        content = f"<@{user_id}>'s interview is now {status_word}"
        await db.execute("INSERT INTO modmail (content) VALUES (?)", (content,))
        await db.execute("UPDATE interview SET status=?, status_changed_at_unix_time=?, verdict=? WHERE id=?", (new_status, int(time.time()), json.dumps(verdict), interview_id))
        await db.commit()
        return sanic.redirect(request.path)

    else:
        return jinja.render('form-404.html', request, 404)


@bp.put('/<interview_id:int>/<token>')
async def put_interview(request: Request, interview_id: int, token) -> HTTPResponse:
    db: aiosqlite.Connection = request.app.ctx.db

    data = None
    async with db.execute("SELECT id, user_id, user_name, edit_token, approve_token, questions_json, answers_json, verdict, status FROM interview WHERE id=?", (interview_id,)) as cursor:
        async for row in cursor:
            data = row
    

    if data is None:
        return json_resp("no such form", 404)

    user_id = data[1]
    edit_token = data[3]
    approve_token = data[4]
    status = data[8]

    if token == edit_token:
        if status != InterviewStatus.WAITING_FOR_USER_TO_SUBMIT:
            json_resp('form not editable', 400)

        answers = request.json
        new_status = InterviewStatus.WAITING_FOR_USER_TO_SUBMIT

        await db.execute("UPDATE interview SET status=?, status_changed_at_unix_time=?, answers_json=? WHERE id=?", (new_status, int(time.time()), json.dumps(answers), interview_id))
        await db.commit()

        return json_resp('ok')
    else:
        return json_resp('no such form', 404)
