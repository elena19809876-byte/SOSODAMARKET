import asyncio,os,secrets
from datetime import datetime,timedelta,timezone
import asyncpg,uvicorn
from aiogram import Bot,Dispatcher,F
from aiogram.filters import Command
from aiogram.types import Message,CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv
from fastapi import FastAPI,Header,HTTPException
from pydantic import BaseModel

load_dotenv()
BOT_TOKEN=os.getenv("BOT_TOKEN","")
ADMIN_ID=int(os.getenv("ADMIN_ID","1915699158"))
SUPPORT=os.getenv("SUPPORT_USERNAME","@SOSODASTORE")
API_SECRET=os.getenv("API_SECRET","")
DATABASE_URL=os.getenv("DATABASE_URL","")
PORT=int(os.getenv("PORT","8080"))
if not BOT_TOKEN: raise RuntimeError("BOT_TOKEN is missing")
if not API_SECRET: raise RuntimeError("API_SECRET is missing")
if not DATABASE_URL: raise RuntimeError("DATABASE_URL is missing. Set DATABASE_URL=${{Postgres.DATABASE_URL}}")
app=FastAPI(title="SOSODA MARKET Premium API")
bot=Bot(BOT_TOKEN); dp=Dispatcher(); pool=None
def now(): return datetime.now(timezone.utc)
async def init_db():
    global pool
    for _ in range(10):
        try:
            pool=await asyncpg.create_pool(DATABASE_URL,min_size=1,max_size=5)
            async with pool.acquire() as c:
                await c.execute("""CREATE TABLE IF NOT EXISTS premium(
                nick TEXT PRIMARY KEY,expires_at TIMESTAMPTZ NOT NULL,
                created_at TIMESTAMPTZ NOT NULL,issued_by BIGINT NOT NULL);
                CREATE TABLE IF NOT EXISTS keys(
                code TEXT PRIMARY KEY,days INTEGER NOT NULL,used BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ NOT NULL,used_by TEXT);""")
            return
        except Exception:
            await asyncio.sleep(3)
    raise RuntimeError("PostgreSQL connection failed")
async def get_premium(nick):
    async with pool.acquire() as c:
        r=await c.fetchrow("SELECT * FROM premium WHERE nick=$1",nick)
        if r and r["expires_at"]<=now():
            await c.execute("DELETE FROM premium WHERE nick=$1",nick); return None
        return r
async def grant(nick,days,issuer):
    async with pool.acquire() as c:
        r=await c.fetchrow("SELECT expires_at FROM premium WHERE nick=$1",nick)
        start=r["expires_at"] if r and r["expires_at"]>now() else now()
        exp=start+timedelta(days=days)
        await c.execute("""INSERT INTO premium(nick,expires_at,created_at,issued_by)
        VALUES($1,$2,$3,$4) ON CONFLICT(nick) DO UPDATE SET expires_at=$2,issued_by=$4""",
        nick,exp,now(),issuer)
        return exp
def admin(m): return bool(m.from_user and m.from_user.id==ADMIN_ID)
def main_kb():
    k=InlineKeyboardBuilder(); k.button(text="⭐ Купить Premium",callback_data="buy")
    k.button(text="🔎 Проверить Premium",callback_data="check")
    k.button(text="💬 Поддержка",callback_data="support"); k.adjust(1); return k.as_markup()
def admin_kb():
    k=InlineKeyboardBuilder(); 
    for t,d in [("➕ Выдать","grant"),("➖ Снять","remove"),("🔎 Проверить","check_admin"),("📋 Список","list"),("🔑 Ключ","key")]: k.button(text=t,callback_data=d)
    k.adjust(2); return k.as_markup()
@dp.message(Command("start"))
async def start(m): await m.answer("🛍 <b>SOSODA MARKET</b>\n\n⭐ Premium для скрипта",reply_markup=main_kb(),parse_mode="HTML")
@dp.message(Command("admin"))
async def acmd(m):
    if not admin(m): return await m.answer("⛔ Доступ запрещён.")
    await m.answer("👑 <b>Админ-панель</b>",reply_markup=admin_kb(),parse_mode="HTML")
@dp.callback_query(F.data=="buy")
async def buy(c): await c.message.answer(f"⭐ <b>SOSODA MARKET Premium</b>\n\nДля покупки: {SUPPORT}",parse_mode="HTML"); await c.answer()
@dp.callback_query(F.data=="support")
async def sup(c): await c.message.answer(f"💬 Поддержка: {SUPPORT}"); await c.answer()
@dp.callback_query(F.data.in_({"check","check_admin"}))
async def chelp(c): await c.message.answer("Использование: /check НИК"); await c.answer()
@dp.message(Command("check"))
async def check(m):
    p=m.text.split(maxsplit=1)
    if len(p)!=2: return await m.answer("Использование: /check НИК")
    r=await get_premium(p[1].strip())
    if not r: return await m.answer("❌ Premium не активен.")
    await m.answer(f"✅ {p[1]}\n⭐ Premium активен\n⏳ До: {r['expires_at'].strftime('%d.%m.%Y %H:%M UTC')}")
