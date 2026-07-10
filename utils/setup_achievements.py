import sqlite3
from datetime import datetime

def setup_default_achievements(guild_id):
    """Создание стандартных достижений для нового сервера"""
    conn = sqlite3.connect('economy.db')
    cursor = conn.cursor()
    
    cursor.execute("PRAGMA table_info(banners)")
    columns = [column[1] for column in cursor.fetchall()]
    if 'is_exclusive' not in columns:
        cursor.execute('ALTER TABLE banners ADD COLUMN is_exclusive BOOLEAN DEFAULT 0')
        print(f"✅ Добавлено поле is_exclusive в таблицу banners")
    
    default_achievements = [
        (guild_id, "Новичок", "Достигнуть 5 уровня", "🌱", "common", 100, 50, "level", 5, 0),
        (guild_id, "Опытный", "Достигнуть 10 уровня", "⭐", "rare", 500, 200, "level", 10, 0),
        (guild_id, "Ветеран", "Достигнуть 20 уровня", "🏆", "epic", 2000, 1000, "level", 20, 0),
        (guild_id, "Легенда", "Достигнуть 30 уровня", "👑", "legendary", 5000, 3000, "level", 30, 0),
        
        (guild_id, "Начинающий инвестор", "Накопить 1000 монет", "💰", "common", 0, 100, "balance", 1000, 0),
        (guild_id, "Состоятельный", "Накопить 10000 монет", "💎", "rare", 1000, 500, "balance", 10000, 0),
        (guild_id, "Миллионер", "Накопить 100000 монет", "🏦", "epic", 5000, 2000, "balance", 100000, 0),
        
        (guild_id, "Болтун", "Написать 100 сообщений", "💬", "common", 50, 25, "messages", 100, 0),
        (guild_id, "Активный участник", "Написать 500 сообщений", "📝", "rare", 200, 100, "messages", 500, 0),
        (guild_id, "Голос чата", "Написать 1000 сообщений", "🎤", "epic", 500, 250, "messages", 1000, 0),
        
        (guild_id, "Трудяга", "Выполнить work 50 раз", "💼", "common", 200, 100, "work_count", 50, 0),
        (guild_id, "Работяга", "Выполнить work 200 раз", "⚒️", "rare", 1000, 500, "work_count", 200, 0),
        
        (guild_id, "Счастливчик", "Выиграть джекпот в слотах", "🍀", "rare", 1000, 500, "slots_jackpot", 1, 1),
    ]
    
    created_at = int(datetime.now().timestamp())
    
    for achievement in default_achievements:
        cursor.execute('''
            INSERT OR IGNORE INTO achievements 
            (guild_id, name, description, icon, rarity, reward_currency, reward_xp, 
             requirement_type, requirement_value, is_secret, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (*achievement, created_at))
    
    default_banners = [
        (guild_id, "Стандартный", "https://i.imgur.com/placeholder.png", "common", 0, None, 1, 0),
        (guild_id, "Золотой", "https://i.imgur.com/placeholder2.png", "rare", 5000, None, 0, 0),
        (guild_id, "Легендарный", "https://i.imgur.com/placeholder3.png", "legendary", None, 4, 0, 0),  # Для ачивки ID 4
    ]
    
    for banner in default_banners:
        name, image_url, rarity, price, achievement_id, is_default, is_exclusive = banner[1:]
        cursor.execute('''
            INSERT OR IGNORE INTO banners 
            (guild_id, name, image_url, rarity, price, achievement_id, is_default, is_exclusive, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (guild_id, name, image_url, rarity, price, achievement_id, is_default, is_exclusive, created_at))
    
    conn.commit()
    conn.close()
    print(f"✅ Созданы стандартные достижения и баннеры для сервера {guild_id}")

def add_default_banner_to_users(guild_id):
    """Добавить баннер по умолчанию всем пользователям сервера"""
    conn = sqlite3.connect('economy.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT banner_id FROM banners WHERE guild_id = ? AND is_default = 1', (guild_id,))
    default_banner = cursor.fetchone()
    
    if not default_banner:
        print(f"⚠️ Баннер по умолчанию не найден для сервера {guild_id}")
        return
    
    banner_id = default_banner[0]
    
    cursor.execute('SELECT user_id FROM users WHERE guild_id = ?', (guild_id,))
    users = cursor.fetchall()
    
    for user_id in users:
        user_id = user_id[0]
        
        cursor.execute('''
            SELECT * FROM user_banners 
            WHERE user_id = ? AND guild_id = ? AND banner_id = ?
        ''', (user_id, guild_id, banner_id))
        
        if not cursor.fetchone():
            cursor.execute('''
                INSERT INTO user_banners (user_id, guild_id, banner_id, is_active, obtained_at)
                VALUES (?, ?, ?, 1, ?)
            ''', (user_id, guild_id, banner_id, int(datetime.now().timestamp())))
    
    conn.commit()
    conn.close()
    print(f"✅ Баннер по умолчанию добавлен пользователям сервера {guild_id}")