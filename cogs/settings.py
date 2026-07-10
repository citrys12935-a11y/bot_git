import discord
from discord import app_commands
from discord.ext import commands
from utils.database import Database
from utils.checks import has_permission

class Settings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()
        self.valid_settings = {
            'work_min': 'work_reward_min',
            'work_max': 'work_reward_max', 
            'work_cooldown': 'work_cooldown',
            'xp_message': 'xp_per_message',
            'xp_voice': 'xp_per_voice_minute',
            'slot_min': 'slot_min_bet',
            'slot_max': 'slot_max_bet',
            'prefix': 'prefix',
            'logs': 'logs_enabled',
            'log_channel': 'log_channel_id',
            'voice_category': 'voice_category_id',
            'text_category': 'text_category_id',
            'max_rooms': 'max_rooms_per_user',
            'room_delete': 'room_auto_delete_minutes',
            'room_name': 'default_room_name',
            'allow_voice': 'allow_voice_rooms',
            'allow_text': 'allow_text_rooms',
            'rob_rich_bal': 'rob_rich_bal',
            'rob_poor_bal': 'rob_poor_bal', 
            'rob_parts': 'rob_parts',
            'rob_threshold': 'rob_threshold',
            'rob_min_victim': 'rob_min_victim_balance',
            'rob_min': 'rob_min_amount',
            'rob_max': 'rob_max_amount',
            'rob_cd': 'rob_cooldown',
            'rob_chance': 'rob_base_chance',
            'rob_penalty': 'rob_level_penalty'
        }
        self.valid_role_groups = [
            'admin', 'high_admin', 'owner', 'moderator', 'room_manager'
        ]
    
    async def show_settings(self, ctx):
        """Показать текущие настройки сервера"""
        try:
            settings = self.db.get_server_settings(ctx.guild.id)
            
            # Преобразуем результат в список для безопасного доступа по индексу
            settings_list = list(settings)
            
            # Проверяем длину, чтобы избежать IndexError
            if len(settings_list) < 28:
                # Если не хватает полей, добавляем дефолтные значения
                default_values = [
                    ctx.guild.id,  # guild_id на позиции 0
                    10, 50, 3600, 5, 2, 1, 1000, '!', 0, None,
                    None, None, 1, 5, 'Комната {username}', 1, 1,
                    25, 7, 3, 10000, 100, 50, 5000, 3600, 0.5, 0.05
                ]
                # Заменяем недостающие значения дефолтными
                for i in range(len(settings_list), 28):
                    settings_list.append(default_values[i])
            
            embed = discord.Embed(
                title="⚙️ Текущие настройки сервера",
                color=0x3498db
            )
            
            # Экономика
            embed.add_field(
                name="💼 Экономика",
                value=f"""
Минимальная награда за work: `{settings_list[1]}`
Максимальная награда за work: `{settings_list[2]}`
Кулдаун work: `{settings_list[3]}` сек.
Опыт за сообщение: `{settings_list[4]}`
Опыт за голос (в минуту): `{settings_list[5]}`
Минимальная ставка в слотах: `{settings_list[6]}`
Максимальная ставка в слотах: `{settings_list[7]}`
Префикс команд: `{settings_list[8]}`
""",
                inline=False
            )
            
            # Логи
            logs_status = "✅ Включены" if settings_list[9] else "❌ Выключены"
            log_channel = ctx.guild.get_channel(settings_list[10])
            log_channel_mention = log_channel.mention if log_channel else "Не установлен"
            embed.add_field(
                name="📝 Логи",
                value=f"""
Статус: {logs_status}
Канал логов: {log_channel_mention}
""",
                inline=False
            )
            
            # Приватные комнаты
            voice_category = ctx.guild.get_channel(settings_list[11])
            text_category = ctx.guild.get_channel(settings_list[12])
            embed.add_field(
                name="🔒 Приватные комнаты",
                value=f"""
Категория для голосовых: {voice_category.mention if voice_category else 'Не установлена'}
Категория для текстовых: {text_category.mention if text_category else 'Не установлена'}
Макс. комнат на пользователя: `{settings_list[13]}`
Автоудаление через: `{settings_list[14]}` мин.
Шаблон названия: `{settings_list[15]}`
Голосовые комнаты: {'✅ Включены' if settings_list[16] else '❌ Выключены'}
Текстовые комнаты: {'✅ Включены' if settings_list[17] else '❌ Выключены'}
""",
                inline=False
            )
            
            # Настройки ограблений
            embed.add_field(
                name="🚔 Настройки ограблений",
                value=f"""
Делитель для богатых: `{settings_list[18]}`
Делитель для бедных: `{settings_list[19]}`
Частей деления: `{settings_list[20]}`
Порог богатства: `{settings_list[21]}`
Мин. баланс жертвы: `{settings_list[22]}`
Мин. сумма ограбления: `{settings_list[23]}`
Макс. сумма ограбления: `{settings_list[24]}`
Кулдаун: `{settings_list[25]}` сек.
Базовый шанс успеха: `{settings_list[26]}`
Штраф за уровень: `{settings_list[27]}`
""",
                inline=False
            )
            
            # Команда для изменения
            prefix = settings_list[8] if settings_list else '!'
            embed.set_footer(text=f"Используйте {prefix}settings help для изменения настроек")
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            print(f"❌ Ошибка в show_settings: {e}")
            import traceback
            traceback.print_exc()
            await ctx.send("❌ Произошла ошибка при получении настроек сервера.")
    
    @commands.hybrid_command(name='settings', description='Показать или изменить настройки сервера')
    @app_commands.describe(
        setting_type="Тип настройки",
        arg1="Первый аргумент (зависит от типа настройки)",
        arg2="Второй аргумент (зависит от типа настройки)",
        arg3="Третий аргумент (зависит от типа настройки)"
    )
    @has_permission('admin', 'high_admin', 'owner')
    async def settings_command(self, ctx, setting_type: str = None, arg1: str = None, arg2: str = None, arg3: str = None):
        if not setting_type:
            await self.show_settings(ctx)
            return
        
        setting_type = setting_type.lower()
        
        if setting_type == 'help':
            await self.show_settings_help(ctx)
            return
        
        # Формируем список аргументов
        all_args = [setting_type]
        if arg1 is not None:
            all_args.append(arg1)
        if arg2 is not None:
            all_args.append(arg2)
        if arg3 is not None:
            all_args.append(arg3)
        
        # Обрабатываем в зависимости от типа настройки
        if setting_type in self.valid_settings:
            await self.handle_economy_settings(ctx, setting_type, all_args[1] if len(all_args) > 1 else None)
        elif setting_type == 'role_group':
            if len(all_args) < 3:
                await ctx.send("❌ Использование: `/settings role_group <группа> <@роль>`")
                return
            await self.handle_role_group(ctx, all_args[1], ' '.join(all_args[2:]))
        elif setting_type == 'role_multiplier':
            if len(all_args) < 4:
                await ctx.send("❌ Использование: `/settings role_multiplier <@роль> <eco_множитель> <xp_множитель>`")
                return
            await self.handle_role_multiplier(ctx, all_args[1], all_args[2], all_args[3])
        elif setting_type == 'level_reward':
            await self.handle_level_reward(ctx, all_args[1:])
        elif setting_type == 'ticket':
            await self.handle_ticket_settings(ctx, all_args[1:])
        else:
            await ctx.send("❌ Неверный тип настройки! Используйте `/settings help` для списка команд")
    
    @settings_command.autocomplete('setting_type')
    async def settings_autocomplete(self, interaction: discord.Interaction, current: str):
        settings_list = [
            'help', 'work_min', 'work_max', 'work_cooldown', 'slot_min', 'slot_max',
            'xp_message', 'xp_voice', 'prefix', 'logs', 'log_channel', 'role_group',
            'role_multiplier', 'level_reward', 'ticket',
            'voice_category', 'text_category', 'max_rooms',
            'room_delete', 'room_name', 'allow_voice', 'allow_text',
            'rob_rich_bal', 'rob_poor_bal', 'rob_parts', 'rob_threshold',
            'rob_min', 'rob_max', 'rob_cd', 'rob_chance', 'rob_penalty', 'rob_min_victim'
        ]
        return [
            app_commands.Choice(name=setting, value=setting)
            for setting in settings_list if current.lower() in setting.lower()
        ][:25]
    
    async def show_settings_help(self, ctx):
        db = Database()
        settings = db.get_server_settings(ctx.guild.id)
        prefix = settings[8] if settings else '!'
        
        # Определяем, как вызвана команда
        if ctx.interaction:
            cmd_prefix = '/settings'
        else:
            cmd_prefix = f'{prefix}settings'
        
        embed = discord.Embed(
            title="📖 Помощь по настройкам (Административные команды)",
            color=0x3498db
        )
        
        # Административные команды экономики
        embed.add_field(
            name="💼 Админские команды экономики", 
            value=f"""
`{prefix}addec @user <сумма>` - Выдать монеты
`{prefix}removeec @user <сумма>` - Забрать монеты
`{prefix}setbalance @user <сумма>` - Установить баланс
""", 
            inline=False
        )
        
        # Административные команды уровней
        embed.add_field(
            name="🏆 Админские команды уровней", 
            value=f"""
`{prefix}setxp @user <опыт>` - Установить опыт
`{prefix}setlevel @user <уровень>` - Установить уровень
`{prefix}levelreward set <уровень> <тип> [роль] [валюта]` - Установить награду
`{prefix}levelreward remove <уровень>` - Удалить награду
`{prefix}levelreward list` - Список наград
""", 
            inline=False
        )

        # Административные команды кланов
        embed.add_field(
            name="🏰 Админские команды кланов", 
            value=f"""
`{prefix}clanadmin addxp <клан/ID> <кол-во> [причина]` - Выдать опыт клана
`{prefix}clanadmin removexp <клан/ID> <кол-во> [причина]` - Забрать опыт клана
`{prefix}clanadmin resetstats <клан/ID> [тип сброса] [@user/ID]` - Сбросить статистику клану/участнику клана
`{prefix}clanadmin setlevel <клан/ID> <кол-во> [причина]` - Установить урвоень клана
`{prefix}clanadmin setxp <клан/ID> <кол-во> [причина]` - Установить опыт клана
""", 
            inline=False
        )
        
        # Настройки экономики
        embed.add_field(
            name="💰 Настройки экономики", 
            value=f"""
`{cmd_prefix} work_min <число>` - Минимальная награда за work
`{cmd_prefix} work_max <число>` - Максимальная награда за work  
`{cmd_prefix} work_cooldown <секунды>` - Кулдаун work
`{cmd_prefix} slot_min <число>` - Минимальная ставка в slots
`{cmd_prefix} slot_max <число>` - Максимальная ставка в slots
`{cmd_prefix} rob_rich_bal <число>` - Делитель для богатых
`{cmd_prefix} rob_poor_bal <число>` - Делитель для бедных
`{cmd_prefix} rob_parts <число>` - Частей деления
`{cmd_prefix} rob_threshold <число>` - Порог богатства
`{cmd_prefix} rob_min <число>` - Минимальная сумма ограбления
`{cmd_prefix} rob_max <число>` - Максимальная сумма ограбления
`{cmd_prefix} rob_cd <секунды>` - Кулдаун ограбления
`{cmd_prefix} rob_chance <0.0-1.0>` - Базовый шанс успеха
`{cmd_prefix} rob_penalty <0.0-1.0>` - Штраф за разницу уровней
`{cmd_prefix} rob_min_victim <число>` - Мин. баланс жертвы
""", 
            inline=False
        )
        
        # Настройки уровней
        embed.add_field(
            name="📈 Настройки уровней", 
            value=f"""
`{cmd_prefix} xp_message <число>` - Опыт за сообщение
`{cmd_prefix} xp_voice <число>` - Опыт за голосовую активность в минуту
`{cmd_prefix} level_reward <уровень> <тип> [роль] [валюта]` - Награда за уровень
""", 
            inline=False
        )
        
        # Настройки ролей
        embed.add_field(
            name="👥 Настройки ролей", 
            value=f"""
`{cmd_prefix} role_group <группа> @роль` - Назначить роль группе
`{cmd_prefix} role_multiplier @роль <eco_множитель> <xp_множитель>` - Установить множители для роли
""", 
            inline=False
        )
        
        # Настройки магазина
        embed.add_field(
            name="🛍️ Админские команды магазина", 
            value=f"""
`{prefix}additem <название> <цена> <тип> [лимит] <описание>` - Добавить предмет
`{prefix}addroleitem "Название" цена @роль [время] [лимит] описание` - Добавить роль
`{prefix}deleteitem <ID_предмета>` - Удалить предмет
`{prefix}clearinventory @user` - Очистить инвентарь
""", 
            inline=False
        )
        
        # Настройки достижений
        embed.add_field(
            name="🏆 Админские команды достижений", 
            value=f"""
`{prefix}achievementadmin create` - Создать достижение
`{prefix}achievementadmin give @user <ID_достижения>` - Выдать достижение
`{prefix}achievementadmin createbanner` - Создать баннер
`{prefix}achievementadmin givebanner @user <ID_баннера>` - Выдать баннер
""", 
            inline=False
        )
        
        # Настройки тикетов
        embed.add_field(
            name="🎫 Настройки тикетов", 
            value=f"""
`{cmd_prefix} ticket group <тип> @роль` - Назначить роль для типа тикетов
`{prefix}ticket list` - Список активных тикетов
""", 
            inline=False
        )

        # Настройки приватных комнат
        embed.add_field(
            name="🔒 Настройки приватных комнат", 
            value=f"""
`{cmd_prefix} voice_category #категория` - Категория для голосовых комнат
`{cmd_prefix} text_category #категория` - Категория для текстовых комнат  
`{cmd_prefix} max_rooms <число>` - Максимальное комнат на пользователя
`{cmd_prefix} room_delete <минуты>` - Автоудаление пустых комнат (0=выключено)
`{cmd_prefix} room_name <шаблон>` - Шаблон названия
`{cmd_prefix} allow_voice on/off` - Разрешить создание голосовых комнат
`{cmd_prefix} allow_text on/off` - Разрешить создание текстовых комнат
`{prefix}forceroomdelete <ID_канала>` - Принудительно удалить комнату
`{prefix}privateroom` - Настроить систему приватных комнат
`{prefix}roomsettings` - Показать настройки приватных комнат
""", 
            inline=False
        )
        
        # Общие настройки
        embed.add_field(
            name="⚙️ Общие настройки", 
            value=f"""
`{cmd_prefix} prefix <префикс>` - Префикс команд (1-3 символа)
`{cmd_prefix} logs on/off` - Включить/выключить систему логов
`{cmd_prefix} log_channel #канал` - Установить канал для логов
""", 
            inline=False
        )
        
        # Модерационные команды
        embed.add_field(
            name="⚖️ Модерационные команды", 
            value=f"""
`{prefix}warn @user [причина]` - Выдать предупреждение
`{prefix}warnings @user` - Посмотреть предупреждения
`{prefix}clearwarns @user` - Очистить предупреждения
`{prefix}mute @user <время> [причина]` - Заглушить пользователя
`{prefix}unmute @user [причина]` - Снять мут
`{prefix}kick @user [причина]` - Кикнуть пользователя
`{prefix}ban @user [причина]` - Забанить пользователя
`{prefix}unban @user` - Разбанить пользователя
`{prefix}clear <количество>` - Очистить сообщения
""", 
            inline=False
        )
        
        # Команды розыгрышей
        embed.add_field(
            name="🎉 Команды розыгрышей", 
            value=f"""
`{prefix}giveaway <время> <победители> <приз>` - Запустить розыгрыш
`{prefix}glist` - Список активных розыгрышей
`{prefix}greroll <id_сообщения>` - Перевыбрать победителей
`{prefix}gend <id_сообщения>` - Завершить розыгрыш досрочно
""", 
            inline=False
        )
        
        # Справочная информация
        embed.add_field(
            name="🎯 Группы ролей", 
            value=", ".join(self.valid_role_groups),
            inline=False
        )
        
        embed.add_field(
            name="🎁 Типы наград за уровни", 
            value="currency, role, both",
            inline=False
        )
        
        embed.add_field(
            name="🎫 Типы тикетов", 
            value="помощь, жалоба",
            inline=False
        )
        
        embed.set_footer(text="Бот для Светогорска • [] - необязательный параметр, <> - обязательный параметр")
        
        await ctx.send(embed=embed)
    
    async def handle_level_reward(self, ctx, args):
        if len(args) < 2:
            await ctx.send("❌ Использование: `/settings level_reward <уровень> <тип> [роль] [валюта]`")
            return
        
        try:
            level = int(args[0])
        except ValueError:
            await ctx.send("❌ Уровень должен быть числом!")
            return
        
        if level < 1:
            await ctx.send("❌ Уровень не может быть меньше 1!")
            return
        
        reward_type = args[1].lower()
        if reward_type not in ['currency', 'role', 'both']:
            await ctx.send("❌ Неверный тип награды! Используйте: currency, role или both")
            return
        
        role = None
        currency_amount = 0
        
        if reward_type in ['role', 'both']:
            if len(args) < 3:
                await ctx.send("❌ Для этого типа награды необходимо указать роль!")
                return
            
            role_input = ' '.join(args[2:]) if reward_type == 'role' else args[2]
            role = await self.parse_role(ctx, role_input)
            if not role:
                await ctx.send("❌ Роль не найдена! Убедитесь, что вы правильно упомянули роль.")
                return
            
            if role.position >= ctx.guild.me.top_role.position:
                await ctx.send("❌ Я не могу управлять этой ролью! Роль находится выше моей в иерархии.")
                return
        
        if reward_type in ['currency', 'both']:
            if len(args) < (4 if reward_type == 'both' else 3):
                await ctx.send("❌ Для этого типа награды необходимо указать количество валюты!")
                return
            
            try:
                currency_str = args[3] if reward_type == 'both' else args[2]
                currency_amount = int(currency_str)
            except (ValueError, IndexError):
                await ctx.send("❌ Количество валюты должно быть числом!")
                return
            
            if currency_amount <= 0:
                await ctx.send("❌ Количество валюты должно быть положительным!")
                return
        
        self.db.set_level_reward(
            ctx.guild.id, 
            level, 
            reward_type, 
            role.id if role else None, 
            currency_amount
        )
        
        embed = discord.Embed(
            title="✅ Награда за уровень установлена!",
            color=0x00ff00
        )
        
        embed.add_field(name="Уровень", value=level, inline=True)
        embed.add_field(name="Тип награды", value=reward_type, inline=True)
        
        if reward_type in ['currency', 'both']:
            embed.add_field(name="Валюта", value=f"{currency_amount} монет", inline=True)
        
        if reward_type in ['role', 'both']:
            embed.add_field(name="Роль", value=role.mention, inline=True)
        
        await ctx.send(embed=embed)
    
    async def handle_ticket_settings(self, ctx, args):
        if len(args) < 3 or args[0] != 'group':
            await ctx.send("❌ Использование: `/settings ticket group <тип> @роль`")
            return
        
        group_type = args[1].lower()
        if group_type not in ['помощь', 'жалоба']:
            await ctx.send("❌ Неверный тип тикета! Используйте: помощь, жалоба")
            return
        
        role_input = ' '.join(args[2:])
        role = await self.parse_role(ctx, role_input)
        
        if not role:
            await ctx.send("❌ Роль не найдена! Убедитесь, что вы правильно упомянули роль.")
            return
        
        self.db.set_ticket_group(ctx.guild.id, group_type, role.id)
        
        embed = discord.Embed(
            title="✅ Настройки тикетов обновлены!",
            color=0x00ff00
        )
        
        embed.add_field(name="Тип тикета", value=group_type, inline=True)
        embed.add_field(name="Роль", value=role.mention, inline=True)
        embed.add_field(name="Описание", value=f"Теперь при создании тикета типа '{group_type}' будет упоминаться роль {role.mention}", inline=False)
        
        await ctx.send(embed=embed)
    
    async def parse_role(self, ctx, role_input):
        if role_input.startswith('<@&') and role_input.endswith('>'):
            role_id = int(role_input[3:-1])
            return ctx.guild.get_role(role_id)
        
        if role_input.isdigit():
            role_id = int(role_input)
            return ctx.guild.get_role(role_id)
        
        role = discord.utils.get(ctx.guild.roles, name=role_input)
        if role:
            return role
        
        for r in ctx.guild.roles:
            if role_input.lower() in r.name.lower():
                return r
        
        return None
    
    async def handle_economy_settings(self, ctx, setting, value):
        if not value:
            await ctx.send(f"❌ Укажите значение для {setting}!")
            return
        
        if setting == 'logs':
            if value.lower() in ['on', 'вкл', '1', 'true', 'yes']:
                db_setting = self.valid_settings[setting]
                self.db.update_server_settings(ctx.guild.id, **{db_setting: 1})
                await ctx.send("✅ Логи включены")
                return
            elif value.lower() in ['off', 'выкл', '0', 'false', 'no']:
                db_setting = self.valid_settings[setting]
                self.db.update_server_settings(ctx.guild.id, **{db_setting: 0})
                await ctx.send("✅ Логи выключены")
                return
            else:
                await ctx.send("❌ Используйте: `on` или `off`")
                return
        
        if setting == 'log_channel':
            channel = None
            if value.startswith('<#') and value.endswith('>'):
                channel_id = int(value[2:-1])
                channel = ctx.guild.get_channel(channel_id)
            elif value.isdigit():
                channel_id = int(value)
                channel = ctx.guild.get_channel(channel_id)
            else:
                channel = discord.utils.get(ctx.guild.channels, name=value)
            
            if not channel:
                await ctx.send("❌ Канал не найден!")
                return
            
            db_setting = self.valid_settings[setting]
            self.db.update_server_settings(ctx.guild.id, **{db_setting: channel.id})
            await ctx.send(f"✅ Канал для логов установлен: {channel.mention}")
            return
        
        if setting == 'prefix':
            if len(value) > 3:
                await ctx.send("❌ Префикс не может быть длиннее 3 символов!")
                return
            if ' ' in value:
                await ctx.send("❌ Префикс не может содержать пробелы!")
                return
            
            db_setting = self.valid_settings[setting]
            self.db.update_server_settings(ctx.guild.id, **{db_setting: value})
            await ctx.send(f"✅ Префикс команд изменен на `{value}`\nТеперь используйте команды так: `{value}help`")
            return
        
        # Обработка настроек приватных комнат
        if setting in ['voice_category', 'text_category']:
            channel = None
            if value.startswith('<#') and value.endswith('>'):
                channel_id = int(value[2:-1])
                channel = ctx.guild.get_channel(channel_id)
            elif value.isdigit():
                channel_id = int(value)
                channel = ctx.guild.get_channel(channel_id)
            else:
                for cat in ctx.guild.categories:
                    if value.lower() in cat.name.lower():
                        channel = cat
                        break
            
            if not channel or not isinstance(channel, discord.CategoryChannel):
                await ctx.send("❌ Категория не найдена! Укажите существующую категорию.")
                return
            
            db_setting = self.valid_settings[setting]
            self.db.update_server_settings(ctx.guild.id, **{db_setting: channel.id})
            await ctx.send(f"✅ Категория для {'голосовых' if setting == 'voice_category' else 'текстовых'} комнат установлена: {channel.mention}")
            return
        
        if setting in ['max_rooms', 'room_delete']:
            if not value.isdigit():
                await ctx.send(f"❌ Укажите числовое значение для {setting}!")
                return
            
            int_value = int(value)
            if int_value < 0:
                await ctx.send(f"❌ Значение {setting} не может быть отрицательным!")
                return
            
            db_setting = self.valid_settings[setting]
            self.db.update_server_settings(ctx.guild.id, **{db_setting: int_value})
            await ctx.send(f"✅ Настройка '{setting}' изменена на {int_value}")
            return
        
        if setting == 'room_name':
            if len(value) > 50:
                await ctx.send("❌ Шаблон названия не может быть длиннее 50 символов!")
                return
            
            db_setting = self.valid_settings[setting]
            self.db.update_server_settings(ctx.guild.id, **{db_setting: value})
            await ctx.send(f"✅ Шаблон названия комнат изменен на: `{value}`")
            return
        
        if setting in ['allow_voice', 'allow_text']:
            if value.lower() in ['on', 'вкл', '1', 'true', 'yes', 'да']:
                db_setting = self.valid_settings[setting]
                self.db.update_server_settings(ctx.guild.id, **{db_setting: 1})
                await ctx.send(f"✅ {'Голосовые' if setting == 'allow_voice' else 'Текстовые'} комнаты включены")
                return
            elif value.lower() in ['off', 'выкл', '0', 'false', 'no', 'нет']:
                db_setting = self.valid_settings[setting]
                self.db.update_server_settings(ctx.guild.id, **{db_setting: 0})
                await ctx.send(f"✅ {'Голосовые' if setting == 'allow_voice' else 'Текстовые'} комнаты выключены")
                return
            else:
                await ctx.send("❌ Используйте: `on` или `off`")
                return
        
        # Проверка для числовых значений
        if not value.replace('.', '', 1).isdigit():
            await ctx.send(f"❌ Укажите числовое значение для {setting}!")
            return
        
        # Для дробных значений
        if '.' in value:
            try:
                float_value = float(value)
                if setting in ['rob_chance', 'rob_penalty']:
                    if not 0 <= float_value <= 1:
                        await ctx.send(f"❌ Значение {setting} должно быть между 0.0 и 1.0!")
                        return
                
                db_setting = self.valid_settings[setting]
                self.db.update_server_settings(ctx.guild.id, **{db_setting: float_value})
                await ctx.send(f"✅ Настройка '{setting}' изменена на {float_value}")
            except ValueError:
                await ctx.send(f"❌ Неверное значение для {setting}!")
        else:
            # Для целых значений
            int_value = int(value)
            db_setting = self.valid_settings[setting]
            self.db.update_server_settings(ctx.guild.id, **{db_setting: int_value})
            await ctx.send(f"✅ Настройка '{setting}' изменена на {int_value}")
    
    async def handle_role_group(self, ctx, role_group, role_input):
        if not role_group or not role_input:
            await ctx.send("❌ Использование: `/settings role_group <группа> <@роль>`")
            return
        
        if role_group not in self.valid_role_groups:
            await ctx.send(f"❌ Неверная группа! Доступные: {', '.join(self.valid_role_groups)}")
            return
        
        role = await self.parse_role(ctx, role_input)
        if not role:
            await ctx.send("❌ Роль не найдена! Убедитесь, что вы правильно упомянули роль.")
            return
        
        self.db.set_role_assignment(ctx.guild.id, role_group, role.id)
        await ctx.send(f"✅ Роль {role.mention} назначена группе '{role_group}'")
    
    async def handle_role_multiplier(self, ctx, role_input, eco_mult_str, xp_mult_str):
        if not role_input or not eco_mult_str or not xp_mult_str:
            await ctx.send("❌ Использование: `/settings role_multiplier @роль <eco_множитель> <xp_множитель>`")
            return
        
        role = await self.parse_role(ctx, role_input)
        if not role:
            await ctx.send("❌ Роль не найдена! Убедитесь, что вы правильно упомянули роль.")
            return
        
        try:
            eco_mult = float(eco_mult_str)
            xp_mult = float(xp_mult_str)
        except ValueError:
            await ctx.send("❌ Множители должны быть числами!")
            return
        
        if eco_mult < 1.0 or xp_mult < 1.0:
            await ctx.send("❌ Множители не могут быть меньше 1.0!")
            return
        
        self.db.set_role_multiplier(role.id, eco_mult, xp_mult)
        
        embed = discord.Embed(
            title="✅ Множители роли установлены!",
            color=0x00ff00
        )
        embed.add_field(name="Роль", value=role.mention, inline=True)
        embed.add_field(name="Множитель экономики", value=f"x{eco_mult}", inline=True)
        embed.add_field(name="Множитель опыта", value=f"x{xp_mult}", inline=True)
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name='roomsettings', description='Показать текущие настройки приватных комнат')
    @has_permission('admin', 'high_admin', 'owner')
    async def room_settings(self, ctx):
        settings = self.db.get_server_settings(ctx.guild.id)
        settings_list = list(settings)
        
        if len(settings_list) < 28:
            default_values = [
                ctx.guild.id,
                10, 50, 3600, 5, 2, 1, 1000, '!', 0, None,
                None, None, 1, 5, 'Комната {username}', 1, 1,
                25, 7, 3, 10000, 100, 50, 5000, 3600, 0.5, 0.05
            ]
            for i in range(len(settings_list), 28):
                settings_list.append(default_values[i])
        
        embed = discord.Embed(
            title="🔒 Настройки приватных комнат",
            color=0x7289da
        )
        
        voice_cat = ctx.guild.get_channel(settings_list[11]) if settings_list[11] else None
        voice_status = "✅ Включено" if settings_list[16] else "❌ Выключено"
        voice_info = f"""
{voice_status}
Категория: {voice_cat.mention if voice_cat else "❌ Не установлена"}
"""
        embed.add_field(name="🎤 Голосовые комнаты", value=voice_info, inline=False)
        
        text_cat = ctx.guild.get_channel(settings_list[12]) if settings_list[12] else None
        text_status = "✅ Включено" if settings_list[17] else "❌ Выключено"
        text_info = f"""
{text_status}
Категория: {text_cat.mention if text_cat else "❌ Не установлена"}
"""
        embed.add_field(name="💬 Текстовые комнаты", value=text_info, inline=False)
        
        embed.add_field(name="📊 Лимиты", value=f"""
Макс. комнат на пользователя: {settings_list[13]}
Автоудаление пустых комнат: {f"{settings_list[14]} мин." if settings_list[14] > 0 else "❌ Выключено"}
""", inline=False)
        
        embed.add_field(name="🏷️ Шаблон названия", value=f"`{settings_list[15]}`", inline=False)
        
        example_name = settings_list[15].format(username=ctx.author.name, user=ctx.author.name, member=ctx.author.name)
        embed.add_field(name="📝 Пример названия", value=f"`{example_name}`", inline=False)
        
        cursor = self.db.conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM private_rooms WHERE guild_id = ?', (ctx.guild.id,))
        room_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(DISTINCT owner_id) FROM private_rooms WHERE guild_id = ?', (ctx.guild.id,))
        owner_count = cursor.fetchone()[0]
        
        embed.add_field(name="📈 Статистика", value=f"""
Всего комнат: {room_count}
Пользователей с комнатами: {owner_count}
Среднее на пользователя: {round(room_count/owner_count, 1) if owner_count > 0 else 0}
""", inline=False)
        
        embed.set_footer(text="Используйте /settings для изменения настроек")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='setmultiplier', description='Установить множители для роли')
    @app_commands.describe(
        role="Роль для установки множителей",
        economy_mult="Множитель для экономики (например: 2.0)",
        xp_mult="Множитель для опыта (например: 1.5)"
    )
    @has_permission('admin', 'high_admin', 'owner')
    async def set_multiplier(self, ctx, role: discord.Role, economy_mult: float, xp_mult: float):
        if economy_mult < 1.0 or xp_mult < 1.0:
            await ctx.send("❌ Множители не могут быть меньше 1.0!")
            return
        
        if role.position >= ctx.guild.me.top_role.position:
            await ctx.send("❌ Я не могу управлять этой ролью! Роль находится выше моей в иерархии.")
            return
        
        self.db.set_role_multiplier(role.id, economy_mult, xp_mult)
        
        embed = discord.Embed(
            title="✅ Множители установлены!",
            color=0x00ff00
        )
        embed.add_field(name="Роль", value=role.mention, inline=True)
        embed.add_field(name="Множитель экономики", value=f"**x{economy_mult}**", inline=True)
        embed.add_field(name="Множитель опыта", value=f"**x{xp_mult}**", inline=True)
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Settings(bot))