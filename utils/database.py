import sqlite3
import json
from datetime import datetime
import os
import time

class Database:
    def __init__(self):
        # Используем check_same_thread=False для работы в многопоточном окружении
        self.conn = sqlite3.connect('economy.db', timeout=30.0, check_same_thread=False)
        self.conn.execute('PRAGMA journal_mode=WAL')  # Включаем режим WAL
        self.conn.execute('PRAGMA busy_timeout=5000')  # Уменьшаем таймаут до 5 секунд
        self.conn.execute('PRAGMA synchronous=NORMAL')  # Улучшаем производительность
        self.conn.row_factory = sqlite3.Row  # Для удобного доступа по имени столбца
        self.create_tables()

    def safe_execute(self, query, params=()):
        """Безопасное выполнение запроса с обработкой блокировок"""
        cursor = self.conn.cursor()
        max_retries = 3
        for attempt in range(max_retries):
            try:
                cursor.execute(query, params)
                self.conn.commit()
                return cursor
            except sqlite3.OperationalError as e:
                if "locked" in str(e) and attempt < max_retries - 1:
                    import time
                    time.sleep(0.1 * (attempt + 1))  # Экспоненциальная задержка
                    continue
                else:
                    raise

    def get_user_clan_safe(self, user_id, guild_id):
        """Безопасное получение клана пользователя"""
        return self.safe_execute('''
            SELECT cm.*, c.name, c.owner_id, c.clan_type, c.bank
            FROM clan_members cm
            JOIN clans c ON cm.clan_id = c.clan_id
            WHERE cm.user_id = ? AND cm.guild_id = ?
        ''', (user_id, guild_id)).fetchone()
    
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

        # Таблица кланов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS clans (
                clan_id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER,
                name TEXT,
                owner_id INTEGER,
                description TEXT DEFAULT '',
                clan_type TEXT DEFAULT 'open', -- open, closed, application
                join_code TEXT DEFAULT NULL, -- для закрытых кланов
                prefix TEXT DEFAULT '', -- префикс роли
                role_id INTEGER DEFAULT NULL, -- ID роли клана
                bank INTEGER DEFAULT 0,
                created_at INTEGER,
                UNIQUE(guild_id, name)
            )
        ''')
        
        # Участники клана
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS clan_members (
                user_id INTEGER,
                guild_id INTEGER,
                clan_id INTEGER,
                role TEXT DEFAULT 'member', -- owner, coowner, member
                joined_at INTEGER,
                PRIMARY KEY (user_id, guild_id),
                FOREIGN KEY (clan_id) REFERENCES clans(clan_id) ON DELETE CASCADE
            )
        ''')
        
        # Заявки на вступление (для типа application)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS clan_applications (
                application_id INTEGER PRIMARY KEY AUTOINCREMENT,
                clan_id INTEGER,
                user_id INTEGER,
                guild_id INTEGER,
                message TEXT,
                status TEXT DEFAULT 'pending', -- pending, approved, rejected
                created_at INTEGER,
                FOREIGN KEY (clan_id) REFERENCES clans(clan_id) ON DELETE CASCADE
            )
        ''')
        
        # Настройки клана (должности, цвета и т.д.)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS clan_settings (
                clan_id INTEGER PRIMARY KEY,
                member_role_name TEXT DEFAULT 'Участник',
                coowner_role_name TEXT DEFAULT 'Совладелец',
                owner_role_name TEXT DEFAULT 'Владелец',
                color INTEGER DEFAULT NULL,
                FOREIGN KEY (clan_id) REFERENCES clans(clan_id) ON DELETE CASCADE
            )
        ''')

        # Система опыта кланов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS clan_xp (
                clan_id INTEGER PRIMARY KEY,
                xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 1,
                total_xp_earned INTEGER DEFAULT 0,
                last_xp_gain INTEGER DEFAULT NULL,
                FOREIGN KEY (clan_id) REFERENCES clans(clan_id) ON DELETE CASCADE
            )
        ''')

        # Детальная статистика участников клана
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS clan_member_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                guild_id INTEGER,
                clan_id INTEGER,
                total_deposited INTEGER DEFAULT 0,
                messages_count INTEGER DEFAULT 0,
                voice_minutes INTEGER DEFAULT 0,
                commands_used INTEGER DEFAULT 0,
                last_active INTEGER DEFAULT NULL,
                xp_contributed INTEGER DEFAULT 0,
                FOREIGN KEY (user_id, guild_id, clan_id) 
                REFERENCES clan_members(user_id, guild_id, clan_id) ON DELETE CASCADE,
                UNIQUE(user_id, guild_id, clan_id)
            )
        ''')

        # События для начисления опыта клану
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS clan_xp_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                clan_id INTEGER,
                user_id INTEGER,
                event_type TEXT, -- member_join, deposit, message, voice, command, etc.
                xp_amount INTEGER,
                details TEXT,
                created_at INTEGER,
                FOREIGN KEY (clan_id) REFERENCES clans(clan_id) ON DELETE CASCADE
            )
        ''')

        # Проверяем и добавляем отсутствующие колонки в существующие таблицы
        try:
            cursor.execute("PRAGMA table_info(clans)")
            existing_clan_columns = [column[1] for column in cursor.fetchall()]
            
            if 'created_at' not in existing_clan_columns:
                cursor.execute('ALTER TABLE clans ADD COLUMN created_at INTEGER')
                print('✅ Добавлена колонка created_at в таблицу clans')
                
            if 'bank' not in existing_clan_columns:
                cursor.execute('ALTER TABLE clans ADD COLUMN bank INTEGER DEFAULT 0')
                print('✅ Добавлена колонка bank в таблицу clans')
                
        except Exception as e:
            print(f'❌ Ошибка при проверке колонок clans: {e}')

        # Проверяем таблицу clan_members
        try:
            cursor.execute("PRAGMA table_info(clan_members)")
            existing_member_columns = [column[1] for column in cursor.fetchall()]
            
            if 'joined_at' not in existing_member_columns:
                cursor.execute('ALTER TABLE clan_members ADD COLUMN joined_at INTEGER')
                print('✅ Добавлена колонка joined_at в таблицу clan_members')
                
        except Exception as e:
            print(f'❌ Ошибка при проверке колонок clan_members: {e}')

        self.conn.commit()

        cursor.execute("PRAGMA table_info(users)")
        existing_columns = [column[1] for column in cursor.fetchall()]

        try:
            cursor.execute("PRAGMA table_info(clan_settings)")
            existing_clan_settings_columns = [column[1] for column in cursor.fetchall()]
            
            if 'level_up_reward' not in existing_clan_settings_columns:
                cursor.execute('ALTER TABLE clan_settings ADD COLUMN level_up_reward TEXT DEFAULT NULL')
                print('✅ Добавлена колонка level_up_reward в таблицу clan_settings')
                
            if 'color' not in existing_clan_settings_columns:
                cursor.execute('ALTER TABLE clan_settings ADD COLUMN color INTEGER DEFAULT NULL')
                print('✅ Добавлена колонка color в таблицу clan_settings')
                
        except Exception as e:
            print(f'❌ Ошибка при проверке колонок clan_settings: {e}')

        # Добавляем колонки для статистики ограблений
        new_columns = [
            ('robbery_success', 'INTEGER DEFAULT 0'),
            ('robbery_fail', 'INTEGER DEFAULT 0'),
            ('robbery_profit', 'INTEGER DEFAULT 0'),
            ('robbery_loss', 'INTEGER DEFAULT 0'),
            ('last_robbery', 'INTEGER DEFAULT NULL')
        ]

        for column_name, column_def in new_columns:
            if column_name not in existing_columns:
                try:
                    cursor.execute(f'ALTER TABLE users ADD COLUMN {column_name} {column_def}')
                    print(f'✅ Добавлена колонка {column_name} в таблицу users')
                except Exception as e:
                    print(f'❌ Ошибка при добавлении колонки {column_name}: {e}')

        # Кулдаун для ограблений
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS robbery_cooldowns (
                user_id INTEGER,
                guild_id INTEGER,
                last_robbery INTEGER,
                cooldown_until INTEGER,
                PRIMARY KEY (user_id, guild_id)
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

                # Таблица ачивок
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS achievements (
                achievement_id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER,
                name TEXT,
                description TEXT,
                icon TEXT DEFAULT '🏆',
                rarity TEXT DEFAULT 'common', -- common, rare, epic, legendary
                reward_currency INTEGER DEFAULT 0,
                reward_xp INTEGER DEFAULT 0,
                requirement_type TEXT, -- level, balance, messages, work_count, voice_time, etc.
                requirement_value INTEGER,
                is_secret BOOLEAN DEFAULT 0,
                created_at INTEGER
            )
        ''')
        
        # Таблица полученных ачивок пользователями
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_achievements (
                user_id INTEGER,
                guild_id INTEGER,
                achievement_id INTEGER,
                progress INTEGER DEFAULT 0,
                completed BOOLEAN DEFAULT 0,
                completed_at INTEGER DEFAULT NULL,
                PRIMARY KEY (user_id, guild_id, achievement_id)
            )
        ''')
        
        # Таблица баннеров (фоны профиля)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS banners (
                banner_id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER,
                name TEXT,
                image_url TEXT,
                rarity TEXT DEFAULT 'common',
                achievement_id INTEGER DEFAULT NULL,
                price INTEGER DEFAULT 0,
                is_default BOOLEAN DEFAULT 0,
                is_exclusive BOOLEAN DEFAULT 0,
                created_at INTEGER
            )
        ''')

        cursor.execute("PRAGMA table_info(banners)")
        existing_columns = [column[1] for column in cursor.fetchall()]

        # Список колонок, которые должны быть в таблице banners
        required_banner_columns = [
        ('is_exclusive', 'BOOLEAN DEFAULT 0')
        ]

        for column_name, column_def in required_banner_columns:
            if column_name not in existing_columns:
                try:
                    cursor.execute(f'ALTER TABLE banners ADD COLUMN {column_name} {column_def}')
                    print(f'✅ Добавлена колонка {column_name} в таблицу banners')
                except Exception as e:
                    print(f'❌ Ошибка при добавлении колонки {column_name} в banners: {e}')
        
        # Таблица баннеров пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_banners (
                user_id INTEGER,
                guild_id INTEGER,
                banner_id INTEGER,
                is_active BOOLEAN DEFAULT 0,
                obtained_at INTEGER,
                PRIMARY KEY (user_id, guild_id, banner_id)
            )
        ''')

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
                log_channel_id INTEGER DEFAULT NULL,
                voice_category_id INTEGER DEFAULT NULL,
                text_category_id INTEGER DEFAULT NULL,
                max_rooms_per_user INTEGER DEFAULT 1,
                room_auto_delete_minutes INTEGER DEFAULT 5,
                default_room_name TEXT DEFAULT 'Комната {username}',
                allow_voice_rooms BOOLEAN DEFAULT 1,
                allow_text_rooms BOOLEAN DEFAULT 1,
                rob_rich_bal INTEGER DEFAULT 25,
                rob_poor_bal INTEGER DEFAULT 7,
                rob_parts INTEGER DEFAULT 3,
                rob_threshold INTEGER DEFAULT 10000,
                rob_min_victim_balance INTEGER DEFAULT 100,
                rob_min_amount INTEGER DEFAULT 50,
                rob_max_amount INTEGER DEFAULT 5000,
                rob_cooldown INTEGER DEFAULT 3600,
                rob_base_chance REAL DEFAULT 0.5,
                rob_level_penalty REAL DEFAULT 0.05
            )
        ''')

        # Проверяем и добавляем отсутствующие колонки в существующую таблицу
        cursor.execute("PRAGMA table_info(server_settings)")
        existing_columns = [column[1] for column in cursor.fetchall()]
    
    # Список колонок, которые должны быть
        required_columns = [
            ('voice_category_id', 'INTEGER DEFAULT NULL'),
            ('text_category_id', 'INTEGER DEFAULT NULL'),
            ('max_rooms_per_user', 'INTEGER DEFAULT 1'),
            ('room_auto_delete_minutes', 'INTEGER DEFAULT 5'),
            ('default_room_name', 'TEXT DEFAULT "Комната {username}"'),
            ('allow_voice_rooms', 'BOOLEAN DEFAULT 1'),
            ('allow_text_rooms', 'BOOLEAN DEFAULT 1'),
            ('rob_rich_bal', 'INTEGER DEFAULT 25'),
            ('rob_poor_bal', 'INTEGER DEFAULT 7'),
            ('rob_parts', 'INTEGER DEFAULT 3'),
            ('rob_threshold', 'INTEGER DEFAULT 10000'),
            ('rob_min_victim_balance', 'INTEGER DEFAULT 100'),
            ('rob_min_amount', 'INTEGER DEFAULT 50'),
            ('rob_max_amount', 'INTEGER DEFAULT 5000'),
            ('rob_cooldown', 'INTEGER DEFAULT 3600'),
            ('rob_base_chance', 'REAL DEFAULT 0.5'),
            ('rob_level_penalty', 'REAL DEFAULT 0.05')
            ]
    
        for column_name, column_def in required_columns:
            if column_name not in existing_columns:
                try:
                    cursor.execute(f'ALTER TABLE server_settings ADD COLUMN {column_name} {column_def}')
                    print(f'✅ Добавлена колонка {column_name} в таблицу server_settings')
                except Exception as e:
                    print(f'❌ Ошибка при добавлении колонки {column_name}: {e}')

        self.conn.commit()
    
    def get_user(self, user_id, guild_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id = ? AND guild_id = ?', (user_id, guild_id))
        result = cursor.fetchone()
        if not result:
            try:
                cursor.execute('INSERT INTO users (user_id, guild_id) VALUES (?, ?)', (user_id, guild_id))
                self.conn.commit()
                return (user_id, guild_id, 0, 0, 1, 0)
            except sqlite3.IntegrityError:
                # Если пользователь уже создан в другом потоке, получаем его
                cursor.execute('SELECT * FROM users WHERE user_id = ? AND guild_id = ?', (user_id, guild_id))
                result = cursor.fetchone()
                if result:
                    return result
                return (user_id, guild_id, 0, 0, 1, 0)
        return result
    def get_roles_for_groups(self, guild_id, groups):
        """Получить ID ролей для указанных групп"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT role_id FROM role_assignments 
            WHERE guild_id = ? AND role_group IN ({})
        '''.format(','.join(['?'] * len(groups))), (guild_id, *groups))
    
        result = cursor.fetchall()
        return [row[0] for row in result] if result else []
    
    def update_balance(self, user_id, guild_id, amount):
        """Обновить баланс пользователя (использует транзакцию)"""
        cursor = self.conn.cursor()
        try:
            # Сначала убедимся, что пользователь существует
            self.get_user(user_id, guild_id)
            
            # Обновляем баланс
            cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ? AND guild_id = ?', 
                         (amount, user_id, guild_id))
            self.conn.commit()
        except Exception as e:
            print(f"❌ Ошибка в update_balance: {e}")
            self.conn.rollback()
    
    def update_xp(self, user_id, guild_id, amount):
        cursor = self.conn.cursor()
        cursor.execute('UPDATE users SET xp = xp + ? WHERE user_id = ? AND guild_id = ?', (amount, user_id, guild_id))
        self.conn.commit()
    
    # ОСТАВЬ ВСЕ ОСТАЛЬНЫЕ МЕТОДЫ БЕЗ ИЗМЕНЕНИЙ, они уже были в твоём файле
    # Просто убери все методы с "_with_retry" и оставь оригинальные
    
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
        cursor.execute('INSERT OR REPLACE INTO role_multipliers (role_id, economy_multiplier, xp_multiplier) VALUES (?, ?, ?)', 
        (role_id, eco_mult, xp_mult))
        self.conn.commit()
    
    def get_server_settings(self, guild_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM server_settings WHERE guild_id = ?', (guild_id,))
        result = cursor.fetchone()
        if not result:
            # Создаем запись с дефолтными значениями ВСЕХ полей
            cursor.execute('''
                INSERT INTO server_settings (guild_id, 
                    work_reward_min, work_reward_max, work_cooldown,
                    xp_per_message, xp_per_voice_minute,
                    slot_min_bet, slot_max_bet,
                    prefix, logs_enabled, log_channel_id,
                    voice_category_id, text_category_id,
                    max_rooms_per_user, room_auto_delete_minutes, default_room_name,
                    allow_voice_rooms, allow_text_rooms,
                    rob_rich_bal, rob_poor_bal, rob_parts, rob_threshold,
                    rob_min_victim_balance, rob_min_amount, rob_max_amount,
                    rob_cooldown, rob_base_chance, rob_level_penalty)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                guild_id,
                10, 50, 3600,  # work_min, work_max, work_cooldown
                5, 2,           # xp_per_message, xp_per_voice_minute
                1, 1000,        # slot_min_bet, slot_max_bet
                '!', 0, None,   # prefix, logs_enabled, log_channel_id
                None, None,     # voice_category_id, text_category_id
                1, 5, 'Комната {username}',  # max_rooms, room_delete, room_name
                1, 1,           # allow_voice, allow_text
                25, 7, 3, 10000,  # rob_rich_bal, rob_poor_bal, rob_parts, rob_threshold
                100, 50, 5000,  # rob_min_victim, rob_min, rob_max
                3600, 0.5, 0.05  # rob_cd, rob_chance, rob_penalty
            ))
            self.conn.commit()
            # Получаем созданную запись
            cursor.execute('SELECT * FROM server_settings WHERE guild_id = ?', (guild_id,))
            result = cursor.fetchone()
        return result
    
    def update_server_settings(self, guild_id, **kwargs):
        cursor = self.conn.cursor()
        settings = self.get_server_settings(guild_id)
        setting_names = ['work_reward_min', 'work_reward_max', 'work_cooldown', 'xp_per_message', 
                        'xp_per_voice_minute', 'slot_min_bet', 'slot_max_bet', 'prefix', 
                        'logs_enabled', 'log_channel_id', 'voice_category_id', 'text_category_id',
                        'max_rooms_per_user', 'room_auto_delete_minutes', 'default_room_name',
                        'allow_voice_rooms', 'allow_text_rooms']
        
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
    
    def get_clan_xp(self, clan_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM clan_xp WHERE clan_id = ?', (clan_id,))
        result = cursor.fetchone()
        if not result:
            cursor.execute('INSERT INTO clan_xp (clan_id) VALUES (?)', (clan_id,))
            self.conn.commit()
            return (clan_id, 0, 1, 0, None)
        return result
    
    def add_clan_xp(self, clan_id, xp_amount, user_id=None, event_type=None, details=None):
        cursor = self.conn.cursor()
        
        # Получаем текущие данные клана
        cursor.execute('SELECT xp, level FROM clan_xp WHERE clan_id = ?', (clan_id,))
        result = cursor.fetchone()
        
        if not result:
            cursor.execute('INSERT INTO clan_xp (clan_id, xp, total_xp_earned, last_xp_gain) VALUES (?, ?, ?, ?)',
                         (clan_id, xp_amount, xp_amount, int(datetime.now().timestamp())))
        else:
            current_xp, current_level = result
            new_xp = current_xp + xp_amount
            cursor.execute('UPDATE clan_xp SET xp = ?, total_xp_earned = total_xp_earned + ?, last_xp_gain = ? WHERE clan_id = ?',
                         (new_xp, xp_amount, int(datetime.now().timestamp()), clan_id))
        
        # Записываем событие если указаны параметры
        if user_id and event_type:
            cursor.execute('''
                INSERT INTO clan_xp_events (clan_id, user_id, event_type, xp_amount, details, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (clan_id, user_id, event_type, xp_amount, details, int(datetime.now().timestamp())))
        
        self.conn.commit()
        
        # Проверяем повышение уровня
        return self.check_clan_level_up(clan_id)
    
    def check_clan_level_up(self, clan_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT xp, level FROM clan_xp WHERE clan_id = ?', (clan_id,))
        result = cursor.fetchone()
        
        if not result:
            return None, None
        
        current_xp, current_level = result
        
        # Формула для уровней: level = floor(sqrt(xp / 100))
        new_level = int((current_xp / 100) ** 0.5)
        
        if new_level > current_level:
            cursor.execute('UPDATE clan_xp SET level = ? WHERE clan_id = ?', (new_level, clan_id))
            self.conn.commit()
            
            # Получаем награду за уровень (если есть в настройках)
            cursor.execute('PRAGMA table_info(clan_settings)')
            columns = [column[1] for column in cursor.fetchall()]
            
            reward_info = None
            if 'level_up_reward' in columns:
                cursor.execute('SELECT level_up_reward FROM clan_settings WHERE clan_id = ?', (clan_id,))
                reward_result = cursor.fetchone()
                reward_info = reward_result[0] if reward_result else None
            
            return new_level, reward_info
        
        return None, None
    
    def get_clan_level_info(self, clan_id):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT cx.*, c.name, c.bank 
            FROM clan_xp cx
            JOIN clans c ON cx.clan_id = c.clan_id
            WHERE cx.clan_id = ?
        ''', (clan_id,))
        return cursor.fetchone()
    
    def get_clan_leaderboard_xp(self, guild_id, limit=10):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT c.clan_id, c.name, cx.level, cx.xp, c.bank,
                   COUNT(cm.user_id) as member_count
            FROM clans c
            JOIN clan_xp cx ON c.clan_id = cx.clan_id
            LEFT JOIN clan_members cm ON c.clan_id = cm.clan_id
            WHERE c.guild_id = ?
            GROUP BY c.clan_id
            ORDER BY cx.level DESC, cx.xp DESC
            LIMIT ?
        ''', (guild_id, limit))
        return cursor.fetchall()
    
    # Методы для статистики участников клана
    def get_clan_member_stats(self, user_id, guild_id, clan_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM clan_member_stats WHERE user_id = ? AND guild_id = ? AND clan_id = ?',
                     (user_id, guild_id, clan_id))
        result = cursor.fetchone()
        if not result:
            cursor.execute('''
                INSERT INTO clan_member_stats (user_id, guild_id, clan_id, last_active)
                VALUES (?, ?, ?, ?)
            ''', (user_id, guild_id, clan_id, int(datetime.now().timestamp())))
            self.conn.commit()
            return self.get_clan_member_stats(user_id, guild_id, clan_id)
        return result
    
    def update_clan_member_stats(self, user_id, guild_id, clan_id, **kwargs):
        cursor = self.conn.cursor()
        
        # Убедимся, что запись существует
        self.get_clan_member_stats(user_id, guild_id, clan_id)
        
        updates = []
        values = []
        for key, value in kwargs.items():
            if key in ['total_deposited', 'messages_count', 'voice_minutes', 'commands_used', 'xp_contributed']:
                updates.append(f"{key} = {key} + ?")
                values.append(value)
            elif key == 'last_active':
                updates.append(f"{key} = ?")
                values.append(value)
        
        if updates:
            values.extend([user_id, guild_id, clan_id])
            query = f'UPDATE clan_member_stats SET {", ".join(updates)} WHERE user_id = ? AND guild_id = ? AND clan_id = ?'
            cursor.execute(query, values)
            self.conn.commit()
    
    def get_clan_detailed_stats(self, clan_id):
        cursor = self.conn.cursor()
        
        # Общая статистика клана
        cursor.execute('''
            SELECT 
                c.name as clan_name,
                c.bank as clan_bank,
                cx.level as clan_level,
                cx.xp as clan_xp,
                COUNT(DISTINCT cm.user_id) as total_members,
                SUM(cms.total_deposited) as total_deposits,
                SUM(cms.messages_count) as total_messages,
                SUM(cms.voice_minutes) as total_voice_minutes,
                SUM(cms.xp_contributed) as total_xp_contributed
            FROM clans c
            JOIN clan_xp cx ON c.clan_id = cx.clan_id
            LEFT JOIN clan_members cm ON c.clan_id = cm.clan_id
            LEFT JOIN clan_member_stats cms ON c.clan_id = cms.clan_id AND cm.user_id = cms.user_id
            WHERE c.clan_id = ?
            GROUP BY c.clan_id
        ''', (clan_id,))
        
        clan_stats = cursor.fetchone()
        
        # Статистика по участникам
        cursor.execute('''
            SELECT 
                cm.user_id,
                cm.role,
                cm.joined_at,
                cms.total_deposited,
                cms.messages_count,
                cms.voice_minutes,
                cms.commands_used,
                cms.xp_contributed,
                cms.last_active,
                (SELECT COUNT(*) FROM clan_xp_events cxe 
                 WHERE cxe.clan_id = cm.clan_id AND cxe.user_id = cm.user_id) as xp_events_count
            FROM clan_members cm
            LEFT JOIN clan_member_stats cms ON cm.user_id = cms.user_id 
                AND cm.guild_id = cms.guild_id 
                AND cm.clan_id = cms.clan_id
            WHERE cm.clan_id = ?
            ORDER BY 
                CASE cm.role
                    WHEN 'owner' THEN 1
                    WHEN 'coowner' THEN 2
                    ELSE 3
                END,
                cms.total_deposited DESC
        ''', (clan_id,))
        
        member_stats = cursor.fetchall()
        
        return clan_stats, member_stats
    
    def get_clan_xp_history(self, clan_id, limit=20):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT cxe.*, u.balance as user_balance
            FROM clan_xp_events cxe
            LEFT JOIN users u ON cxe.user_id = u.user_id
            WHERE cxe.clan_id = ?
            ORDER BY cxe.created_at DESC
            LIMIT ?
        ''', (clan_id, limit))
        return cursor.fetchall()
    
    # Методы для управления настройками клана
    def update_clan_settings(self, clan_id, **kwargs):
        cursor = self.conn.cursor()
        
        # Проверяем существование записи
        cursor.execute('SELECT clan_id FROM clan_settings WHERE clan_id = ?', (clan_id,))
        if not cursor.fetchone():
            cursor.execute('INSERT INTO clan_settings (clan_id) VALUES (?)', (clan_id,))
        
        updates = []
        values = []
        for key, value in kwargs.items():
            if key in ['member_role_name', 'coowner_role_name', 'owner_role_name', 'color', 'level_up_reward']:
                updates.append(f"{key} = ?")
                values.append(value)
        
        if updates:
            values.append(clan_id)
            query = f'UPDATE clan_settings SET {", ".join(updates)} WHERE clan_id = ?'
            cursor.execute(query, values)
            self.conn.commit()
    
    def get_clan_settings(self, clan_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM clan_settings WHERE clan_id = ?', (clan_id,))
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
    
    def process_automatic_clan_xp(self):
        """Автоматическое начисление XP за активность (вызывать раз в день)"""
        cursor = self.conn.cursor()
        
        # Начисляем XP за ежедневную активность
        cursor.execute('''
            SELECT DISTINCT clan_id 
            FROM clan_members 
            WHERE joined_at <= ? - 86400  # Участники, которые в клане хотя бы день
        ''', (int(datetime.now().timestamp()),))
        
        clans = cursor.fetchall()
        
        for (clan_id,) in clans:
            # Получаем активных участников за последний день
            cursor.execute('''
                SELECT COUNT(DISTINCT cms.user_id)
                FROM clan_member_stats cms
                WHERE cms.clan_id = ? AND cms.last_active >= ? - 86400
            ''', (clan_id, int(datetime.now().timestamp())))
            
            active_members = cursor.fetchone()[0] or 0
            
            if active_members >= 3:  # Минимум 3 активных участника
                xp_amount = active_members * 10  # 10 XP за каждого активного участника
                
                # Начисляем XP
                cursor.execute('''
                    UPDATE clan_xp 
                    SET xp = xp + ?, total_xp_earned = total_xp_earned + ?
                    WHERE clan_id = ?
                ''', (xp_amount, xp_amount, clan_id))
                
                # Записываем событие
                cursor.execute('''
                    INSERT INTO clan_xp_events (clan_id, event_type, xp_amount, details, created_at)
                    VALUES (?, ?, ?, ?, ?)
                ''', (clan_id, 'daily', xp_amount, f"Ежедневная активность ({active_members} участников)", 
                      int(datetime.now().timestamp())))
        
        self.conn.commit()

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