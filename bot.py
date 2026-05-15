import logging
import sqlite3
import random
import string
from datetime import datetime
from urllib.parse import urlencode
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    WebAppInfo, ChatPermissions
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

import os

# ═══════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════
BOT_TOKEN    = os.environ.get("BOT_TOKEN", "")
ADMIN_ID     = int(os.environ.get("ADMIN_ID", "8514275237"))
SUPPORT_USER = "SentinelGarant"
BOT_USERNAME = "SentinelGarantBot"
GROUP_URL    = "https://t.me/SentinelGarantGroup"
WEBAPP_URL   = "https://createrfollows-design.github.io/sentinel-garant/"
COMMISSION   = 25
# ═══════════════════════════════════════════════

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# States
(
    ENTER_NFT, ENTER_PRICE, ENTER_BUYER,
    SUPPORT_MSG
) = range(4)

STATUS_MAP = {
    "pending":    ("⏳", "Ожидает"),
    "nft_sent":   ("📦", "NFT получен"),
    "stars_sent": ("⭐", "Оплачено"),
    "completed":  ("✅", "Завершена"),
    "cancelled":  ("❌", "Отменена"),
    "dispute":    ("⚠️", "Спор"),
}

# ───────────────── DATABASE ─────────────────────
def init_db():
    with sqlite3.connect("deals.db") as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS deals (
                id          TEXT PRIMARY KEY,
                seller_id   INTEGER,
                seller_name TEXT,
                buyer_name  TEXT,
                nft_link    TEXT,
                nft_name    TEXT,
                price       INTEGER,
                commission  INTEGER DEFAULT 25,
                status      TEXT DEFAULT 'pending',
                created     TEXT,
                updated     TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id     INTEGER PRIMARY KEY,
                username    TEXT,
                first_name  TEXT,
                deals_count INTEGER DEFAULT 0,
                joined      TEXT
            )
        """)

def register_user(user):
    with sqlite3.connect("deals.db") as conn:
        conn.execute("""
            INSERT OR IGNORE INTO users (user_id, username, first_name, joined)
            VALUES (?, ?, ?, ?)
        """, (user.id, user.username or "", user.first_name or "", 
              datetime.now().strftime("%d.%m.%Y")))

def save_deal(d):
    with sqlite3.connect("deals.db") as conn:
        conn.execute(
            "INSERT INTO deals VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (d["id"], d["seller_id"], d["seller_name"], d["buyer_name"],
             d["nft_link"], d["nft_name"], d["price"], d["commission"],
             d["status"], d["created"], d["created"])
        )
        conn.execute(
            "UPDATE users SET deals_count = deals_count + 1 WHERE user_id = ?",
            (d["seller_id"],)
        )

def get_deal(deal_id):
    with sqlite3.connect("deals.db") as conn:
        row = conn.execute("SELECT * FROM deals WHERE id=?", (deal_id,)).fetchone()
    if not row:
        return None
    keys = ["id","seller_id","seller_name","buyer_name",
            "nft_link","nft_name","price","commission","status","created","updated"]
    return dict(zip(keys, row))

def update_status(deal_id, status):
    with sqlite3.connect("deals.db") as conn:
        conn.execute(
            "UPDATE deals SET status=?, updated=? WHERE id=?",
            (status, datetime.now().strftime("%d.%m.%Y %H:%M"), deal_id)
        )

def user_deals(seller_id):
    with sqlite3.connect("deals.db") as conn:
        rows = conn.execute(
            "SELECT * FROM deals WHERE seller_id=? ORDER BY created DESC LIMIT 10",
            (seller_id,)
        ).fetchall()
    keys = ["id","seller_id","seller_name","buyer_name",
            "nft_link","nft_name","price","commission","status","created","updated"]
    return [dict(zip(keys, r)) for r in rows]

def stats():
    with sqlite3.connect("deals.db") as conn:
        total   = conn.execute("SELECT COUNT(*) FROM deals").fetchone()[0]
        done    = conn.execute("SELECT COUNT(*) FROM deals WHERE status='completed'").fetchone()[0]
        users   = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        volume  = conn.execute("SELECT COALESCE(SUM(price),0) FROM deals WHERE status='completed'").fetchone()[0]
    return total, done, users, volume

def gen_id():
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=8))

def deal_link(deal_id):
    return f"https://t.me/{BOT_USERNAME}?start=deal_{deal_id}"

def deal_webapp(d):
    params = urlencode({
        "id":         d["id"],
        "nft":        d["nft_name"],
        "link":       d["nft_link"],
        "price":      d["price"],
        "commission": d["commission"],
        "seller":     d["seller_name"],
        "buyer":      d["buyer_name"],
        "status":     d["status"],
        "created":    d["created"],
    })
    return WEBAPP_URL + "?" + params

# ───────────────── KEYBOARDS ────────────────────
def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🤝 Создать сделку",    callback_data="create")],
        [
            InlineKeyboardButton("📋 Мои сделки",     callback_data="mydeals"),
            InlineKeyboardButton("📊 Статистика",     callback_data="stats"),
        ],
        [InlineKeyboardButton("📖 Как это работает",  callback_data="howto")],
        [
            InlineKeyboardButton("💬 Поддержка",      callback_data="support"),
            InlineKeyboardButton("👥 Сообщество",     url=GROUP_URL),
        ],
    ])

def back_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ Главное меню", callback_data="main")]
    ])

def deal_kb(deal_id, url):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Открыть сделку", web_app=WebAppInfo(url=url))],
        [InlineKeyboardButton("💬 Поддержка",      url=f"https://t.me/{SUPPORT_USER}")],
        [InlineKeyboardButton("◀️ Главное меню",   callback_data="main")],
    ])

def admin_kb(deal_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📦 NFT получен",  callback_data=f"a_nft_{deal_id}"),
            InlineKeyboardButton("⭐ Оплачено",     callback_data=f"a_stars_{deal_id}"),
        ],
        [
            InlineKeyboardButton("✅ Завершить",    callback_data=f"a_done_{deal_id}"),
            InlineKeyboardButton("❌ Отменить",     callback_data=f"a_cancel_{deal_id}"),
        ],
        [InlineKeyboardButton("⚠️ Открыть спор",  callback_data=f"a_dispute_{deal_id}")],
    ])

def cancel_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_conv")]
    ])

# ───────────────── TEXTS ────────────────────────
WELCOME = """🛡 *Sentinel Garant*
━━━━━━━━━━━━━━━━━━━━

