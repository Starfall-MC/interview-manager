from sanic.response import HTTPResponse, html
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
    async with db.execute("SELECT id, user_id, user_name, edit_token, approve_token, questions_json, answers_json, verdict, status FROM interview WHERE id=?", (interview_id,)) as cursor:
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
    status = data[8]
    
    if token == approve_token:
        return html("approve token supplied")
    else: # token == edit_token
        if status == InterviewStatus.WAITING_FOR_USER_TO_SUBMIT:
            return jinja.render('edit.html', request, questions=questions, answers=answers, validity=dict())
        else:
            return html(f"edit token supplied, but status is {status}")