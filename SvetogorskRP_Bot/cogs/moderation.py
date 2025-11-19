import discord
from discord.ext import commands
import asyncio
from datetime import datetime, timedelta

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        from utils.database import Database
        self.db = Database()

    async def get_log_channel(self, guild_id):
        settings = self.db.get_server_settings(guild_id)
        if not settings[9]:
            return None
        
        channel_id = settings[10]
        if not channel_id:
            return None
        
        channel = self.bot.get_channel(channel_id)
        return channel

    async def send_log(self, guild, embed):
        channel = await self.get_log_channel(guild.id)
        if channel:
            try:
                await channel.send(embed=embed)
            except:
                pass

    @commands.command(name='mute')
    @commands.has_permissions(manage_roles=True)
    async def mute(self, ctx, member: discord.Member, time: str, *, reason="Не указана"):
        if member == ctx.author:
            embed = discord.Embed(
                title="❌ Ошибка",
                description="Вы не можете замутить самого себя!",
                color=0xff0000
            )
            await ctx.send(embed=embed)
            return
        
        if member.bot:
            embed = discord.Embed(
                title="❌ Ошибка",
                description="Нельзя замутить бота!",
                color=0xff0000
            )
            await ctx.send(embed=embed)
            return

        mute_role = discord.utils.get(ctx.guild.roles, name="Muted")
        if not mute_role:
            try:
                mute_role = await ctx.guild.create_role(name="Muted")
                for channel in ctx.guild.channels:
                    await channel.set_permissions(mute_role, speak=False, send_messages=False)
            except discord.Forbidden:
                embed = discord.Embed(
                    title="❌ Ошибка",
                    description="У бота недостаточно прав для создания роли мута!",
                    color=0xff0000
                )
                await ctx.send(embed=embed)
                return
        
        try:
            time_amount = int(time[:-1])
            time_unit = time[-1].lower()
            
            if time_unit == 's':
                delta = timedelta(seconds=time_amount)
                time_display = f"{time_amount} секунд"
            elif time_unit == 'm':
                delta = timedelta(minutes=time_amount)
                time_display = f"{time_amount} минут"
            elif time_unit == 'h':
                delta = timedelta(hours=time_amount)
                time_display = f"{time_amount} часов"
            elif time_unit == 'd':
                delta = timedelta(days=time_amount)
                time_display = f"{time_amount} дней"
            else:
                await ctx.send("❌ Неверный формат времени! Используйте: s, m, h, d")
                return
        except ValueError:
            embed = discord.Embed(
                title="❌ Ошибка",
                description="Неверный формат времени! Пример: `10m`, `1h`, `7d`",
                color=0xff0000
            )
            await ctx.send(embed=embed)
            return

        try:
            await member.add_roles(mute_role, reason=reason)
            
            embed = discord.Embed(title="🔇 Мут выдан", color=0xff0000)
            embed.add_field(name="👤 Пользователь", value=member.mention, inline=True)
            embed.add_field(name="⏰ Время", value=time_display, inline=True)
            embed.add_field(name="📝 Причина", value=reason, inline=True)
            embed.add_field(name="🛡️ Модератор", value=ctx.author.mention, inline=True)
            embed.timestamp = datetime.now()
            
            await ctx.send(embed=embed)
            
            # Логирование
            log_embed = discord.Embed(
                title="🔇 Мут через команду",
                color=0xff0000,
                timestamp=datetime.now()
            )
            log_embed.add_field(name="Пользователь", value=member.mention, inline=True)
            log_embed.add_field(name="Модератор", value=ctx.author.mention, inline=True)
            log_embed.add_field(name="Время", value=time_display, inline=True)
            log_embed.add_field(name="Причина", value=reason, inline=False)
            await self.send_log(ctx.guild, log_embed)
            
            try:
                user_embed = discord.Embed(
                    title="🔇 Вам выдан мут",
                    description=f"На сервере {ctx.guild.name}",
                    color=0xff0000
                )
                user_embed.add_field(name="⏰ Длительность", value=time_display, inline=True)
                user_embed.add_field(name="📝 Причина", value=reason, inline=True)
                user_embed.timestamp = datetime.now()
                await member.send(embed=user_embed)
            except:
                pass
            
            await asyncio.sleep(delta.total_seconds())
            if mute_role in member.roles:
                await member.remove_roles(mute_role)
                try:
                    unmute_embed = discord.Embed(
                        title="🔊 Мут снят",
                        description="Время мута истекло",
                        color=0x00ff00
                    )
                    await member.send(embed=unmute_embed)
                except:
                    pass
                    
        except discord.Forbidden:
            embed = discord.Embed(
                title="❌ Ошибка",
                description="У бота недостаточно прав для выдачи мута!",
                color=0xff0000
            )
            await ctx.send(embed=embed)

    @commands.command(name='unmute')
    @commands.has_permissions(manage_roles=True)
    async def unmute(self, ctx, member: discord.Member, *, reason="Не указана"):
        mute_role = discord.utils.get(ctx.guild.roles, name="Muted")
        if mute_role and mute_role in member.roles:
            try:
                await member.remove_roles(mute_role, reason=reason)
                
                embed = discord.Embed(
                    title="🔊 Размут",
                    description=f"{member.mention} был размучен",
                    color=0x00ff00
                )
                embed.add_field(name="📝 Причина", value=reason, inline=True)
                embed.add_field(name="🛡️ Модератор", value=ctx.author.mention, inline=True)
                embed.timestamp = datetime.now()
                
                await ctx.send(embed=embed)
                
                # Логирование
                log_embed = discord.Embed(
                    title="🔊 Размут через команду",
                    color=0x00ff00,
                    timestamp=datetime.now()
                )
                log_embed.add_field(name="Пользователь", value=member.mention, inline=True)
                log_embed.add_field(name="Модератор", value=ctx.author.mention, inline=True)
                log_embed.add_field(name="Причина", value=reason, inline=False)
                await self.send_log(ctx.guild, log_embed)
                
                try:
                    user_embed = discord.Embed(
                        title="🔊 Мут снят",
                        description=f"На сервере {ctx.guild.name}",
                        color=0x00ff00
                    )
                    user_embed.add_field(name="📝 Причина", value=reason, inline=True)
                    user_embed.timestamp = datetime.now()
                    await member.send(embed=user_embed)
                except:
                    pass
                    
            except discord.Forbidden:
                embed = discord.Embed(
                    title="❌ Ошибка",
                    description="У бота недостаточно прав для снятия мута!",
                    color=0xff0000
                )
                await ctx.send(embed=embed)
        else:
            embed = discord.Embed(
                title="❌ Ошибка",
                description="Пользователь не в муте или роль мута не найдена!",
                color=0xff0000
            )
            await ctx.send(embed=embed)

    @commands.command(name='warn')
    @commands.has_permissions(manage_roles=True)
    async def warn(self, ctx, member: discord.Member, *, reason="Не указана"):
        if member == ctx.author:
            embed = discord.Embed(
                title="❌ Ошибка",
                description="Вы не можете выдать предупреждение самому себе!",
                color=0xff0000
            )
            await ctx.send(embed=embed)
            return
        
        if member.bot:
            embed = discord.Embed(
                title="❌ Ошибка",
                description="Нельзя выдать предупреждение боту!",
                color=0xff0000
            )
            await ctx.send(embed=embed)
            return

        embed = discord.Embed(title="⚠️ Предупреждение выдано", color=0xffa500)
        embed.add_field(name="👤 Пользователь", value=member.mention, inline=True)
        embed.add_field(name="📝 Причина", value=reason, inline=True)
        embed.add_field(name="🛡️ Модератор", value=ctx.author.mention, inline=True)
        embed.timestamp = datetime.now()
        
        await ctx.send(embed=embed)
        
        # Логирование
        log_embed = discord.Embed(
            title="⚠️ Предупреждение через команду",
            color=0xffa500,
            timestamp=datetime.now()
        )
        log_embed.add_field(name="Пользователь", value=member.mention, inline=True)
        log_embed.add_field(name="Модератор", value=ctx.author.mention, inline=True)
        log_embed.add_field(name="Причина", value=reason, inline=False)
        await self.send_log(ctx.guild, log_embed)
        
        try:
            user_embed = discord.Embed(
                title="⚠️ Вы получили предупреждение",
                description=f"На сервере {ctx.guild.name}",
                color=0xffa500
            )
            user_embed.add_field(name="📝 Причина", value=reason, inline=True)
            user_embed.timestamp = datetime.now()
            await member.send(embed=user_embed)
        except:
            pass

    @commands.command(name='kick')
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason="Не указана"):
        if member == ctx.author:
            embed = discord.Embed(
                title="❌ Ошибка",
                description="Вы не можете кикнуть самого себя!",
                color=0xff0000
            )
            await ctx.send(embed=embed)
            return
        
        if member.bot:
            embed = discord.Embed(
                title="❌ Ошибка",
                description="Нельзя кикнуть бота!",
                color=0xff0000
            )
            await ctx.send(embed=embed)
            return

        try:
            await member.kick(reason=reason)
            
            embed = discord.Embed(title="👢 Кик", color=0xff6b6b)
            embed.add_field(name="👤 Пользователь", value=member.mention, inline=True)
            embed.add_field(name="📝 Причина", value=reason, inline=True)
            embed.add_field(name="🛡️ Модератор", value=ctx.author.mention, inline=True)
            embed.timestamp = datetime.now()
            
            await ctx.send(embed=embed)
            
            # Логирование
            log_embed = discord.Embed(
                title="👢 Кик через команду",
                color=0xff6b6b,
                timestamp=datetime.now()
            )
            log_embed.add_field(name="Пользователь", value=member.mention, inline=True)
            log_embed.add_field(name="Модератор", value=ctx.author.mention, inline=True)
            log_embed.add_field(name="Причина", value=reason, inline=False)
            await self.send_log(ctx.guild, log_embed)
            
        except discord.Forbidden:
            embed = discord.Embed(
                title="❌ Ошибка",
                description="У бота недостаточно прав для кика!",
                color=0xff0000
            )
            await ctx.send(embed=embed)

    @commands.command(name='ban')
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason="Не указана"):
        if member == ctx.author:
            embed = discord.Embed(
                title="❌ Ошибка",
                description="Вы не можете забанить самого себя!",
                color=0xff0000
            )
            await ctx.send(embed=embed)
            return
        
        if member.bot:
            embed = discord.Embed(
                title="❌ Ошибка",
                description="Нельзя забанить бота!",
                color=0xff0000
            )
            await ctx.send(embed=embed)
            return

        try:
            await member.ban(reason=reason)
            
            embed = discord.Embed(title="🔨 Бан", color=0xff0000)
            embed.add_field(name="👤 Пользователь", value=member.mention, inline=True)
            embed.add_field(name="📝 Причина", value=reason, inline=True)
            embed.add_field(name="🛡️ Модератор", value=ctx.author.mention, inline=True)
            embed.timestamp = datetime.now()
            
            await ctx.send(embed=embed)
            
            # Логирование
            log_embed = discord.Embed(
                title="🔨 Бан через команду",
                color=0xff0000,
                timestamp=datetime.now()
            )
            log_embed.add_field(name="Пользователь", value=member.mention, inline=True)
            log_embed.add_field(name="Модератор", value=ctx.author.mention, inline=True)
            log_embed.add_field(name="Причина", value=reason, inline=False)
            await self.send_log(ctx.guild, log_embed)
            
        except discord.Forbidden:
            embed = discord.Embed(
                title="❌ Ошибка",
                description="У бота недостаточно прав для бана!",
                color=0xff0000
            )
            await ctx.send(embed=embed)

    @commands.command(name='clear')
    @commands.has_permissions(manage_messages=True)
    async def clear(self, ctx, amount: int):
        if amount > 100:
            embed = discord.Embed(
                title="❌ Ошибка",
                description="Нельзя удалить больше 100 сообщений за раз!",
                color=0xff0000
            )
            await ctx.send(embed=embed)
            return
        
        if amount < 1:
            embed = discord.Embed(
                title="❌ Ошибка",
                description="Укажите число больше 0!",
                color=0xff0000
            )
            await ctx.send(embed=embed)
            return

        deleted = await ctx.channel.purge(limit=amount + 1)
        
        embed = discord.Embed(
            title="🗑️ Очистка сообщений",
            description=f"Удалено {len(deleted) - 1} сообщений",
            color=0x00ff00
        )
        embed.add_field(name="📊 Количество", value=len(deleted) - 1, inline=True)
        embed.add_field(name="🛡️ Модератор", value=ctx.author.mention, inline=True)
        embed.timestamp = datetime.now()
        
        # Логирование
        log_embed = discord.Embed(
            title="🗑️ Очистка сообщений через команду",
            color=0x00ff00,
            timestamp=datetime.now()
        )
        log_embed.add_field(name="Модератор", value=ctx.author.mention, inline=True)
        log_embed.add_field(name="Канал", value=ctx.channel.mention, inline=True)
        log_embed.add_field(name="Количество", value=len(deleted) - 1, inline=True)
        await self.send_log(ctx.guild, log_embed)
        
        message = await ctx.send(embed=embed)
        await asyncio.sleep(5)
        await message.delete()

async def setup(bot):
    await bot.add_cog(Moderation(bot))