import telebot
from telebot import types
import json
import requests
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
import re

TOKEN = '7548327118:AAEj9J7Dnm23usIz4cosz1M28LIn8BOqaWc'
OPENWEATHER_API_KEY = '4d0d47bf998c359eb519496fb38caa8b'

bot = telebot.TeleBot(TOKEN)
scheduler = BackgroundScheduler()
scheduler.start()

notes = {}
reminders = {}
user_settings = {}
daily_settings = {}

# Загрузка
for fname, store in [('notes.json', notes), ('reminders.json', reminders), ('user_settings.json', user_settings), ('daily_settings.json', daily_settings)]:
    try:
        with open(fname, 'r', encoding='utf-8') as f:
            store.update(json.load(f))
    except:
        pass

# Восстановление задач
for uid, items in reminders.items():
    for item in items:
        t = datetime.strptime(item['time'], '%Y-%m-%d %H:%M')
        if t > datetime.now():
            uid_copy = uid
            item_copy = item.copy()
            scheduler.add_job(
                lambda u=uid_copy, text=item_copy['text']: bot.send_message(int(u), f'🔔 Напоминание: {text}'),
                'date',
                run_date=t
            )

for uid, data in daily_settings.items():
    time_str = data.get("time", "")
    if re.match(r'^\d{1,2}:\d{2}$', time_str):
        try:
            hour, minute = map(int, time_str.split(':'))
            scheduler.add_job(lambda u=uid: send_daily(u), 'cron', hour=hour, minute=minute, id=f'daily_{uid}', replace_existing=True)
        except Exception as e:
            print(f"⛔ Ошибка в расписании пользователя {uid}: {e}")
    else:
        print(f"⚠️ Пропущено некорректное время у {uid}: '{time_str}'")

@bot.message_handler(commands=['start'])
def start(msg):
    bot.send_message(msg.chat.id, "Привет! Я бот-помощник.\nКоманды:\n/note — новая заметка\n/mynote — мои заметки\n/clearnotes — удалить все или по номеру\n/remind — напоминание\n/myreminders — мои напоминания\n/clearreminders — удалить все или по номеру\n/settings — основной чат\n/daily — ежедневная сводка")

@bot.message_handler(commands=['note'])
def note(msg):
    bot.send_message(msg.chat.id, "✏️ Введи текст заметки:")
    bot.register_next_step_handler(msg, lambda m: save_note(m, str(m.chat.id)))

def save_note(msg, uid):
    notes.setdefault(uid, []).append(msg.text)
    save_json('notes.json', notes)
    bot.send_message(msg.chat.id, "💾 Заметка сохранена!")

@bot.message_handler(commands=['mynote'])
def mynotes(msg):
    uid = str(msg.chat.id)
    user_notes = notes.get(uid, [])
    if user_notes:
        msg_txt = '\n'.join(f'{i+1}) {n}' for i, n in enumerate(user_notes))
        bot.send_message(msg.chat.id, f"🗒 Твои заметки:\n{msg_txt}")
    else:
        bot.send_message(msg.chat.id, "📭 Нет заметок.")

@bot.message_handler(commands=['clearnotes'])
def clearnotes(msg):
    uid = str(msg.chat.id)
    user_notes = notes.get(uid, [])
    if user_notes:
        msg_txt = '\n'.join(f'{i+1}) {n}' for i, n in enumerate(user_notes))
        bot.send_message(msg.chat.id, f"🗒 Заметки:\n{msg_txt}\n\nНапиши номер заметки для удаления или 'все'")
        bot.register_next_step_handler(msg, lambda m: process_clearnotes(m, uid))
    else:
        bot.send_message(msg.chat.id, "📭 Нет заметок.")

def process_clearnotes(msg, uid):
    if msg.text.lower() == 'все':
        notes[uid] = []
    else:
        try:
            idx = int(msg.text) - 1
            del notes[uid][idx]
        except:
            bot.send_message(msg.chat.id, '⚠️ Ошибка. Укажи номер.')
            return
    save_json('notes.json', notes)
    bot.send_message(msg.chat.id, '✅ Готово.')

@bot.message_handler(commands=['remind'])
def remind(msg):
    bot.send_message(msg.chat.id, "🕒 Введи напоминание в формате: Текст, время (например: 'Позвонить, в 15:45' или 'Позвонить, через 10 минут')")
    bot.register_next_step_handler(msg, lambda m: parse_reminder(m, str(m.chat.id)))

def parse_reminder(msg, uid):
    try:
        txt = msg.text.strip()
        if ',' not in txt:
            raise ValueError()
        text, raw_time = map(str.strip, re.split(r'[,;:]', txt, maxsplit=1))

        now = datetime.now()
        if 'через' in raw_time:
            mins = int(re.findall(r'(\d+)', raw_time)[0])
            remind_time = now + timedelta(minutes=mins)
        elif re.match(r'\d{1,2}[-\\/.,:;]\d{2}', raw_time):
            parts = re.split(r'[-\\/.,:;]', raw_time)
            remind_time = now.replace(hour=int(parts[0]), minute=int(parts[1]), second=0, microsecond=0)
            if remind_time < now:
                remind_time += timedelta(days=1)
        elif re.match(r'\d{1,2}-\d{1,2}-\d{4}', raw_time):
            remind_time = datetime.strptime(raw_time, '%d-%m-%Y')
        else:
            raise ValueError()

        reminders.setdefault(uid, []).append({'text': text, 'time': remind_time.strftime('%Y-%m-%d %H:%M')})
        save_json('reminders.json', reminders)
        scheduler.add_job(lambda u=uid, t=text: bot.send_message(int(u), f'🔔 Напоминание: {t}'), 'date', run_date=remind_time)
        bot.send_message(msg.chat.id, "✅ Напоминание установлено!")
    except:
        bot.send_message(msg.chat.id, "⚠️ Не понял. Пример: Купить хлеб, в 12:30 или через 5 минут")

