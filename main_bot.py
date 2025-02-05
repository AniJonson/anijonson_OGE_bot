import telebot
import time
from telebot import types
import json
import os
import requests
from collections import defaultdict

API_TOKEN = 'token'

bot = telebot.TeleBot(API_TOKEN)
ADMIN_IDS = [IDs]
ADMIN_ROLES = {
    ID1: "Name",
    ID2: "Name"
}
DATA_FILE = 'oge_data.json'
LOG_FILE = 'oge_history.json'


def create_log_file():
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'w', encoding='utf-8') as f:
            json.dump([], f, ensure_ascii=False, indent=4)

def log_event(event_type, user_id=None, message_text=None):
    create_log_file()
    log_entry = {
        "time": time.strftime('%Y-%m-%d %H:%M:%S'),
        "type": event_type,
        "user_id": user_id,
        "message": message_text
    }
    try:
        with open(LOG_FILE, 'r+', encoding='utf-8') as f:
            logs = json.load(f)
            logs.append(log_entry)
            f.seek(0)
            json.dump(logs, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Ошибка записи лога: {e}")

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return create_default_data()
    else:
        return create_default_data()

def create_default_data():
    return {
        'ban_list': [],
        'user_states': {},
        'user_message_count': {},
        'user_last_message_time': {},
        'total_messages_sent': 0,
        'user_info': {}  
    }

def save_data(data):
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception:
        pass

data = load_data()
ban_list = set(data['ban_list'])
user_states = data['user_states']
user_message_count = defaultdict(int, data['user_message_count'])
user_last_message_time = data['user_last_message_time']
total_messages_sent = data['total_messages_sent']
user_info = data['user_info']

def is_user_allowed(message):
    return message.from_user.id not in ban_list

@bot.message_handler(commands=['suggest'], func=is_user_allowed)
def suggest_command(message):
    user_states[message.from_user.id] = 'suggest_mode'
    bot.send_message(message.chat.id, "Пожалуйста, отправьте ваше сообщение админам.")
    log_event("command", message.from_user.id, "/suggest")

@bot.message_handler(func=lambda message: user_states.get(message.from_user.id) == 'suggest_mode',
                     content_types=['text', 'photo', 'audio', 'document', 'video', 'voice', 'video_note', 'sticker', 'animation'])
def suggest_state(message):
    global total_messages_sent
    total_messages_sent += 1
    user_id = message.from_user.id
    current_time = time.time()

    if user_id in user_last_message_time:
        if current_time - user_last_message_time[user_id] < 30 and user_message_count[user_id] >= 2:
            bot.send_message(message.chat.id, "Ошибка отправки. Попробуйте через 30 секунд.")
            log_event("error", user_id, "Rate limit exceeded")
            return
        if current_time - user_last_message_time[user_id] >= 30:
            user_message_count[user_id] = 0

    user_last_message_time[user_id] = current_time
    user_message_count[user_id] += 1

    user = message.from_user
    user_info[user_id] = {
        "first_name": user.first_name,
        "last_name": user.last_name if user.last_name else "",
        "username": user.username if user.username else "Неизвестно",
        "messages_sent": user_message_count[user_id],
        "is_banned": user_id in ban_list
    }

    markup = types.InlineKeyboardMarkup().add(
        types.InlineKeyboardButton("Ответить", callback_data=f'reply_{message.from_user.id}'),
        types.InlineKeyboardButton("Бан", callback_data=f'ban_{message.from_user.id}'),
        types.InlineKeyboardButton("Отправитель", callback_data=f'info_{message.from_user.id}')
    )

    for admin_id in ADMIN_IDS:
        try:
            bot.forward_message(admin_id, message.chat.id, message.message_id)
            bot.send_message(admin_id, "Выберите одну из кнопок:", reply_markup=markup)
        except Exception as e:
            log_event("error", user_id, f"Error forwarding message: {e}")

    bot.send_message(message.chat.id, f"Ваше сообщение было отправлено! Мы обязательно свяжемся с вами. #{total_messages_sent}")
    log_event("message", user_id, "Message sent to admins")
    del user_states[message.from_user.id]

    data['ban_list'] = list(ban_list)
    data['user_states'] = user_states
    data['user_message_count'] = dict(user_message_count)
    data['user_last_message_time'] = user_last_message_time
    data['total_messages_sent'] = total_messages_sent
    data['user_info'] = user_info
    save_data(data)

@bot.callback_query_handler(func=lambda call: call.data.startswith(('reply_', 'ban_', 'info_')))
def handle_callback(call):
    action, user_id = call.data.split('_')
    user_id = int(user_id)

    if action == 'reply':
        bot.send_message(call.message.chat.id, "Введите ваш ответ:")
        user_states[call.from_user.id] = f'reply_to_{user_id}'
        log_event("admin_action", call.from_user.id, f"Reply to {user_id}")
    elif action == 'ban':
        if user_id in ban_list:
            ban_list.remove(user_id)
            bot.send_message(call.message.chat.id, f"Пользователь {user_id} разбанен.")
            log_event("admin_action", call.from_user.id, f"Unbanned {user_id}")
        else:
            ban_list.add(user_id)
            bot.send_message(call.message.chat.id, f"Пользователь {user_id} забанен.")
            log_event("admin_action", call.from_user.id, f"Banned {user_id}")
    elif action == 'info':
        user_name = "Неизвестно"
        message_count = user_message_count.get(user_id, 0)
        is_banned = "Да" if user_id in ban_list else "Нет"

        user_data = user_info.get(user_id, {})
        first_name = user_data.get("first_name", "Неизвестно")
        last_name = user_data.get("last_name", "")
        username = user_data.get("username", "Неизвестно")

        bot.send_message(call.message.chat.id, f"Информация о пользователе:\n"
                                               f"ID: {user_id}\n"
                                               f"Имя: {first_name} {last_name}\n"
                                               f"Username: {username}\n"
                                               f"Отправлено сообщений: {message_count}\n"
                                               f"Забанен: {is_banned}")
        log_event("admin_action", call.from_user.id, f"Requested info for {user_id}")

    data['ban_list'] = list(ban_list)
    data['user_states'] = user_states
    data['user_message_count'] = dict(user_message_count)
    data['user_last_message_time'] = user_last_message_time
    data['total_messages_sent'] = total_messages_sent
    data['user_info'] = user_info 
    save_data(data)

@bot.message_handler(func=lambda message: user_states.get(message.from_user.id, '').startswith('reply_to_'))
def handle_admin_reply(message):
    admin_id = message.from_user.id
    user_id = int(user_states[admin_id].split('_')[2])

    admin_role = ADMIN_ROLES.get(admin_id, "Неизвестно")
    bot.send_message(user_id, f"Ответ от {admin_role}: {message.text}")
    bot.send_message(admin_id, "Ваш ответ был отправлен пользователю.")
    
    del user_states[admin_id]
    log_event("admin_reply", admin_id, f"Replied to user {user_id} with message: {message.text}")

    data['user_states'] = user_states
    save_data(data)

@bot.message_handler(commands=['code', 'data', 'history'])
def admin_commands(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.send_message(message.chat.id, "У вас нет прав для выполнения этой команды.")
        log_event("unauthorized_access", message.from_user.id, message.text)
        return

    command = message.text.split()[0][1:]
    try:
        if command == 'code':
            bot.send_document(message.chat.id, open('bot_ideal.py', 'rb'))
            log_event("admin_command", message.from_user.id, "/code executed")
        elif command == 'data':
            if os.path.exists(DATA_FILE):
                bot.send_document(message.chat.id, open(DATA_FILE, 'rb'))
                log_event("admin_command", message.from_user.id, "/data executed")
            else:
                bot.send_message(message.chat.id, "Файл data.json не найден.")
        elif command == 'history':
            if os.path.exists(LOG_FILE):
                bot.send_document(message.chat.id, open(LOG_FILE, 'rb'))
                log_event("admin_command", message.from_user.id, "/history executed")
            else:
                bot.send_message(message.chat.id, "Файл history.json не найден.")
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка при выполнении команды: {e}")
        log_event("error", message.from_user.id, f"Error executing {command}: {e}")
@bot.message_handler(commands=['set_topic'])
def set_topic(message):
    topics = (
        
        "**[Разбор заданий первой части ОГЭ по информатике](https://telegra.ph/Razbor-zadanij-pervoj-chasti-OGEH-01-19)**\n\n"
        
        
        "**[Основы информатики](https://telegra.ph/Osnovy-informatiki-01-19)**\n\n"
        
        
        "**[Руководства по некоторым языкам программирования](https://telegra.ph/Osnovy-nekotoryh-yazykov-programmirovaniya-01-20)**"
    )
    
    bot.send_message(message.chat.id, topics, parse_mode="Markdown", disable_web_page_preview=True)
@bot.message_handler(commands=['start'])
def start_command(message):
    bot.send_message(message.chat.id, f"Привет, {message.from_user.first_name}! Добро пожаловать в нашего бота.\n\n"
                                      f"Здесь ты сможешь найти материалы для подготовки к ОГЭ по информатике! Для этого используй команду /set_topic\n\n"
                                      f"Для того, чтобы связаться с поддержкой, используй команду /suggest\n\n"
                                      f"Powered by @AniJonson\n")
    log_event("command", message.from_user.id, "/start")
def is_user_allowed(message):
    return message.from_user.id not in ban_list

@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    log_event("message", message.from_user.id, message.text)


def retry_polling():
    while True:
        try:
            bot.polling(none_stop=True)
        except requests.exceptions.ConnectionError as e:
            print("Произошла ошибка подключения. Повтор через 5 секунд...")
            log_event("error", None, f"Ошибка подключения: {e}")
            time.sleep(5)
        except Exception as e:
            print(f"Произошла непредвиденная ошибка: {e}")
            log_event("error", None, f"Неожиданная ошибка: {e}")
            time.sleep(5)

retry_polling()