Добро пожаловать в профессиональный сервис безопасных сделок с Telegram NFT и Stars.

*Почему выбирают нас:*
▸ Каждая сделка защищена гарантом
▸ Активы хранятся у нейтральной стороны
▸ Поддержка 24/7
▸ Прозрачные условия

Выберите действие:"""

HOWTO = """📖 *Как проходит сделка*
━━━━━━━━━━━━━━━━━━━━

*Шаг 1 — Создание*
Продавец создаёт сделку, указывает NFT, цену и юзернейм покупателя.

*Шаг 2 — Отправка NFT*
Продавец отправляет NFT на аккаунт гаранта @{support}.

*Шаг 3 — Оплата*
Покупатель переводит Stars + комиссию {commission}⭐ гаранту @{support}.

*Шаг 4 — Завершение*
Гарант передаёт NFT покупателю и Stars продавцу.

*Комиссия:* {commission} ⭐ Stars (покрывает стоимость передачи NFT)

⚠️ Никогда не переводите средства напрямую!""".format(
    support=SUPPORT_USER, commission=COMMISSION
)

# ───────────────── HANDLERS ─────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user)

    args = ctx.args
    if args and args[0].startswith("deal_"):
        deal_id = args[0][5:]
        deal = get_deal(deal_id)
        if deal:
            icon, label = STATUS_MAP.get(deal["status"], ("❓", deal["status"]))
            url = deal_webapp(deal)
            await update.message.reply_text(
                f"🤝 *Сделка #{deal['id']}*\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"🖼 NFT: *{deal['nft_name']}*\n"
                f"⭐ Цена: *{deal['price']} Stars*\n"
                f"💰 Комиссия: *{deal['commission']} Stars*\n"
                f"👤 Продавец: @{deal['seller_name']}\n"
                f"👤 Покупатель: @{deal['buyer_name']}\n"
                f"📊 Статус: {icon} {label}\n"
                f"📅 Создана: {deal['created']}\n\n"
                f"_Нажмите кнопку ниже чтобы открыть детали сделки_",
                parse_mode="Markdown",
                reply_markup=deal_kb(deal["id"], url)
            )
            return
        await update.message.reply_text("❌ Сделка не найдена.")
        return

    await update.message.reply_text(
        WELCOME, parse_mode="Markdown", reply_markup=main_kb()
    )

async def btn_main(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.edit_text(
        WELCOME, parse_mode="Markdown", reply_markup=main_kb()
    )

async def btn_howto(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.edit_text(
        HOWTO, parse_mode="Markdown", reply_markup=back_kb()
    )

async def btn_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    total, done, users, volume = stats()
    await q.message.edit_text(
        f"📊 *Статистика Sentinel Garant*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📋 Всего сделок: *{total}*\n"
        f"✅ Завершено: *{done}*\n"
        f"👥 Пользователей: *{users}*\n"
        f"💰 Оборот: *{volume:,} Stars*\n\n"
        f"_Обновлено: {datetime.now().strftime('%d.%m.%Y %H:%M')}_",
        parse_mode="Markdown",
        reply_markup=back_kb()
    )

async def btn_support(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.edit_text(
        f"💬 *Поддержка*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"По всем вопросам обращайтесь к гаранту:\n\n"
        f"👤 @{SUPPORT_USER}\n\n"
        f"*Время ответа:* обычно до 15 минут\n"
        f"*Режим работы:* ежедневно\n\n"
        f"Также можете задать вопрос в нашем сообществе:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✉️ Написать гаранту", url=f"https://t.me/{SUPPORT_USER}")],
            [InlineKeyboardButton("👥 Сообщество",       url=GROUP_URL)],
            [InlineKeyboardButton("◀️ Главное меню",     callback_data="main")],
        ])
    )

# ── Создание сделки ──────────────────────────────
async def btn_create(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.edit_text(
        f"🤝 *Создание сделки*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"*Шаг 1 из 3 — NFT*\n\n"
        f"Отправьте ссылку на NFT который хотите продать:\n\n"
        f"Пример:\n`https://t.me/nft/PlushPepe-111`",
        parse_mode="Markdown",
        reply_markup=cancel_kb()
    )
    return ENTER_NFT

async def step_nft(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if "t.me/nft/" not in text and "t.me/gifts/" not in text:
        await update.message.reply_text(
            "❌ Некорректная ссылка. Пример:\n`https://t.me/nft/PlushPepe-111`",
            parse_mode="Markdown",
            reply_markup=cancel_kb()
        )
        return ENTER_NFT

    name = text.rstrip("/").split("/")[-1]
    ctx.user_data["nft_link"] = text
    ctx.user_data["nft_name"] = name

    await update.message.reply_text(
        f"✅ *NFT принят:* `{name}`\n\n"
        f"*Шаг 2 из 3 — Цена*\n\n"
        f"Введите цену в Telegram Stars:\n\n"
        f"Пример: `1000`\n\n"
        f"_Комиссия гаранта {COMMISSION}⭐ оплачивается покупателем отдельно_",
        parse_mode="Markdown",
        reply_markup=cancel_kb()
    )
    return ENTER_PRICE

async def step_price(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        price = int(update.message.text.strip())
        if price < 1:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "❌ Введите корректную сумму (целое число больше 0).",
            reply_markup=cancel_kb()
        )
        return ENTER_PRICE

    ctx.user_data["price"] = price
    await update.message.reply_text(
        f"✅ *Цена: {price} ⭐*\n\n"
        f"*Шаг 3 из 3 — Покупатель*\n\n"
        f"Введите Telegram юзернейм покупателя без @:\n\n"
        f"Пример: `username`",
        parse_mode="Markdown",
        reply_markup=cancel_kb()
    )
    return ENTER_BUYER

async def step_buyer(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    buyer  = update.message.text.strip().lstrip("@")
    seller = update.effective_user
    seller_name = seller.username or str(seller.id)
    total = ctx.user_data["price"] + COMMISSION

    deal = {
        "id":          gen_id(),
        "seller_id":   seller.id,
        "seller_name": seller_name,
        "buyer_name":  buyer,
        "nft_link":    ctx.user_data["nft_link"],
        "nft_name":    ctx.user_data["nft_name"],
        "price":       ctx.user_data["price"],
        "commission":  COMMISSION,
        "status":      "pending",
        "created":     datetime.now().strftime("%d.%m.%Y %H:%M"),
    }
    save_deal(deal)

    url  = deal_webapp(deal)
    link = deal_link(deal["id"])

    await update.message.reply_text(
        f"🎉 *Сделка создана успешно!*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🆔 ID: `{deal['id']}`\n"
        f"🖼 NFT: *{deal['nft_name']}*\n"
        f"⭐ Цена: *{deal['price']} Stars*\n"
        f"💰 Комиссия: *{COMMISSION} Stars*\n"
        f"💎 Итого покупателю: *{total} Stars*\n"
        f"👤 Покупатель: @{buyer}\n\n"
        f"📤 *Ссылка для покупателя:*\n`{link}`\n\n"
        f"_Отправьте эту ссылку покупателю. Гарант получит уведомление._",
        parse_mode="Markdown",
        reply_markup=deal_kb(deal["id"], url)
    )

    # Уведомление гаранту
    try:
        await ctx.bot.send_message(
            ADMIN_ID,
            f"🔔 *НОВАЯ СДЕЛКА*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🆔 `{deal['id']}`\n"
            f"🖼 NFT: `{deal['nft_name']}`\n"
            f"🔗 {deal['nft_link']}\n"
            f"⭐ Цена: {deal['price']} Stars\n"
            f"💰 Комиссия: {COMMISSION} Stars\n"
            f"💎 Итого: {total} Stars\n"
            f"👤 Продавец: @{seller_name}\n"
            f"👤 Покупатель: @{buyer}\n"
            f"📅 {deal['created']}\n\n"
            f"🔗 {link}",
            parse_mode="Markdown",
            reply_markup=admin_kb(deal["id"])
        )
    except Exception as e:
        logging.warning(f"Не удалось уведомить гаранта: {e}")

    ctx.user_data.clear()
    return ConversationHandler.END

async def cancel_conv(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ctx.user_data.clear()
    await q.message.edit_text(
        WELCOME, parse_mode="Markdown", reply_markup=main_kb()
    )
    return ConversationHandler.END

async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text(
        "❌ Создание сделки отменено.",
        reply_markup=main_kb()
    )
    return ConversationHandler.END

# Мои сделки
async def btn_mydeals(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    deals = user_deals(q.from_user.id)
    if not deals:
        await q.message.edit_text(
            "📋 *Мои сделки*\n━━━━━━━━━━━━━━━━━━━━\n\nУ вас пока нет сделок.\n\nСоздайте первую сделку!",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🤝 Создать сделку", callback_data="create")],
                [InlineKeyboardButton("◀️ Главное меню",   callback_data="main")],
            ])
        )
        return

    lines = [f"📋 *Ваши сделки:*\n━━━━━━━━━━━━━━━━━━━━\n"]
    for d in deals:
        icon, label = STATUS_MAP.get(d["status"], ("❓", d["status"]))
        lines.append(f"{icon} `#{d['id']}` — *{d['nft_name']}*\n   {d['price']}⭐ → @{d['buyer_name']} — {label}\n")

    await q.message.edit_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=back_kb()
    )

# Действия гаранта
async def admin_action(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("⛔ Нет доступа", show_alert=True)
        return
    await q.answer()

    parts   = q.data.split("_", 2)
    action  = parts[1]
    deal_id = parts[2]
    deal    = get_deal(deal_id)
    if not deal:
        await q.answer("Сделка не найдена", show_alert=True)
        return

    actions = {
        "nft":     ("nft_sent",   "📦 NFT получен гарантом"),
        "stars":   ("stars_sent", "⭐ Оплата Stars получена"),
        "done":    ("completed",  "✅ Сделка завершена"),
        "cancel":  ("cancelled",  "❌ Сделка отменена"),
        "dispute": ("dispute",    "⚠️ Открыт спор"),
    }

    if action in actions:
        status, label = actions[action]
        update_status(deal_id, status)
        kb = admin_kb(deal_id) if action not in ("done", "cancel") else None
        try:
            await q.message.edit_text(
                q.message.text + f"\n\n*{label}*\n_{datetime.now().strftime('%H:%M')}_",
                parse_mode="Markdown",
                reply_markup=kb
            )
        except Exception:
            pass

        # Уведомить продавца
        if action == "done":
            try:
                await ctx.bot.send_message(
                    deal["seller_id"],
                    f"✅ *Сделка #{deal_id} завершена!*\n\n"
                    f"NFT отправлен покупателю, Stars зачислены вам.\n"
                    f"Спасибо за использование Sentinel Garant!",
                    parse_mode="Markdown",
                    reply_markup=main_kb()
                )
            except Exception:
                pass

# ───────────────── MAIN ─────────────────────────
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(btn_create, pattern="^create$")],
        states={
            ENTER_NFT:   [MessageHandler(filters.TEXT & ~filters.COMMAND, step_nft)],
            ENTER_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, step_price)],
            ENTER_BUYER: [MessageHandler(filters.TEXT & ~filters.COMMAND, step_buyer)],
        },
        fallbacks=[
            CommandHandler("cancel", cmd_cancel),
            CallbackQueryHandler(cancel_conv, pattern="^cancel_conv$"),
        ],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(btn_main,     pattern="^main$"))
    app.add_handler(CallbackQueryHandler(btn_howto,    pattern="^howto$"))
    app.add_handler(CallbackQueryHandler(btn_stats,    pattern="^stats$"))
    app.add_handler(CallbackQueryHandler(btn_support,  pattern="^support$"))
    app.add_handler(CallbackQueryHandler(btn_mydeals,  pattern="^mydeals$"))
    app.add_handler(CallbackQueryHandler(admin_action, pattern="^a_"))

    print("✅ Sentinel Garant запущен!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