@dp.message(Command("grant"))
async def gcmd(m):
    if not admin(m): return await m.answer("⛔ Доступ запрещён.")
    p=m.text.split()
    if len(p)!=3 or not p[2].isdigit() or int(p[2])<1: return await m.answer("Использование: /grant НИК ДНИ")
    e=await grant(p[1],int(p[2]),m.from_user.id); await m.answer(f"✅ Premium выдан: {p[1]}\nДо: {e.strftime('%d.%m.%Y %H:%M UTC')}")
@dp.message(Command("remove"))
async def rcmd(m):
    if not admin(m): return await m.answer("⛔ Доступ запрещён.")
    p=m.text.split(maxsplit=1)
    if len(p)!=2: return await m.answer("Использование: /remove НИК")
    async with pool.acquire() as c: res=await c.execute("DELETE FROM premium WHERE nick=$1",p[1].strip())
    await m.answer("✅ Premium снят." if res.endswith("1") else "ℹ️ Premium не найден.")
@dp.message(Command("list"))
async def lcmd(m):
    if not admin(m): return await m.answer("⛔ Доступ запрещён.")
    async with pool.acquire() as c: rows=await c.fetch("SELECT nick,expires_at FROM premium WHERE expires_at>NOW() ORDER BY expires_at")
    await m.answer("📋 Premium нет." if not rows else "\n".join(f"• {r['nick']} — {r['expires_at'].strftime('%d.%m.%Y')}" for r in rows))
@dp.message(Command("key"))
async def kcmd(m):
    if not admin(m): return await m.answer("⛔ Доступ запрещён.")
    p=m.text.split()
    if len(p)!=2 or not p[1].isdigit() or int(p[1])<1: return await m.answer("Использование: /key ДНИ")
    code="SOSA-"+secrets.token_hex(6).upper()
    async with pool.acquire() as c: await c.execute("INSERT INTO keys(code,days,created_at) VALUES($1,$2,$3)",code,int(p[1]),now())
    await m.answer(f"🔑 {code}\nСрок: {p[1]} дн.")
class GrantRequest(BaseModel): nick:str; days:int
@app.get("/")
async def health(): return {"ok":True,"service":"SOSODA MARKET Premium API"}
class ActivateRequest(BaseModel):
    code: str
    nick: str

@app.post("/activate")
async def activate(req: ActivateRequest, x_api_secret: str = Header(default="")):
    if x_api_secret != API_SECRET:
        raise HTTPException(401, "unauthorized")

    code = req.code.strip().upper()
    nick = req.nick.strip()

    if not code or not nick:
        raise HTTPException(400, "code and nick are required")

    async with pool.acquire() as c:
        async with c.transaction():
            key_row = await c.fetchrow(
                "SELECT code, days, used FROM keys WHERE code=$1 FOR UPDATE",
                code
            )

            if not key_row:
                raise HTTPException(404, "invalid_key")

            if key_row["used"]:
                raise HTTPException(409, "key_already_used")

            days = int(key_row["days"])
            r = await c.fetchrow(
                "SELECT expires_at FROM premium WHERE nick=$1",
                nick
            )
            start = r["expires_at"] if r and r["expires_at"] > now() else now()
            exp = start + timedelta(days=days)

            await c.execute(
                """INSERT INTO premium(nick,expires_at,created_at,issued_by)
                VALUES($1,$2,$3,$4)
                ON CONFLICT(nick) DO UPDATE SET expires_at=$2,issued_by=$4""",
                nick, exp, now(), ADMIN_ID
            )

            await c.execute(
                "UPDATE keys SET used=TRUE, used_by=$2 WHERE code=$1",
                code, nick
            )

    return {
        "ok": True,
        "premium": True,
        "nick": nick,
        "expires_at": exp.isoformat(),
        "days": days
    }

@app.get("/premium/{nick}")
async def premium(nick:str,x_api_secret:str=Header(default="")):
    if x_api_secret!=API_SECRET: raise HTTPException(401,"unauthorized")
    r=await get_premium(nick)
    return {"ok":True,"premium":bool(r),"nick":nick,**({"expires_at":r["expires_at"].isoformat()} if r else {})}
@app.post("/admin/grant")
async def api_grant(req:GrantRequest,x_api_secret:str=Header(default="")):
    if x_api_secret!=API_SECRET: raise HTTPException(401,"unauthorized")
    if req.days<1 or req.days>3650: raise HTTPException(400,"invalid days")
    e=await grant(req.nick,req.days,ADMIN_ID); return {"ok":True,"nick":req.nick,"expires_at":e.isoformat()}
async def main():
    await init_db()
    s=uvicorn.Server(uvicorn.Config(app,host="0.0.0.0",port=PORT,log_level="info"))
    await asyncio.gather(dp.start_polling(bot),s.serve())
if __name__=="__main__": asyncio.run(main())
