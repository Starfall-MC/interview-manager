import datetime
import time
from sanic.response import HTTPResponse, html, json as json_resp
from sanic import Blueprint, Request
import sanic
import sanic_jinja2
import aiosqlite
import json
from database import InterviewStatus


bp = Blueprint('public')

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
        elif status == InterviewStatus.VERDICT_ACCEPT_APPLIED:
            why_no_verdict = 'This interview has already been accepted, and the user is now granted the role on the server'
        elif status == InterviewStatus.VERDICT_ACCEPT_NOT_APPLIED:
            why_no_verdict = 'This interview has already been accepted, waiting for Discord bot to apply role...'
        elif status == InterviewStatus.VERDICT_REJECT_NOT_SENT:
            why_no_verdict = 'This interview has already been rejected, waiting for Discord bot to send rejection message...'
        elif status == InterviewStatus.VERDICT_REJECT_SENT:
            why_no_verdict = 'This interview has already been rejected, and the Discord bot has already sent rejection message'
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

    if token == edit_token:
        if status != InterviewStatus.WAITING_FOR_USER_TO_SUBMIT:
            return html("You have tried submitting a form when it was already submitted. Please open this page again to see the current state of the form.")

        questions = json.loads(data[5])
        answers = {}
        validity = dict()
        for question in questions:
            answers[question['id']] = answer = request.form.get(f'question-{question["id"]}', '')
            
            # Run validations
            for constraint in question['constraints'] or []:
                if constraint['kind'] == 'len_above':
                    if len(answer) < constraint['value']:
                        validity[question['id']] = validity.get(question['id'], []) + [f"The answer to this must be {constraint['value']} letters or longer"]
                elif constraint['kind'] == 'len_below':
                    if len(answer) > constraint['value']:
                        validity[question['id']] = validity.get(question['id'], []) + [f"The answer to this must be {constraint['value']} letters or shorter"]
                else:
                    print("!! Unknown constraint kind:", constraint)


        # Validations run and answers built
        if not validity:
            new_status = InterviewStatus.WAITING_FOR_VERDICT
            content = f"@everyone The user <@{user_id}> has sent in their responses. Please set the verdict now: https://interview.starfallmc.space/{interview_id}/{approve_token}"
            await db.execute("INSERT INTO modmail (content) VALUES (?)", (content,))
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
            new_status = InterviewStatus.VERDICT_ACCEPT_NOT_APPLIED
            status_word = 'ACCEPTED'
            verdict = {'accept': True, 'reason': None}
        else:
            new_status = InterviewStatus.VERDICT_REJECT_NOT_SENT
            status_word = f'REJECTED with reason: {reason}'
            verdict = {'accept': False, 'reason': reason}

        content = f"<@{user_id}>'s interview is now {status_word}, waiting for change to be propagated..."
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