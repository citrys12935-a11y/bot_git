import sqlite3
import json
from datetime import datetime
import os

class Database:
    def __init__(self):
        self.conn = sqlite3.connect('economy.db')
        self.create_tables()
    
    def create_tables(self):
        cursor = self.conn.cursor()
        
        # Основная таблица пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER,
                guild_id INTEGER,
                balance INTEGER DEFAULT 0,
                xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 1,
                warnings INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, guild_id)
            )
        ''')
        
        # Множители ролей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS role_multipliers (
                role_id INTEGER PRIMARY KEY,
                economy_multiplier REAL DEFAULT 1.0,
                xp_multiplier REAL DEFAULT 1.0
            )
        ''')
        
        # Настройки серверов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS server_settings (
                guild_id INTEGER PRIMARY KEY,
                work_reward_min INTEGER DEFAULT 10,
                work_reward_max INTEGER DEFAULT 50,
                work_cooldown INTEGER DEFAULT 3600,
                xp_per_message INTEGER DEFAULT 5,
                xp_per_voice_minute INTEGER DEFAULT 2,
                slot_min_bet INTEGER DEFAULT 1,
                slot_max_bet INTEGER DEFAULT 1000,
                prefix TEXT DEFAULT '!',
                logs_enabled BOOLEAN DEFAULT 0,
                log_channel_id INTEGER DEFAULT NULL
            )
        ''')
        
        # Кулдауны
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cooldowns (
                user_id INTEGER,
                guild_id INTEGER,
                command TEXT,
                last_used INTEGER,
                PRIMARY KEY (user_id, guild_id, command)
            )
        ''')

        # Права команд
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS command_permissions (
                guild_id INTEGER,
                role_group TEXT,
                command_name TEXT,
                PRIMARY KEY (guild_id, role_group, command_name)
            )
        ''')

        # Назначения ролей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS role_assignments (
                guild_id INTEGER,
                role_group TEXT,
                role_id INTEGER,
                PRIMARY KEY (guild_id, role_group, role_id)
            )
        ''')

        # Розыгрыши
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS giveaways (
                message_id INTEGER PRIMARY KEY,
                guild_id INTEGER,
                channel_id INTEGER,
                prize TEXT,
                winners_count INTEGER,
                end_time INTEGER,
                ended BOOLEAN DEFAULT 0
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS giveaway_entries (
                message_id INTEGER,
                user_id INTEGER,
                PRIMARY KEY (message_id, user_id)
            )
        ''')

        # Магазин
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS shop_items (
                item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER,
                name TEXT,
                description TEXT,
                price INTEGER,
                item_type TEXT,
                role_id INTEGER DEFAULT NULL,
                duration INTEGER DEFAULT 0,
                max_purchases INTEGER DEFAULT -1,
                created_at INTEGER
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_inventory (
                user_id INTEGER,
                guild_id INTEGER,
                item_id INTEGER,
                purchase_time INTEGER,
                expires_at INTEGER DEFAULT NULL,
                PRIMARY KEY (user_id, guild_id, item_id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS item_purchases (
                user_id INTEGER,
                guild_id INTEGER,
                item_id INTEGER,
                purchase_count INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, guild_id, item_id)
            )
        ''')

        # Торговая площадка
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS marketplace (
                listing_id INTEGER PRIMARY KEY AUTOINCREMENT,
                seller_id INTEGER,
                guild_id INTEGER,
                item_id INTEGER,
                price INTEGER,
                created_at INTEGER,
                status TEXT DEFAULT 'active'
            )
        ''')

        # Транзакции
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_user_id INTEGER,
                to_user_id INTEGER,
                guild_id INTEGER,
                item_id INTEGER,
                amount INTEGER,
                transaction_type TEXT,
                created_at INTEGER
            )
        ''')

        # Награды за уровни
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS level_rewards (
                guild_id INTEGER,
                level INTEGER,
                reward_type TEXT,
                role_id INTEGER DEFAULT NULL,
                currency_amount INTEGER DEFAULT 0,
                PRIMARY KEY (guild_id, level)
            )
        ''')

        # Тикет-группы
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ticket_groups (
                guild_id INTEGER,
                group_type TEXT,
                role_id INTEGER,
                PRIMARY KEY (guild_id, group_type)
            )
        ''')

        # Активные тикеты
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS active_tickets (
                channel_id INTEGER PRIMARY KEY,
                guild_id INTEGER,
                user_id INTEGER,
                ticket_type TEXT,
                created_at INTEGER
            )
        ''')

        self.conn.commit()
    
    def get_user(self, user_id, guild_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id = ? AND guild_id = ?', (user_id, guild_id))
        result = cursor.fetchone()
        if not result:
            cursor.execute('INSERT INTO users (user_id, guild_id) VALUES (?, ?)', (user_id, guild_id))
            self.conn.commit()
            return (user_id, guild_id, 0, 0, 1, 0)
        return result
    
    def set_command_permission(self, guild_id, role_group, command_name):
        cursor = self.conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO command_permissions (guild_id, role_group, command_name) VALUES (?, ?, ?)', 
                      (guild_id, role_group, command_name))
        self.conn.commit()

    def get_command_permissions(self, guild_id, role_group):
        cursor = self.conn.cursor()
        cursor.execute('SELECT command_name FROM command_permissions WHERE guild_id = ? AND role_group = ?', (guild_id, role_group))
        return [row[0] for row in cursor.fetchall()]

    def set_role_assignment(self, guild_id, role_group, role_id):
        cursor = self.conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO role_assignments (guild_id, role_group, role_id) VALUES (?, ?, ?)', 
                  (guild_id, role_group, role_id))
        self.conn.commit()

    def get_role_assignments(self, guild_id, role_group):
        cursor = self.conn.cursor()
        cursor.execute('SELECT role_id FROM role_assignments WHERE guild_id = ? AND role_group = ?', (guild_id, role_group))
        return [row[0] for row in cursor.fetchall()]

    def update_balance(self, user_id, guild_id, amount):
        cursor = self.conn.cursor()
        cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ? AND guild_id = ?', (amount, user_id, guild_id))
        self.conn.commit()
    
    def update_xp(self, user_id, guild_id, amount):
        cursor = self.conn.cursor()
        cursor.execute('UPDATE users SET xp = xp + ? WHERE user_id = ? AND guild_id = ?', (amount, user_id, guild_id))
        self.conn.commit()
    
    def set_balance(self, user_id, guild_id, amount):
        cursor = self.conn.cursor()
        cursor.execute('UPDATE users SET balance = ? WHERE user_id = ? AND guild_id = ?', (amount, user_id, guild_id))
        self.conn.commit()
    
    def set_xp(self, user_id, guild_id, amount):
        cursor = self.conn.cursor()
        cursor.execute('UPDATE users SET xp = ? WHERE user_id = ? AND guild_id = ?', (amount, user_id, guild_id))
        self.conn.commit()
    
    def set_level(self, user_id, guild_id, level):
        cursor = self.conn.cursor()
        cursor.execute('UPDATE users SET level = ? WHERE user_id = ? AND guild_id = ?', (level, user_id, guild_id))
        self.conn.commit()
    
    def get_leaderboard_ec(self, guild_id, limit=10):
        cursor = self.conn.cursor()
        cursor.execute('SELECT user_id, balance FROM users WHERE guild_id = ? ORDER BY balance DESC LIMIT ?', (guild_id, limit))
        return cursor.fetchall()
    
    def get_leaderboard_lv(self, guild_id, limit=10):
        cursor = self.conn.cursor()
        cursor.execute('SELECT user_id, level, xp FROM users WHERE guild_id = ? ORDER BY level DESC, xp DESC LIMIT ?', (guild_id, limit))
        return cursor.fetchall()
    
    def get_role_multiplier(self, role_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT economy_multiplier, xp_multiplier FROM role_multipliers WHERE role_id = ?', (role_id,))
        return cursor.fetchone()
    
    def set_role_multiplier(self, role_id, eco_mult, xp_mult):
        cursor = self.conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO role_multipliers (role_id, economy_multiplier, xp_multiplier) VALUES (?, ?, ?)', (role_id, eco_mult, xp_mult))
        self.conn.commit()
    
    def get_server_settings(self, guild_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM server_settings WHERE guild_id = ?', (guild_id,))
        result = cursor.fetchone()
        if not result:
            cursor.execute('INSERT INTO server_settings (guild_id) VALUES (?)', (guild_id,))
            self.conn.commit()
            return (guild_id, 10, 50, 3600, 5, 2, 1, 1000, '!', 0, None)
        return result
    
    def update_server_settings(self, guild_id, **kwargs):
        cursor = self.conn.cursor()
        settings = self.get_server_settings(guild_id)
        setting_names = ['work_reward_min', 'work_reward_max', 'work_cooldown', 'xp_per_message', 
                        'xp_per_voice_minute', 'slot_min_bet', 'slot_max_bet', 'prefix', 
                        'logs_enabled', 'log_channel_id']
        
        updates = []
        values = []
        for name in setting_names:
            if name in kwargs:
                updates.append(f"{name} = ?")
                values.append(kwargs[name])
        
        if updates:
            values.append(guild_id)
            cursor.execute(f'UPDATE server_settings SET {", ".join(updates)} WHERE guild_id = ?', values)
            self.conn.commit()
    
    def set_cooldown(self, user_id, guild_id, command):
        cursor = self.conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO cooldowns (user_id, guild_id, command, last_used) VALUES (?, ?, ?, ?)', 
                      (user_id, guild_id, command, int(datetime.now().timestamp())))
        self.conn.commit()
    
    def get_cooldown(self, user_id, guild_id, command):
        cursor = self.conn.cursor()
        cursor.execute('SELECT last_used FROM cooldowns WHERE user_id = ? AND guild_id = ? AND command = ?', 
                      (user_id, guild_id, command))
        result = cursor.fetchone()
        return result[0] if result else None

    def set_warnings(self, user_id, guild_id, warnings):
        cursor = self.conn.cursor()
        cursor.execute('UPDATE users SET warnings = ? WHERE user_id = ? AND guild_id = ?', (warnings, user_id, guild_id))
        self.conn.commit()

    # Магазин методы
    def add_shop_item(self, guild_id, name, description, price, item_type, role_id=None, duration=0, max_purchases=-1):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO shop_items (guild_id, name, description, price, item_type, role_id, duration, max_purchases, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (guild_id, name, description, price, item_type, role_id, duration, max_purchases, int(datetime.now().timestamp())))
        self.conn.commit()
        return cursor.lastrowid

    def get_shop_items(self, guild_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM shop_items WHERE guild_id = ? ORDER BY price ASC', (guild_id,))
        return cursor.fetchall()

    def get_shop_item(self, item_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM shop_items WHERE item_id = ?', (item_id,))
        return cursor.fetchone()

    def delete_shop_item(self, item_id):
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM shop_items WHERE item_id = ?', (item_id,))
        self.conn.commit()

    def purchase_item(self, user_id, guild_id, item_id):
        cursor = self.conn.cursor()
        
        item = self.get_shop_item(item_id)
        if not item:
            return False, "Предмет не найден"
        
        if item[8] != -1:
            cursor.execute('SELECT purchase_count FROM item_purchases WHERE user_id = ? AND guild_id = ? AND item_id = ?', 
                         (user_id, guild_id, item_id))
            purchase_data = cursor.fetchone()
            if purchase_data and purchase_data[0] >= item[8]:
                return False, f"Вы уже купили максимальное количество этого предмета ({item[8]})"
        
        user_data = self.get_user(user_id, guild_id)
        if user_data[2] < item[4]:
            return False, "Недостаточно монет"
        
        expires_at = None
        if item[7] > 0:
            expires_at = int(datetime.now().timestamp()) + item[7]
        
        cursor.execute('''
            INSERT OR REPLACE INTO user_inventory (user_id, guild_id, item_id, purchase_time, expires_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, guild_id, item_id, int(datetime.now().timestamp()), expires_at))
        
        cursor.execute('''
            INSERT OR REPLACE INTO item_purchases (user_id, guild_id, item_id, purchase_count)
            VALUES (?, ?, ?, COALESCE((SELECT purchase_count FROM item_purchases WHERE user_id = ? AND guild_id = ? AND item_id = ?), 0) + 1)
        ''', (user_id, guild_id, item_id, user_id, guild_id, item_id))
        
        cursor.execute('UPDATE users SET balance = balance - ? WHERE user_id = ? AND guild_id = ?', 
                     (item[4], user_id, guild_id))
        
        self.conn.commit()
        return True, "Покупка успешна"

    def get_user_inventory(self, user_id, guild_id):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT ui.*, si.name, si.description, si.item_type, si.role_id, si.duration
            FROM user_inventory ui
            JOIN shop_items si ON ui.item_id = si.item_id
            WHERE ui.user_id = ? AND ui.guild_id = ?
            ORDER BY ui.purchase_time DESC
        ''', (user_id, guild_id))
        return cursor.fetchall()

    def get_expired_items(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM user_inventory 
            WHERE expires_at IS NOT NULL AND expires_at <= ?
        ''', (int(datetime.now().timestamp()),))
        return cursor.fetchall()

    def remove_inventory_item(self, user_id, guild_id, item_id):
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM user_inventory WHERE user_id = ? AND guild_id = ? AND item_id = ?', 
                     (user_id, guild_id, item_id))
        self.conn.commit()

    # Торговая площадка методы
    def add_market_listing(self, seller_id, guild_id, item_id, price):
        cursor = self.conn.cursor()
        
        cursor.execute('''
            INSERT INTO marketplace (seller_id, guild_id, item_id, price, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (seller_id, guild_id, item_id, price, int(datetime.now().timestamp())))
        
        self.conn.commit()
        return cursor.lastrowid

    def get_market_listings(self, guild_id, status='active'):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT m.*, si.name, si.description, si.item_type, u.balance as seller_balance
            FROM marketplace m
            JOIN shop_items si ON m.item_id = si.item_id
            JOIN users u ON m.seller_id = u.user_id AND m.guild_id = u.guild_id
            WHERE m.guild_id = ? AND m.status = ?
            ORDER BY m.created_at DESC
        ''', (guild_id, status))
        return cursor.fetchall()

    def get_market_listing(self, listing_id):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT m.*, si.name, si.description, si.item_type
            FROM marketplace m
            JOIN shop_items si ON m.item_id = si.item_id
            WHERE m.listing_id = ?
        ''', (listing_id,))
        return cursor.fetchone()

    def purchase_market_item(self, buyer_id, guild_id, listing_id):
        cursor = self.conn.cursor()
        
        listing = self.get_market_listing(listing_id)
        if not listing:
            return False, "Предложение не найдено"
        
        if listing[6] != 'active':
            return False, "Это предложение уже продано или отменено"
        
        buyer_data = self.get_user(buyer_id, guild_id)
        if buyer_data[2] < listing[4]:
            return False, "Недостаточно монет"
        
        seller_id = listing[1]
        
        if buyer_id == seller_id:
            return False, "Нельзя купить свой же предмет"
        
        item_info = self.get_shop_item(listing[3])
        if not item_info:
            return False, "Предмет не найден в магазине"
        
        expires_at = None
        if item_info[7] > 0:
            expires_at = int(datetime.now().timestamp()) + item_info[7]
        
        cursor.execute('''
            INSERT OR REPLACE INTO user_inventory (user_id, guild_id, item_id, purchase_time, expires_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (buyer_id, guild_id, listing[3], int(datetime.now().timestamp()), expires_at))
        
        cursor.execute('UPDATE users SET balance = balance - ? WHERE user_id = ? AND guild_id = ?', 
                     (listing[4], buyer_id, guild_id))
        
        cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ? AND guild_id = ?', 
                     (listing[4], seller_id, guild_id))
        
        cursor.execute('UPDATE marketplace SET status = ? WHERE listing_id = ?', 
                     ('sold', listing_id))
        
        self.add_transaction(seller_id, buyer_id, guild_id, listing[3], listing[4], 'market_sale')
        
        self.conn.commit()
        return True, "Покупка успешна"

    def remove_market_listing(self, listing_id):
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM marketplace WHERE listing_id = ?', (listing_id,))
        self.conn.commit()

    def get_user_market_listings(self, user_id, guild_id):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT m.*, si.name, si.description, si.item_type
            FROM marketplace m
            JOIN shop_items si ON m.item_id = si.item_id
            WHERE m.seller_id = ? AND m.guild_id = ? AND m.status = 'active'
            ORDER BY m.created_at DESC
        ''', (user_id, guild_id))
        return cursor.fetchall()

    # Транзакции
    def add_transaction(self, from_user_id, to_user_id, guild_id, item_id, amount, transaction_type):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO transactions (from_user_id, to_user_id, guild_id, item_id, amount, transaction_type, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (from_user_id, to_user_id, guild_id, item_id, amount, transaction_type, int(datetime.now().timestamp())))
        self.conn.commit()

    def get_user_transactions(self, user_id, guild_id, limit=10):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM transactions 
            WHERE (from_user_id = ? OR to_user_id = ?) AND guild_id = ?
            ORDER BY created_at DESC 
            LIMIT ?
        ''', (user_id, user_id, guild_id, limit))
        return cursor.fetchall()

    # Награды за уровни
    def set_level_reward(self, guild_id, level, reward_type, role_id=None, currency_amount=0):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO level_rewards (guild_id, level, reward_type, role_id, currency_amount)
            VALUES (?, ?, ?, ?, ?)
        ''', (guild_id, level, reward_type, role_id, currency_amount))
        self.conn.commit()

    def get_level_reward(self, guild_id, level):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM level_rewards WHERE guild_id = ? AND level = ?', (guild_id, level))
        return cursor.fetchone()

    def get_all_level_rewards(self, guild_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM level_rewards WHERE guild_id = ? ORDER BY level ASC', (guild_id,))
        return cursor.fetchall()

    def delete_level_reward(self, guild_id, level):
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM level_rewards WHERE guild_id = ? AND level = ?', (guild_id, level))
        self.conn.commit()

    # Тикеты
    def set_ticket_group(self, guild_id, group_type, role_id):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO ticket_groups (guild_id, group_type, role_id)
            VALUES (?, ?, ?)
        ''', (guild_id, group_type, role_id))
        self.conn.commit()

    def get_ticket_group(self, guild_id, group_type):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM ticket_groups WHERE guild_id = ? AND group_type = ?', (guild_id, group_type))
        result = cursor.fetchone()
        return result[2] if result else None

    def get_all_ticket_groups(self, guild_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM ticket_groups WHERE guild_id = ?', (guild_id,))
        return cursor.fetchall()

    def create_ticket(self, channel_id, guild_id, user_id, ticket_type):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO active_tickets (channel_id, guild_id, user_id, ticket_type, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (channel_id, guild_id, user_id, ticket_type, int(datetime.now().timestamp())))
        self.conn.commit()

    def get_ticket(self, channel_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM active_tickets WHERE channel_id = ?', (channel_id,))
        return cursor.fetchone()

    def get_user_tickets(self, user_id, guild_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM active_tickets WHERE user_id = ? AND guild_id = ?', (user_id, guild_id))
        return cursor.fetchall()

    def delete_ticket(self, channel_id):
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM active_tickets WHERE channel_id = ?', (channel_id,))
        self.conn.commit()

    def get_all_tickets(self, guild_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM active_tickets WHERE guild_id = ?', (guild_id,))
        return cursor.fetchall()

    # Очистка данных сервера при выходе бота
    def cleanup_guild_data(self, guild_id):
        cursor = self.conn.cursor()
        
        # Удаляем данные пользователей этого сервера
        cursor.execute('DELETE FROM users WHERE guild_id = ?', (guild_id,))
        
        # Удаляем настройки сервера
        cursor.execute('DELETE FROM server_settings WHERE guild_id = ?', (guild_id,))
        
        # Удаляем кулдауны
        cursor.execute('DELETE FROM cooldowns WHERE guild_id = ?', (guild_id,))
        
        # Удаляем права команд
        cursor.execute('DELETE FROM command_permissions WHERE guild_id = ?', (guild_id,))
        
        # Удаляем назначения ролей
        cursor.execute('DELETE FROM role_assignments WHERE guild_id = ?', (guild_id,))
        
        # Удаляем предметы магазина
        cursor.execute('DELETE FROM shop_items WHERE guild_id = ?', (guild_id,))
        
        # Удаляем инвентари
        cursor.execute('DELETE FROM user_inventory WHERE guild_id = ?', (guild_id,))
        
        # Удаляем покупки
        cursor.execute('DELETE FROM item_purchases WHERE guild_id = ?', (guild_id,))
        
        # Удаляем предложения торговой площадки
        cursor.execute('DELETE FROM marketplace WHERE guild_id = ?', (guild_id,))
        
        # Удаляем транзакции
        cursor.execute('DELETE FROM transactions WHERE guild_id = ?', (guild_id,))
        
        # Удаляем награды за уровни
        cursor.execute('DELETE FROM level_rewards WHERE guild_id = ?', (guild_id,))
        
        # Удаляем группы тикетов
        cursor.execute('DELETE FROM ticket_groups WHERE guild_id = ?', (guild_id,))
        
        # Удаляем активные тикеты
        cursor.execute('DELETE FROM active_tickets WHERE guild_id = ?', (guild_id,))
        
        self.conn.commit()