@bot.message_handler(commands=['myreminders'])
def show_reminders(msg):
    uid = str(msg.chat.id)
    rlist = reminders.get(uid, [])
    if rlist:
        reply = '\n'.join(f"{i+1}) {r['text']} — {r['time']}" for i, r in enumerate(rlist))
        bot.send_message(msg.chat.id, f"📅 Напоминания:\n{reply}")
    else:
        bot.send_message(msg.chat.id, "📭 Нет напоминаний.")

@bot.message_handler(commands=['clearreminders'])
def clear_reminders(msg):
    uid = str(msg.chat.id)
    rlist = reminders.get(uid, [])
    if rlist:
        reply = '\n'.join(f"{i+1}) {r['text']} — {r['time']}" for i, r in enumerate(rlist))
        bot.send_message(msg.chat.id, f"📅 Напоминания:\n{reply}\n\nНапиши номер напоминания для удаления или 'все'")
        bot.register_next_step_handler(msg, lambda m: process_clearreminders(m, uid))
    else:
        bot.send_message(msg.chat.id, "📭 Нет напоминаний.")

def process_clearreminders(msg, uid):
    if msg.text.lower() == 'все':
        reminders[uid] = []
    else:
        try:
            idx = int(msg.text) - 1
            del reminders[uid][idx]
        except:
            bot.send_message(msg.chat.id, '⚠️ Ошибка. Укажи номер.')
            return
    save_json('reminders.json', reminders)
    bot.send_message(msg.chat.id, '✅ Удалено.')

@bot.message_handler(commands=['settings'])
def settings(msg):
    uid = str(msg.chat.id)
    user_settings[uid] = uid
    save_json('user_settings.json', user_settings)
    bot.send_message(msg.chat.id, '✅ Этот чат сохранён.')

@bot.message_handler(commands=['daily'])
def daily(msg):
    uid = str(msg.chat.id)
    bot.send_message(msg.chat.id, '🕗 Во сколько присылать сводку? (напр. 08:00)')
    bot.register_next_step_handler(msg, lambda m: daily_city(m, uid))

def daily_city(msg, uid):
    time_str = msg.text.strip()
    if not re.match(r'^\d{1,2}:\d{2}$', time_str):
        bot.send_message(msg.chat.id, '⚠️ Неверный формат. Пример: 08:00')
        return
    daily_settings[uid] = {'time': time_str}
    bot.send_message(msg.chat.id, '🏙 Укажи город или города через запятую:')
    bot.register_next_step_handler(msg, lambda m: daily_currency(m, uid))

def daily_currency(msg, uid):
    cities = [c.strip() for c in msg.text.split(',') if c.strip()]
    daily_settings[uid]['cities'] = cities
    bot.send_message(msg.chat.id, '💱 Какие валюты интересуют? (например: USD, EUR, RUB, KZT или "все")')
    bot.register_next_step_handler(msg, lambda m: finish_daily_setup(m, uid))

def finish_daily_setup(msg, uid):
    raw = msg.text.strip()
    if raw.lower() == 'все':
        currencies = list(get_currency().keys())
    else:
        currencies = [v.strip().upper() for v in raw.split(',') if v.strip()]
    daily_settings[uid]['currencies'] = currencies
    save_json('daily_settings.json', daily_settings)
    hour, minute = map(int, daily_settings[uid]['time'].split(':'))
    scheduler.add_job(lambda u=uid: send_daily(u), 'cron', hour=hour, minute=minute, id=f'daily_{uid}', replace_existing=True)
    bot.send_message(int(uid), f"✅ Сводка будет присылаться в {daily_settings[uid]['time']}")

def send_daily(uid):
    uid = str(uid)
    data = daily_settings.get(uid, {})
    cities = data.get('cities', ['Moscow'])
    currencies = data.get('currencies', ['USD'])

    parts = []
    for city in cities:
        w = get_weather(city)
        parts.append(f"🌆 {city.title()}\n🌡 {w['temp']}°C, 🌬 {w['wind']} м/с, ☁ {w['clouds']}%")

    exchange = get_currency()
    cur_lines = [f"💱 {c}: {exchange.get(c, '–')}₽" for c in currencies]
    final_msg = f"☀️ Утреняя сводка:\n\n" + '\n\n'.join(parts) + '\n\n' + '\n'.join(cur_lines)
    bot.send_message(int(user_settings.get(uid, uid)), final_msg)

def get_weather(city):
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={OPENWEATHER_API_KEY}&units=metric&lang=ru"
        r = requests.get(url)
        d = r.json()
        return {'temp': d['main']['temp'], 'wind': d['wind']['speed'], 'clouds': d['clouds']['all']}
    except:
        return {'temp': '?', 'wind': '?', 'clouds': '?'}

def get_currency():
    try:
        r = requests.get("https://www.cbr-xml-daily.ru/daily_json.js")
        d = r.json()
        return {k: round(v['Value'], 2) for k, v in d['Valute'].items()}
    except:
        return {}

def save_json(filename, data):
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Ошибка при сохранении {filename}: {e}")

print("✅ Бот запущен")
bot.infinity_polling()

