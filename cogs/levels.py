import discord
from discord import app_commands
from discord.ext import commands, tasks
from utils.database import Database
from utils.checks import has_permission
from datetime import datetime
import asyncio

class Levels(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()
        self.voice_users = {}  # { (guild_id, user_id): datetime_joined }
        self.check_voice_xp.start()

    def cog_unload(self):
        self.check_voice_xp.cancel()
    
    @tasks.loop(minutes=1)
    async def check_voice_xp(self):
        """Проверка голосовой активности каждую минуту"""
        try:
            current_time = datetime.now()
            to_remove = []
            
            for (guild_id, user_id), join_time in list(self.voice_users.items()):
                guild = self.bot.get_guild(guild_id)
                if not guild:
                    to_remove.append((guild_id, user_id))
                    continue
                
                member = guild.get_member(user_id)
                if not member:
                    to_remove.append((guild_id, user_id))
                    continue
                
                # Проверяем, что пользователь все еще в голосовом канале
                if not member.voice or not member.voice.channel:
                    to_remove.append((guild_id, user_id))
                    continue
                
                # Проверяем, не находится ли пользователь в AFK
                if member.voice.afk:
                    continue
                
                # Проверяем, не отключен ли микрофон и не в режиме "не беспокоить"
                if member.voice.self_deaf or member.voice.self_mute:
                    continue
                
                # Вычисляем, сколько минут прошло
                minutes = (current_time - join_time).total_seconds() / 60
                if minutes >= 1:
                    # Начисляем опыт за каждую минуту
                    settings = self.db.get_server_settings(guild_id)
                    xp_per_minute = settings[5]  # xp_per_voice_minute
                    
                    # Применяем множители ролей
                    multiplier = 1.0
                    for role in member.roles:
                        role_mult = self.db.get_role_multiplier(role.id)
                        if role_mult and role_mult[1] > multiplier:
                            multiplier = role_mult[1]
                    
                    # Округляем до целого количества минут
                    full_minutes = int(minutes)
                    xp_gain = int(xp_per_minute * full_minutes * multiplier)
                    
                    if xp_gain > 0:
                        self.db.update_xp(user_id, guild_id, xp_gain)
                        
                        # Обновляем время захода, чтобы не начислять повторно
                        self.voice_users[(guild_id, user_id)] = current_time
                        
                        # Проверяем уровень
                        user_data = self.db.get_user(user_id, guild_id)
                        new_level = self.calculate_level(user_data[3])
                        
                        if new_level > user_data[4]:
                            self.db.set_level(user_id, guild_id, new_level)
                            
                            # Отправляем сообщение в системный канал или в канал где находится пользователь
                            try:
                                channel = member.voice.channel
                                embed = discord.Embed(
                                    title="🎉 Новый уровень!",
                                    description=f"{member.mention} достиг **{new_level}** уровня в голосовом чате!",
                                    color=0x00ff00
                                )
                                
                                # Вызываем событие повышения уровня
                                await self.trigger_level_up(user_id, guild_id, new_level, channel)
                            except:
                                pass
            
            for key in to_remove:
                if key in self.voice_users:
                    del self.voice_users[key]
                    
        except Exception as e:
            print(f"❌ Ошибка в check_voice_xp: {e}")
    
    @check_voice_xp.before_loop
    async def before_check_voice_xp(self):
        await self.bot.wait_until_ready()
    
    async def trigger_level_up(self, user_id, guild_id, new_level, channel=None):
        """Триггерит событие повышения уровня"""
        # Вызываем событие для кога Achievements
        achievements_cog = self.bot.get_cog('Achievements')
        if achievements_cog and hasattr(achievements_cog, 'on_level_up'):
            await achievements_cog.on_level_up(user_id, guild_id, new_level)
        
        # Даем награды за уровень
        if channel:
            member = channel.guild.get_member(user_id)
            if member:
                reward_embed = await self.give_level_reward(member, new_level, channel)
                if reward_embed:
                    await channel.send(embed=reward_embed)
    
    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Отслеживание входа/выхода из голосового канала"""
        if member.bot:
            return
        
        guild_id = member.guild.id
        user_id = member.id
        key = (guild_id, user_id)
        
        # Пользователь зашел в голосовой канал
        if before.channel is None and after.channel is not None:
            # Проверяем, не AFK ли канал
            if after.channel.name.lower() != "afk":
                self.voice_users[key] = datetime.now()
                print(f"📢 {member.name} зашел в голосовой канал")
        
        # Пользователь вышел из голосового канала
        elif before.channel is not None and after.channel is None:
            if key in self.voice_users:
                # Начисляем оставшийся опыт перед выходом
                join_time = self.voice_users[key]
                minutes = (datetime.now() - join_time).total_seconds() / 60
                
                if minutes >= 1:
                    settings = self.db.get_server_settings(guild_id)
                    xp_per_minute = settings[5]
                    
                    multiplier = 1.0
                    for role in member.roles:
                        role_mult = self.db.get_role_multiplier(role.id)
                        if role_mult and role_mult[1] > multiplier:
                            multiplier = role_mult[1]
                    
                    xp_gain = int(xp_per_minute * minutes * multiplier)
                    if xp_gain > 0:
                        self.db.update_xp(user_id, guild_id, xp_gain)
                        print(f"📢 {member.name} вышел, получено {xp_gain} опыта")
                
                del self.voice_users[key]
        
        # Пользователь перешел в другой канал
        elif before.channel is not None and after.channel is not None and before.channel != after.channel:
            # Если перешел в AFK
            if after.channel.name.lower() == "afk":
                if key in self.voice_users:
                    del self.voice_users[key]
            else:
                # Обновляем время захода
                self.voice_users[key] = datetime.now()
    
    def calculate_level(self, xp):
        return int((xp / 50) ** 0.5) + 1
    
    def xp_for_level(self, level):
        return (level - 1) ** 2 * 50
    
    async def give_level_reward(self, member, level, channel):
        """Выдача награды за достижение уровня"""
        reward = self.db.get_level_reward(member.guild.id, level)
        
        if not reward:
            return None
        
        guild_id, level, reward_type, role_id, currency_amount = reward
        
        embed = discord.Embed(
            title="🎁 Получена награда за уровень!",
            description=f"За достижение **{level}** уровня вы получаете:",
            color=0x00ff00
        )
        
        rewards_given = []
        
        # Выдача валюты
        if reward_type in ['currency', 'both'] and currency_amount > 0:
            self.db.update_balance(member.id, member.guild.id, currency_amount)
            rewards_given.append(f"💰 **{currency_amount} монет**")
        
        # Выдача роли
        if reward_type in ['role', 'both'] and role_id:
            role = member.guild.get_role(role_id)
            if role:
                try:
                    await member.add_roles(role)
                    rewards_given.append(f"🎭 Роль {role.mention}")
                except discord.Forbidden:
                    rewards_given.append(f"🎭 Роль {role.name} (не удалось выдать)")
                except Exception as e:
                    rewards_given.append(f"🎭 Роль {role.name} (ошибка: {str(e)})")
        
        if rewards_given:
            embed.add_field(
                name="Полученные награды:",
                value="\n".join(rewards_given),
                inline=False
            )
            
            # Логирование
            try:
                log_embed = discord.Embed(
                    title="🏆 Выдана награда за уровень",
                    color=0x00ff00,
                    timestamp=discord.utils.utcnow()
                )
                log_embed.add_field(name="Пользователь", value=member.mention, inline=True)
                log_embed.add_field(name="Уровень", value=level, inline=True)
                log_embed.add_field(name="Награды", value=", ".join(rewards_given), inline=True)
                
                settings = self.db.get_server_settings(member.guild.id)
                if settings[9] and settings[10]:
                    log_channel = member.guild.get_channel(settings[10])
                    if log_channel:
                        await log_channel.send(embed=log_embed)
            except:
                pass
            
            return embed
        
        return None
    
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return
        
        user_id = message.author.id
        guild_id = message.guild.id
        
        settings = self.db.get_server_settings(guild_id)
        xp_gain = settings[4]
        
        # Применяем множители ролей
        multiplier = 1.0
        for role in message.author.roles:
            role_mult = self.db.get_role_multiplier(role.id)
            if role_mult and role_mult[1] > multiplier:
                multiplier = role_mult[1]
        
        xp_gain = int(xp_gain * multiplier)
        self.db.update_xp(user_id, guild_id, xp_gain)
        
        # Проверяем уровень
        user_data = self.db.get_user(user_id, guild_id)
        new_level = self.calculate_level(user_data[3])
        
        if new_level > user_data[4]:
            self.db.set_level(user_id, guild_id, new_level)
            
            # Основное сообщение о новом уровне
            embed = discord.Embed(
                title="🎉 Новый уровень!",
                description=f"{message.author.mention} достиг **{new_level}** уровня!",
                color=0x00ff00
            )
            
            # Вызываем событие повышения уровня
            await self.trigger_level_up(user_id, guild_id, new_level, message.channel)
            
            # Проверяем и выдаем награду за уровень
            reward_embed = await self.give_level_reward(message.author, new_level, message.channel)
            
            if reward_embed:
                await message.channel.send(embed=embed)
                await message.channel.send(embed=reward_embed)
            else:
                await message.channel.send(embed=embed)

    @commands.hybrid_command(name='voice_stats', description='Показать статистику по голосовому опыту')
    async def voice_stats(self, ctx):
        """Показывает текущую голосовую активность"""
        user_id = ctx.author.id
        guild_id = ctx.guild.id
        key = (guild_id, user_id)
        
        if key in self.voice_users:
            join_time = self.voice_users[key]
            minutes = (datetime.now() - join_time).total_seconds() / 60
            settings = self.db.get_server_settings(guild_id)
            xp_per_minute = settings[5]
            
            # Применяем множители
            multiplier = 1.0
            for role in ctx.author.roles:
                role_mult = self.db.get_role_multiplier(role.id)
                if role_mult and role_mult[1] > multiplier:
                    multiplier = role_mult[1]
            
            xp_earned = int(xp_per_minute * minutes * multiplier)
            
            embed = discord.Embed(
                title="📢 Голосовая активность",
                description=f"{ctx.author.mention} в голосовом канале:",
                color=0x3498db
            )
            
            embed.add_field(name="⏱️ Времени в голосовом", value=f"{int(minutes)} минут", inline=True)
            embed.add_field(name="⚡ XP/минуту", value=f"{xp_per_minute} * {multiplier:.1f} = {int(xp_per_minute * multiplier)}", inline=True)
            embed.add_field(name="💰 Заработано XP", value=f"{xp_earned}", inline=True)
            
            await ctx.send(embed=embed)
        else:
            await ctx.send("Вы не в голосовом канале или система голосового опыта отключена.")
    
    @commands.hybrid_command(name='level', description='Посмотреть уровень пользователя')
    @app_commands.describe(member='Пользователь, чей уровень нужно посмотреть (необязательно)')
    async def level(self, ctx, member: discord.Member = None):
        """Просмотр уровня"""
        member = member or ctx.author
        user_data = self.db.get_user(member.id, ctx.guild.id)
        
        current_xp = user_data[3]
        current_level = user_data[4]
        xp_needed = self.xp_for_level(current_level + 1)
        xp_current_level = self.xp_for_level(current_level)
        progress = current_xp - xp_current_level
        total_needed = xp_needed - xp_current_level
        
        progress_percent = int((progress / total_needed) * 100) if total_needed > 0 else 100
        
        progress_bar_length = 10
        filled = int(progress_percent / 100 * progress_bar_length)
        progress_bar = "█" * filled + "░" * (progress_bar_length - filled)
        
        embed = discord.Embed(
            title=f"🏆 Уровень {member.display_name}",
            color=0x0099ff
        )
        
        embed.add_field(name="📊 Уровень", value=current_level, inline=True)
        embed.add_field(name="⭐ Опыт", value=f"{current_xp}/{xp_needed}", inline=True)
        embed.add_field(name="📈 Прогресс", value=f"{progress_percent}%", inline=True)
        
        embed.add_field(
            name="🎯 Прогресс до следующего уровня", 
            value=f"`{progress_bar}` {progress}/{total_needed} XP", 
            inline=False
        )
        
        next_reward = self.db.get_level_reward(ctx.guild.id, current_level + 1)
        if next_reward:
            reward_info = self.format_reward_info(next_reward, ctx.guild)
            embed.add_field(
                name="🎁 Следующая награда",
                value=f"На **{current_level + 1}** уровне: {reward_info}",
                inline=False
            )
        
        embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
        await ctx.send(embed=embed)
    
    def format_reward_info(self, reward, guild):
        guild_id, level, reward_type, role_id, currency_amount = reward
        
        rewards = []
        
        if reward_type in ['currency', 'both'] and currency_amount > 0:
            rewards.append(f"💰 {currency_amount} монет")
        
        if reward_type in ['role', 'both'] and role_id:
            role = guild.get_role(role_id)
            if role:
                rewards.append(f"🎭 {role.mention}")
        
        return " + ".join(rewards) if rewards else "Нет награды"
    
    @commands.hybrid_command(name='leaderboardlv', aliases=['lblv'], description='Топ сервера по уровням')
    async def leaderboard_lv(self, ctx):
        leaders = self.db.get_leaderboard_lv(ctx.guild.id)
        
        embed = discord.Embed(
            title="🏆 Топ по уровням", 
            color=0xffd700
        )
        
        if not leaders:
            embed.description = "Пока нет данных о пользователях."
        else:
            for i, (user_id, level, xp) in enumerate(leaders[:10], 1):
                user = self.bot.get_user(user_id)
                username = user.name if user else f"Неизвестный ({user_id})"
                embed.add_field(
                    name=f"{i}. {username}", 
                    value=f"Уровень {level} | Опыт {xp}", 
                    inline=False
                )
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name='rank', description='Детальная информация о профиле')
    @app_commands.describe(member='Пользователь, чей профиль нужно посмотреть (необязательно)')
    async def rank(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        user_data = self.db.get_user(member.id, ctx.guild.id)
        
        current_xp = user_data[3]
        current_level = user_data[4]
        balance = user_data[2]
        xp_needed = self.xp_for_level(current_level + 1)
        xp_current_level = self.xp_for_level(current_level)
        progress = current_xp - xp_current_level
        total_needed = xp_needed - xp_current_level
        progress_percent = int((progress / total_needed) * 100) if total_needed > 0 else 100
        
        progress_bar_length = 15
        filled = int(progress_percent / 100 * progress_bar_length)
        progress_bar = "█" * filled + "░" * (progress_bar_length - filled)
        
        embed = discord.Embed(
            title=f"📊 Профиль {member.display_name}",
            color=member.color if member.color else 0x0099ff
        )
        
        embed.add_field(name="🏆 Уровень", value=current_level, inline=True)
        embed.add_field(name="⭐ Опыт", value=current_xp, inline=True)
        embed.add_field(name="💰 Баланс", value=f"{balance} монет", inline=True)
        
        embed.add_field(
            name="🎯 Прогресс", 
            value=f"`{progress_bar}` {progress_percent}%\n{progress}/{total_needed} XP до уровня {current_level + 1}", 
            inline=False
        )
        
        rewards = self.db.get_all_level_rewards(ctx.guild.id)
        user_rewards = [r for r in rewards if r[1] <= current_level]
        
        if user_rewards:
            reward_text = []
            for reward in user_rewards[-5:]:
                reward_info = self.format_reward_info(reward, ctx.guild)
                reward_text.append(f"**Ур. {reward[1]}**: {reward_info}")
            
            embed.add_field(
                name="🎁 Полученные награды",
                value="\n".join(reward_text),
                inline=False
            )
        
        embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
        embed.set_footer(text=f"ID: {member.id}")
        await ctx.send(embed=embed)
    
    @commands.hybrid_group(name='levelreward', aliases=['lreward'], description='Управление наградами за уровни')
    async def level_reward(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)
    
    @level_reward.command(name='set', description='Установить награду за уровень')
    @app_commands.describe(
        level='Уровень для награды',
        reward_type='Тип награды (currency, role, both)',
        role='Роль для награды (если требуется)',
        currency_amount='Количество монет (если требуется)'
    )
    @has_permission('admin', 'high_admin', 'owner')
    async def set_level_reward(self, ctx, level: int, reward_type: str, role: discord.Role = None, currency_amount: int = 0):
        if level < 1:
            await ctx.send("❌ Уровень не может быть меньше 1!")
            return
        
        reward_type = reward_type.lower()
        if reward_type not in ['currency', 'role', 'both']:
            await ctx.send("❌ Неверный тип награды! Используйте: currency, role или both")
            return
        
        if reward_type in ['role', 'both'] and not role:
            await ctx.send("❌ Для этого типа награды необходимо указать роль!")
            return
        
        if reward_type in ['currency', 'both'] and currency_amount <= 0:
            await ctx.send("❌ Для этого типа награды необходимо указать количество валюты!")
            return
        
        if role and role.position >= ctx.guild.me.top_role.position:
            await ctx.send("❌ Я не могу управлять этой ролью! Роль находится выше моей в иерархии.")
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
        embed.add_field(name="Тип награда", value=reward_type, inline=True)
        
        if reward_type in ['currency', 'both']:
            embed.add_field(name="Валюта", value=f"{currency_amount} монет", inline=True)
        
        if reward_type in ['role', 'both']:
            embed.add_field(name="Роль", value=role.mention, inline=True)
        
        await ctx.send(embed=embed)
    
    @level_reward.command(name='remove', description='Удалить награду за уровень')
    @app_commands.describe(level='Уровень для удаления награды')
    @has_permission('admin', 'high_admin', 'owner')
    async def remove_level_reward(self, ctx, level: int):
        reward = self.db.get_level_reward(ctx.guild.id, level)
        
        if not reward:
            await ctx.send(f"❌ Награда за {level} уровень не найдена!")
            return
        
        self.db.delete_level_reward(ctx.guild.id, level)
        
        embed = discord.Embed(
            title="✅ Награда удалена",
            description=f"Награда за {level} уровень удалена",
            color=0x00ff00
        )
        await ctx.send(embed=embed)
    
    @level_reward.command(name='list', description='Показать все награды за уровни')
    async def list_level_rewards(self, ctx):
        rewards = self.db.get_all_level_rewards(ctx.guild.id)
        
        if not rewards:
            embed = discord.Embed(
                title="🏆 Награды за уровни",
                description="Награды за уровни не установлены",
                color=0x3498db
            )
            await ctx.send(embed=embed)
            return
        
        embed = discord.Embed(
            title="🏆 Награды за уровни",
            color=0x3498db
        )
        
        for reward in rewards:
            guild_id, level, reward_type, role_id, currency_amount = reward
            
            reward_info = f"**Тип:** {reward_type}\n"
            
            if reward_type in ['currency', 'both'] and currency_amount > 0:
                reward_info += f"**Валюта:** {currency_amount} монет\n"
            
            if reward_type in ['role', 'both'] and role_id:
                role = ctx.guild.get_role(role_id)
                if role:
                    reward_info += f"**Роль:** {role.mention}\n"
            
            embed.add_field(
                name=f"Уровень {level}",
                value=reward_info,
                inline=True
            )
        
        await ctx.send(embed=embed)
    
    @level_reward.command(name='info', description='Информация о награде за уровень')
    @app_commands.describe(level='Уровень для просмотра награды')
    async def level_reward_info(self, ctx, level: int):
        reward = self.db.get_level_reward(ctx.guild.id, level)
        
        if not reward:
            await ctx.send(f"❌ Награда за {level} уровень не найдена!")
            return
        
        guild_id, level, reward_type, role_id, currency_amount = reward
        
        embed = discord.Embed(
            title=f"🏆 Награда за {level} уровень",
            color=0x3498db
        )
        
        embed.add_field(name="Тип награды", value=reward_type, inline=True)
        
        if reward_type in ['currency', 'both'] and currency_amount > 0:
            embed.add_field(name="Валюта", value=f"{currency_amount} монет", inline=True)
        
        if reward_type in ['role', 'both'] and role_id:
            role = ctx.guild.get_role(role_id)
            if role:
                embed.add_field(name="Роль", value=role.mention, inline=True)
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name='setxp', description='Установить опыт пользователю')
    @app_commands.describe(
        member='Пользователь, которому установить опыт',
        amount='Количество опыта'
    )
    @has_permission('admin', 'high_admin', 'owner')
    async def set_xp(self, ctx, member: discord.Member, amount: int):
        if amount < 0:
            await ctx.send("❌ Опыт не может быть отрицательным!")
            return
            
        self.db.set_xp(member.id, ctx.guild.id, amount)
        new_level = self.calculate_level(amount)
        self.db.set_level(member.id, ctx.guild.id, new_level)
        
        # Триггерим событие повышения уровня если нужно
        old_level = self.db.get_user(member.id, ctx.guild.id)[4]
        if new_level > old_level:
            await self.trigger_level_up(member.id, ctx.guild.id, new_level, ctx.channel)
        
        embed = discord.Embed(
            title="✅ Опыт установлен",
            description=f"Опыт {member.mention} установлен на {amount}",
            color=0x00ff00
        )
        embed.add_field(name="Новый уровень", value=new_level, inline=True)
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name='setlevel', description='Установить уровень пользователю')
    @app_commands.describe(
        member='Пользователь, которому установить уровень',
        level='Уровень'
    )
    @has_permission('admin', 'high_admin', 'owner')
    async def set_level_cmd(self, ctx, member: discord.Member, level: int):
        if level < 1:
            await ctx.send("❌ Уровень не может быть меньше 1!")
            return
            
        xp_needed = self.xp_for_level(level)
        old_level = self.db.get_user(member.id, ctx.guild.id)[4]
        self.db.set_xp(member.id, ctx.guild.id, xp_needed)
        self.db.set_level(member.id, ctx.guild.id, level)
        
        # Триггерим событие повышения уровня если нужно
        if level > old_level:
            await self.trigger_level_up(member.id, ctx.guild.id, level, ctx.channel)
        
        embed = discord.Embed(
            title="✅ Уровень установлен",
            description=f"Уровень {member.mention} установлен на {level}",
            color=0x00ff00
        )
        embed.add_field(name="Необходимый опыт", value=xp_needed, inline=True)
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Levels(bot))