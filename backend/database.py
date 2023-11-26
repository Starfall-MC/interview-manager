import aiosqlite

async def create_tables():
    db = await aiosqlite.connect('/data/interviews.sqlite')
    await db.execute("""CREATE TABLE IF NOT EXISTS interview (
                     id INTEGER NOT NULL PRIMARY KEY,
                     user_id INTEGER NOT NULL,
                     user_name TEXT NOT NULL,
                     edit_token INTEGER NOT NULL,
                     approve_token INTEGER NOT NULL,
                     questions_json TEXT NOT NULL,
                     answers_json TEXT NOT NULL,
                     verdict TEXT,
                     status INTEGER NOT NULL,
                     status_changed_at_unix_time INTEGER NOT NULL
    )""")

    await db.execute("""CREATE TABLE IF NOT EXISTS modmail (
                     id INTEGER NOT NULL PRIMARY KEY,
                     content TEXT NOT NULL
    )""")
    return db

class InterviewStatus:
    WAITING_FOR_USER_TO_SUBMIT = 0
    WAITING_FOR_VERDICT = 1
    VERDICT_ACCEPT_ROLE_NOT_APPLIED_MC_NOT_APPLIED = 2
    VERDICT_ACCEPT_ROLE_APPLIED_MC_NOT_APPLIED = 3
    VERDICT_REJECT_NOT_SENT = 4
    VERDICT_REJECT_SENT = 5
    VERDICT_ACCEPT_ROLE_NOT_APPLIED_MC_APPLIED = 6
    VERDICT_ACCEPT_ROLE_APPLIED_MC_APPLIED = 7
