import discord
from discord.ext import commands
from utils.database import Database

class Levels(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()
    
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
            
            # Проверяем и выдает награду за уровень
            reward_embed = await self.give_level_reward(message.author, new_level, message.channel)
            
            if reward_embed:
                await message.channel.send(embed=embed)
                await message.channel.send(embed=reward_embed)
            else:
                await message.channel.send(embed=embed)
    
    @commands.command(name='level')
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
    
    @commands.command(name='leaderboardlv', aliases=['lblv'])
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
    
    @commands.command(name='rank')
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
    
    @commands.group(name='levelreward', aliases=['lreward'])
    @commands.has_permissions(administrator=True)
    async def level_reward(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)
    
    @level_reward.command(name='set')
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
        embed.add_field(name="Тип награды", value=reward_type, inline=True)
        
        if reward_type in ['currency', 'both']:
            embed.add_field(name="Валюта", value=f"{currency_amount} монет", inline=True)
        
        if reward_type in ['role', 'both']:
            embed.add_field(name="Роль", value=role.mention, inline=True)
        
        await ctx.send(embed=embed)
    
    @level_reward.command(name='remove')
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
    
    @level_reward.command(name='list')
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
    
    @level_reward.command(name='info')
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
    
    @commands.command(name='setxp')
    @commands.has_permissions(administrator=True)
    async def set_xp(self, ctx, member: discord.Member, amount: int):
        if amount < 0:
            await ctx.send("❌ Опыт не может быть отрицательным!")
            return
            
        self.db.set_xp(member.id, ctx.guild.id, amount)
        new_level = self.calculate_level(amount)
        self.db.set_level(member.id, ctx.guild.id, new_level)
        
        embed = discord.Embed(
            title="✅ Опыт установлен",
            description=f"Опыт {member.mention} установлен на {amount}",
            color=0x00ff00
        )
        embed.add_field(name="Новый уровень", value=new_level, inline=True)
        await ctx.send(embed=embed)
    
    @commands.command(name='setlevel')
    @commands.has_permissions(administrator=True)
    async def set_level_cmd(self, ctx, member: discord.Member, level: int):
        if level < 1:
            await ctx.send("❌ Уровень не может быть меньше 1!")
            return
            
        xp_needed = self.xp_for_level(level)
        self.db.set_xp(member.id, ctx.guild.id, xp_needed)
        self.db.set_level(member.id, ctx.guild.id, level)
        
        embed = discord.Embed(
            title="✅ Уровень установлен",
            description=f"Уровень {member.mention} установлен на {level}",
            color=0x00ff00
        )
        embed.add_field(name="Необходимый опыт", value=xp_needed, inline=True)
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Levels(bot))