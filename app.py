import asyncio, os, secrets
from datetime import datetime, timedelta, timezone

import asyncpg
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from pydantic import BaseModel
import uvicorn

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "1915699158"))
SUPPORT = os.getenv("SUPPORT_USERNAME", "@SOSODASTORE")
API_SECRET = os.getenv("API_SECRET", "")
PORT = int(os.getenv("PORT", "8080"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing")
if not API_SECRET:
    raise RuntimeError("API_SECRET is missing")

app = FastAPI(title="SOSODA MARKET Premium API")
bot = Bot(BOT_TOKEN)
dp = Dispatcher()
pool = None

async def db():
    global pool
    if pool is None:
        pool = await asyncpg.create_pool(os.environ["DATABASE_URL"], min_size=1, max_size=5)
        async with pool.acquire() as c:
            await c.execute("""
            CREATE TABLE IF NOT EXISTS premium (
                nick TEXT PRIMARY KEY,
                expires_at TIMESTAMPTZ NOT NULL,
                created_at TIMESTAMPTZ NOT NULL,
                issued_by BIGINT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS keys (
                code TEXT PRIMARY KEY,
                days INTEGER NOT NULL,
                used BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ NOT NULL,
                used_by TEXT
            );
            """)
    return pool

def now():
    return datetime.now(timezone.utc)

def esc(s):
    return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

async def get_premium(nick):
    p = await db()
    async with p.acquire() as c:
        row = await c.fetchrow("SELECT * FROM premium WHERE nick=$1", nick)
        if row and row["expires_at"] <= now():
            await c.execute("DELETE FROM premium WHERE nick=$1", nick)
            return None
        return row

async def grant(nick, days, issuer):
    p = await db()
    async with p.acquire() as c:
        row = await c.fetchrow("SELECT expires_at FROM premium WHERE nick=$1", nick)
        start = row["expires_at"] if row and row["expires_at"] > now() else now()
        expires = start + timedelta(days=days)
        await c.execute("""
            INSERT INTO premium(nick,expires_at,created_at,issued_by)
            VALUES($1,$2,$3,$4)
            ON CONFLICT(nick) DO UPDATE SET expires_at=$2, issued_by=$4
        """, nick, expires, now(), issuer)
        return expires

async def remove(nick):
    p = await db()
    async with p.acquire() as c:
        return await c.execute("DELETE FROM premium WHERE nick=$1", nick)

def is_admin(m):
    return bool(m.from_user and m.from_user.id == ADMIN_ID)

def main_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="⭐ Купить Premium", callback_data="buy")
    kb.button(text="🔎 Проверить Premium", callback_data="check")
    kb.button(text="💬 Поддержка", callback_data="support")
    kb.adjust(1)
    return kb.as_markup()

def admin_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Выдать", callback_data="grant")
    kb.button(text="➖ Снять", callback_data="remove")
    kb.button(text="🔎 Проверить", callback_data="check_admin")
    kb.button(text="📋 Список", callback_data="list")
    kb.button(text="🔑 Ключ", callback_data="key")
    kb.adjust(2)
    return kb.as_markup()

@dp.message(Command("start"))
async def start(m: Message):
    await m.answer(
        "🛍 <b>SOSODA MARKET</b>\n\n⭐ Premium для скрипта",
        reply_markup=main_kb(), parse_mode="HTML"
    )

@dp.message(Command("admin"))
async def admin_cmd(m: Message):
    if not is_admin(m):
        return await m.answer("⛔ Доступ запрещён.")
    await m.answer("👑 <b>Админ-панель</b>", reply_markup=admin_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "buy")
async def buy(c: CallbackQuery):
    await c.message.answer(
        f"⭐ <b>SOSODA MARKET Premium</b>\n\n"
        f"Для покупки напишите: {SUPPORT}\n\n"
        "После оплаты Premium будет выдан на ваш игровой ник.",
        parse_mode="HTML")
    await c.answer()

@dp.callback_query(F.data == "support")
async def support(c: CallbackQuery):
    await c.message.answer(f"💬 Поддержка: {SUPPORT}")
    await c.answer()

@dp.callback_query(F.data.in_({"check","check_admin"}))
async def check_help(c: CallbackQuery):
    await c.message.answer("Использование: /check НИК")
    await c.answer()

@dp.message(Command("check"))
async def check_cmd(m: Message):
    p = m.text.split(maxsplit=1)
    if len(p) != 2:
        return await m.answer("Использование: /check НИК")
    row = await get_premium(p[1].strip())
    if not row:
        return await m.answer(f"❌ {esc(p[1])}: Premium не активен.")
    await m.answer(f"✅ {esc(p[1])}\n⭐ Premium активен\n⏳ До: {row['expires_at'].strftime('%d.%m.%Y %H:%M UTC')}")

@dp.callback_query(F.data == "grant")
async def grant_help(c: CallbackQuery):
    if c.from_user.id != ADMIN_ID: return await c.answer("Нет доступа", show_alert=True)
    await c.message.answer("Использование: /grant НИК ДНИ\nНапример: /grant Player_Name 30")
    await c.answer()

@dp.message(Command("grant"))
async def grant_cmd(m: Message):
    if not is_admin(m): return await m.answer("⛔ Доступ запрещён.")
    p = m.text.split()
    if len(p) != 3 or not p[2].isdigit() or int(p[2]) <= 0:
        return await m.answer("Использование: /grant НИК ДНИ")
    exp = await grant(p[1], int(p[2]), m.from_user.id)
    await m.answer(f"✅ Premium выдан\nНик: <code>{esc(p[1])}</code>\nДо: {exp.strftime('%d.%m.%Y %H:%M UTC')}", parse_mode="HTML")

@dp.callback_query(F.data == "remove")
async def remove_help(c: CallbackQuery):
    if c.from_user.id != ADMIN_ID: return await c.answer("Нет доступа", show_alert=True)
    await c.message.answer("Использование: /remove НИК")
    await c.answer()

@dp.message(Command("remove"))
async def remove_cmd(m: Message):
    if not is_admin(m): return await m.answer("⛔ Доступ запрещён.")
    p = m.text.split(maxsplit=1)
    if len(p) != 2: return await m.answer("Использование: /remove НИК")
    result = await remove(p[1].strip())
    await m.answer("✅ Premium снят." if result.endswith("1") else "ℹ️ Premium не найден.")

@dp.callback_query(F.data == "list")
async def list_cb(c: CallbackQuery):
    if c.from_user.id != ADMIN_ID: return await c.answer("Нет доступа", show_alert=True)
    p = await db()
    async with p.acquire() as conn:
        rows = await conn.fetch("SELECT nick, expires_at FROM premium WHERE expires_at > NOW() ORDER BY expires_at")
    if not rows: return await c.message.answer("📋 Premium-пользователей нет.")
    text = ["📋 <b>Premium</b>"] + [f"• <code>{esc(r['nick'])}</code> — {r['expires_at'].strftime('%d.%m.%Y')}" for r in rows]
    await c.message.answer("\n".join(text), parse_mode="HTML")
    await c.answer()

@dp.message(Command("list"))
async def list_cmd(m: Message):
    if not is_admin(m): return await m.answer("⛔ Доступ запрещён.")
    p = await db()
    async with p.acquire() as conn:
        rows = await conn.fetch("SELECT nick, expires_at FROM premium WHERE expires_at > NOW() ORDER BY expires_at")
    if not rows: return await m.answer("📋 Premium-пользователей нет.")
    await m.answer("\n".join([f"• {r['nick']} — {r['expires_at'].strftime('%d.%m.%Y')}" for r in rows]))

@dp.callback_query(F.data == "key")
async def key_help(c: CallbackQuery):
    if c.from_user.id != ADMIN_ID: return await c.answer("Нет доступа", show_alert=True)
    await c.message.answer("Использование: /key ДНИ\nНапример: /key 30")
    await c.answer()

@dp.message(Command("key"))
async def key_cmd(m: Message):
    if not is_admin(m): return await m.answer("⛔ Доступ запрещён.")
    p = m.text.split()
    if len(p) != 2 or not p[1].isdigit() or int(p[1]) <= 0:
        return await m.answer("Использование: /key ДНИ")
    code = "SOSA-" + secrets.token_hex(6).upper()
    dbp = await db()
    async with dbp.acquire() as c:
        await c.execute("INSERT INTO keys(code,days,created_at) VALUES($1,$2,$3)", code, int(p[1]), now())
    await m.answer(f"🔑 <code>{code}</code>\nСрок: {p[1]} дн.", parse_mode="HTML")

class GrantRequest(BaseModel):
    nick: str
    days: int

@app.get("/")
async def health():
    return {"ok": True, "service": "SOSODA MARKET Premium API"}

@app.get("/premium/{nick}")
async def premium(nick: str, x_api_secret: str = Header(default="")):
    if x_api_secret != API_SECRET:
        raise HTTPException(401, "unauthorized")
    row = await get_premium(nick)
    if not row:
        return {"ok": True, "premium": False, "nick": nick}
    return {"ok": True, "premium": True, "nick": nick, "expires_at": row["expires_at"].isoformat()}

@app.post("/admin/grant")
async def api_grant(req: GrantRequest, x_api_secret: str = Header(default="")):
    if x_api_secret != API_SECRET:
        raise HTTPException(401, "unauthorized")
    if req.days < 1 or req.days > 3650:
        raise HTTPException(400, "invalid days")
    exp = await grant(req.nick, req.days, ADMIN_ID)
    return {"ok": True, "nick": req.nick, "expires_at": exp.isoformat()}

async def main():
    await db()
    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=PORT, log_level="info"))
    await asyncio.gather(dp.start_polling(bot), server.serve())

if __name__ == "__main__":
    asyncio.run(main())
