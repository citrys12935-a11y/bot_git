import discord
from discord.ext import commands
from utils.database import Database

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
            'log_channel': 'log_channel_id'
        }
        self.valid_role_groups = [
            'player', 'moderator', 'admin', 'high_admin', 'owner'
        ]
    
    @commands.command(name='settings')
    @commands.has_permissions(administrator=True)
    async def settings(self, ctx, *args):
        if not args:
            await self.show_settings(ctx)
            return
        
        setting_type = args[0].lower()
        
        if setting_type == 'help':
            await self.show_settings_help(ctx)
            return
        
        if setting_type in self.valid_settings:
            await self.handle_economy_settings(ctx, setting_type, args[1] if len(args) > 1 else None)
        elif setting_type == 'role_group':
            if len(args) < 3:
                await ctx.send("❌ Использование: `!settings role_group <группа> <@роль>`")
                return
            await self.handle_role_group(ctx, args[1], ' '.join(args[2:]))
        elif setting_type == 'role_multiplier':
            if len(args) < 4:
                await ctx.send("❌ Использование: `!settings role_multiplier <economy/xp> <@роль> <множитель>`")
                return
            await self.handle_role_multiplier(ctx, args[1], ' '.join(args[2:-1]), args[-1])
        elif setting_type == 'level_reward':
            await self.handle_level_reward(ctx, args[1:])
        elif setting_type == 'ticket':
            await self.handle_ticket_settings(ctx, args[1:])
        else:
            await ctx.send("❌ Неверный тип настройки! Используйте `!settings help` для списка команд")
    
    async def show_settings_help(self, ctx):
        db = Database()
        settings = db.get_server_settings(ctx.guild.id)
        prefix = settings[8] if settings else '!'
        
        embed = discord.Embed(title="📖 Помощь по настройкам", color=0x3498db)
        
        embed.add_field(
            name="💼 Настройки экономики", 
            value=f"""
`{prefix}settings work_min <число>` - Минимальная награда за work
`{prefix}settings work_max <число>` - Максимальная награда за work  
`{prefix}settings work_cooldown <секунды>` - Кулдаун work
`{prefix}settings slot_min <число>` - Минимальная ставка в slots
`{prefix}settings slot_max <число>` - Максимальная ставка в slots
""", 
            inline=False
        )
        
        embed.add_field(
            name="🏆 Настройки уровней", 
            value=f"""
`{prefix}settings xp_message <число>` - Опыт за сообщение
`{prefix}settings xp_voice <число>` - Опыт за голосовую активность в минуту
`{prefix}settings level_reward <уровень> <тип> [роль] [валюта]` - Награда за уровень
""", 
            inline=False
        )
        
        embed.add_field(
            name="⚙️ Общие настройки", 
            value=f"""
`{prefix}settings prefix <префикс>` - Префикс команд (1-3 символа)
`{prefix}settings logs on/off` - Включить/выключить систему логов
`{prefix}settings log_channel #канал` - Установить канал для логов
""", 
            inline=False
        )
        
        embed.add_field(
            name="👥 Настройки ролей", 
            value=f"""
`{prefix}settings role_group <группа> @роль` - Назначить роль группе
`{prefix}settings role_multiplier <economy/xp> @роль <множитель>` - Установить множитель для роли
""", 
            inline=False
        )
        
        embed.add_field(
            name="🎫 Настройки тикетов", 
            value=f"""
`{prefix}settings ticket group <тип> @роль` - Назначить роль для типа тикетов
""", 
            inline=False
        )
        
        embed.add_field(
            name="📝 Примеры использования", 
            value=f"""
`{prefix}settings work_min 20` - установить мин. награду 20
`{prefix}settings work_max 100` - установить макс. награду 100
`{prefix}settings prefix $` - изменить префикс на $
`{prefix}settings logs on` - включить логи
`{prefix}settings log_channel #логи` - установить канал для логов
`{prefix}settings role_group admin @Админ` - назначить роль группе
`{prefix}settings role_multiplier economy @Вип 2.0` - множитель x2 для экономики
`{prefix}settings level_reward 5 currency 1000` - 1000 монет за 5 уровень
`{prefix}settings level_reward 10 role @VIP` - роль VIP за 10 уровень
`{prefix}settings level_reward 15 both @VIP 2000` - роль VIP + 2000 монет за 15 уровень
`{prefix}settings ticket group помощь @Helper` - роль для тикетов помощи
`{prefix}settings` - показать текущие настройки
""", 
            inline=False
        )
        
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
        
        await ctx.send(embed=embed)
    
    async def show_settings(self, ctx):
        settings = self.db.get_server_settings(ctx.guild.id)
        
        embed = discord.Embed(title="⚙️ Текущие настройки", color=0x00ff00)
        
        embed.add_field(name="⚙️ Общие", value=f"""
Префикс команд: `{settings[8]}`
Логи: {'✅ Включены' if settings[9] else '❌ Выключены'}
Канал логов: {'Не установлен' if not settings[10] else f'<#{settings[10]}>'}
""", inline=False)
        
        embed.add_field(name="💼 Экономика", value=f"""
Work: {settings[1]}-{settings[2]} монет
Кулдаун: {settings[3]}сек
Слоты: {settings[6]}-{settings[7]} монет
""", inline=False)
        
        embed.add_field(name="🏆 Уровни", value=f"""
За сообщение: {settings[4]} XP
За голосовую активность: {settings[5]} XP/мин
""", inline=False)
        
        level_rewards = self.db.get_all_level_rewards(ctx.guild.id)
        if level_rewards:
            rewards_text = []
            for reward in level_rewards[:5]:
                guild_id, level, reward_type, role_id, currency_amount = reward
                reward_info = f"Ур. {level}: "
                
                if reward_type in ['currency', 'both'] and currency_amount > 0:
                    reward_info += f"{currency_amount} монет"
                
                if reward_type in ['role', 'both'] and role_id:
                    role = ctx.guild.get_role(role_id)
                    if role:
                        if reward_type == 'both':
                            reward_info += " + "
                        reward_info += f"роль {role.name}"
                
                rewards_text.append(reward_info)
            
            embed.add_field(
                name="🎁 Награды за уровни", 
                value="\n".join(rewards_text) + ("\n..." if len(level_rewards) > 5 else ""), 
                inline=False
            )
        
        ticket_groups = self.db.get_all_ticket_groups(ctx.guild.id)
        if ticket_groups:
            tickets_text = []
            for group in ticket_groups:
                guild_id, group_type, role_id = group
                role = ctx.guild.get_role(role_id)
                if role:
                    tickets_text.append(f"{group_type}: {role.mention}")
            
            embed.add_field(
                name="🎫 Настройки тикетов", 
                value="\n".join(tickets_text), 
                inline=False
            )
        
        await ctx.send(embed=embed)
    
    async def handle_level_reward(self, ctx, args):
        """Обработка настройки наград за уровни"""
        if len(args) < 2:
            await ctx.send("❌ Использование: `!settings level_reward <уровень> <тип> [роль] [валюта]`")
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
            
            # Парсим роль из оставшихся аргументов
            role_input = ' '.join(args[2:]) if reward_type == 'role' else args[2]
            
            # Ищем роль
            role = await self.parse_role(ctx, role_input)
            if not role:
                await ctx.send("❌ Роль не найдена! Убедитесь, что вы правильно упомянули роль.")
                return
            
            # Проверяем права бота
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
        
        # Устанавливаем награду
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
        """Обработка настроек тикетов"""
        if len(args) < 3 or args[0] != 'group':
            await ctx.send("❌ Использование: `!settings ticket group <тип> @роль`")
            return
        
        group_type = args[1].lower()
        if group_type not in ['помощь', 'жалоба']:
            await ctx.send("❌ Неверный тип тикета! Используйте: помощь, жалоба")
            return
        
        # Парсим роль из оставшихся аргументов
        role_input = ' '.join(args[2:])
        role = await self.parse_role(ctx, role_input)
        
        if not role:
            await ctx.send("❌ Роль не найдена! Убедитесь, что вы правильно упомянули роль.")
            return
        
        # Устанавливаем группу тикетов
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
        """Парсит роль из входной строки"""
        # Пытаемся найти роль по упоминанию
        if role_input.startswith('<@&') and role_input.endswith('>'):
            role_id = int(role_input[3:-1])
            return ctx.guild.get_role(role_id)
        
        # Пытаемся найти роль по ID
        if role_input.isdigit():
            role_id = int(role_input)
            return ctx.guild.get_role(role_id)
        
        # Пытаемся найти роль по имени (точное совпадение)
        role = discord.utils.get(ctx.guild.roles, name=role_input)
        if role:
            return role
        
        # Пытаемся найти роль по имени (частичное совпадение)
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
        
        if not value.isdigit():
            await ctx.send(f"❌ Укажите числовое значение для {setting}!")
            return
        
        int_value = int(value)
        db_setting = self.valid_settings[setting]
        
        self.db.update_server_settings(ctx.guild.id, **{db_setting: int_value})
        await ctx.send(f"✅ Настройка '{setting}' изменена на {int_value}")
    
    async def handle_role_group(self, ctx, role_group, role_input):
        if not role_group or not role_input:
            await ctx.send("❌ Использование: `!settings role_group <группа> <@роль>`")
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
    
    async def handle_role_multiplier(self, ctx, multiplier_type, role_input, multiplier_str):
        if not multiplier_type or not role_input or not multiplier_str:
            await ctx.send("❌ Использование: `!settings role_multiplier <economy/xp> <@роль> <множитель>`")
            return
        
        role = await self.parse_role(ctx, role_input)
        if not role:
            await ctx.send("❌ Роль не найдена! Убедитесь, что вы правильно упомянули роль.")
            return
        
        try:
            multiplier = float(multiplier_str)
        except ValueError:
            await ctx.send("❌ Множитель должен быть числом!")
            return
        
        if multiplier_type == 'economy' or multiplier_type == 'ec':
            self.db.set_role_multiplier(role.id, multiplier, 1.0)
            await ctx.send(f"✅ Для роли {role.mention} установлен множитель экономики: x{multiplier}")
        elif multiplier_type == 'xp':
            self.db.set_role_multiplier(role.id, 1.0, multiplier)
            await ctx.send(f"✅ Для роли {role.mention} установлен множитель опыта: x{multiplier}")
        else:
            await ctx.send("❌ Неверный тип множителя! Используйте 'economy' или 'xp'")

    @commands.command(name='setmultiplier')
    @commands.has_permissions(administrator=True)
    async def set_multiplier(self, ctx, role: discord.Role, multiplier_type: str, value: float):
        if multiplier_type.lower() not in ['economy', 'xp']:
            await ctx.send("❌ Неверный тип множителя! Используйте 'economy' или 'xp'")
            return
        
        if value < 1.0:
            await ctx.send("❌ Множитель не может быть меньше 1.0!")
            return
        
        if multiplier_type.lower() == 'economy':
            self.db.set_role_multiplier(role.id, value, 1.0)
            await ctx.send(f"✅ Для роли {role.mention} установлен множитель экономики: **x{value}**")
        else:
            self.db.set_role_multiplier(role.id, 1.0, value)
            await ctx.send(f"✅ Для роли {role.mention} установлен множитель опыта: **x{value}**")

async def setup(bot):
    await bot.add_cog(Settings(bot))