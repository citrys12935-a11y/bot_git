from flask import Flask
from threading import Thread
import os

app = Flask('')

@app.route('/')
def home():
    return "Бот работает!"

def run():
    # Берем порт из переменной окружения PORT, которую дает Render
    # Если PORT не найден, используем 8080 как запасной вариант
    port = int(os.environ.get('PORT', 8080))
    # Обязательно слушаем на 0.0.0.0
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()
