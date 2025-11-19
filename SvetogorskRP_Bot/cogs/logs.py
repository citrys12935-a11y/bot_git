import discord
from discord.ext import commands
from datetime import datetime
import asyncio

class Logs(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        from utils.database import Database
        self.db = Database()

    async def get_log_channel(self, guild_id):
        settings = self.db.get_server_settings(guild_id)
        if not settings[9]:  # logs_enabled
            return None
        
        channel_id = settings[10]  # log_channel_id
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

    # События магазина и торговой площадки
    @commands.Cog.listener()
    async def on_shop_purchase(self, ctx, item, price):
        """Логирование покупки в магазине"""
        embed = discord.Embed(
            title="🛍️ Покупка в магазине",
            color=0x00ff00,
            timestamp=datetime.now()
        )
        embed.add_field(name="Покупатель", value=ctx.author.mention, inline=True)
        embed.add_field(name="Предмет", value=item[2], inline=True)
        embed.add_field(name="Цена", value=f"{price} монет", inline=True)
        embed.add_field(name="ID предмета", value=item[0], inline=True)
        await self.send_log(ctx.guild, embed)

    @commands.Cog.listener() 
    async def on_shop_item_add(self, ctx, item_id, name, price, item_type):
        """Логирование добавления предмета в магазин"""
        embed = discord.Embed(
            title="🛍️ Добавлен предмет в магазин",
            color=0x3498db,
            timestamp=datetime.now()
        )
        embed.add_field(name="Администратор", value=ctx.author.mention, inline=True)
        embed.add_field(name="Предмет", value=name, inline=True)
        embed.add_field(name="Цена", value=f"{price} монет", inline=True)
        embed.add_field(name="Тип", value=item_type, inline=True)
        embed.add_field(name="ID", value=item_id, inline=True)
        await self.send_log(ctx.guild, embed)

    @commands.Cog.listener()
    async def on_shop_item_remove(self, ctx, item_id, name):
        """Логирование удаления предмета из магазина"""
        embed = discord.Embed(
            title="🛍️ Удален предмет из магазина",
            color=0xff0000,
            timestamp=datetime.now()
        )
        embed.add_field(name="Администратор", value=ctx.author.mention, inline=True)
        embed.add_field(name="Предмет", value=name, inline=True)
        embed.add_field(name="ID", value=item_id, inline=True)
        await self.send_log(ctx.guild, embed)

    @commands.Cog.listener()
    async def on_market_listing_add(self, ctx, listing_id, item_name, price):
        """Логирование добавления предложения на площадку"""
        embed = discord.Embed(
            title="🏪 Предмет выставлен на площадку",
            color=0x00ff00,
            timestamp=datetime.now()
        )
        embed.add_field(name="Продавец", value=ctx.author.mention, inline=True)
        embed.add_field(name="Предмет", value=item_name, inline=True)
        embed.add_field(name="Цена", value=f"{price} монет", inline=True)
        embed.add_field(name="ID предложения", value=listing_id, inline=True)
        await self.send_log(ctx.guild, embed)

    @commands.Cog.listener()
    async def on_market_purchase(self, ctx, listing_id, item_name, price, seller):
        """Логирование покупки на торговой площадке"""
        embed = discord.Embed(
            title="🏪 Покупка на торговой площадке",
            color=0x00ff00,
            timestamp=datetime.now()
        )
        embed.add_field(name="Покупатель", value=ctx.author.mention, inline=True)
        embed.add_field(name="Продавец", value=seller.mention, inline=True)
        embed.add_field(name="Предмет", value=item_name, inline=True)
        embed.add_field(name="Цена", value=f"{price} монет", inline=True)
        embed.add_field(name="ID предложения", value=listing_id, inline=True)
        await self.send_log(ctx.guild, embed)

    @commands.Cog.listener()
    async def on_market_listing_remove(self, ctx, listing_id):
        """Логирование удаления предложения с площадки"""
        embed = discord.Embed(
            title="🏪 Предложение убрано с площадки",
            color=0xff0000,
            timestamp=datetime.now()
        )
        embed.add_field(name="Пользователь", value=ctx.author.mention, inline=True)
        embed.add_field(name="ID предложения", value=listing_id, inline=True)
        await self.send_log(ctx.guild, embed)

    @commands.Cog.listener()
    async def on_inventory_clear(self, ctx, target):
        """Логирование очистки инвентаря"""
        embed = discord.Embed(
            title="🛍️ Инвентарь очищен",
            color=0xff0000,
            timestamp=datetime.now()
        )
        embed.add_field(name="Администратор", value=ctx.author.mention, inline=True)
        embed.add_field(name="Пользователь", value=target.mention, inline=True)
        await self.send_log(ctx.guild, embed)

    # Остальные события логирования (из твоего кода)
    @commands.Cog.listener()
    async def on_guild_update(self, before, after):
        if before.name != after.name:
            embed = discord.Embed(
                title="🔄 Изменение названия сервера",
                color=0x3498db,
                timestamp=datetime.now()
            )
            embed.add_field(name="До", value=before.name, inline=True)
            embed.add_field(name="После", value=after.name, inline=True)
            await self.send_log(after, embed)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        embed = discord.Embed(
            title="📁 Создан канал",
            description=f"Канал: {channel.mention}",
            color=0x00ff00,
            timestamp=datetime.now()
        )
        embed.add_field(name="Тип", value=str(channel.type).title(), inline=True)
        embed.add_field(name="Категория", value=channel.category.name if channel.category else "Нет", inline=True)
        await self.send_log(channel.guild, embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        embed = discord.Embed(
            title="🗑️ Удален канал",
            description=f"Канал: {channel.name}",
            color=0xff0000,
            timestamp=datetime.now()
        )
        embed.add_field(name="Тип", value=str(channel.type).title(), inline=True)
        embed.add_field(name="Категория", value=channel.category.name if channel.category else "Нет", inline=True)
        await self.send_log(channel.guild, embed)

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before, after):
        if before.name != after.name:
            embed = discord.Embed(
                title="✏️ Переименован канал",
                color=0xf39c12,
                timestamp=datetime.now()
            )
            embed.add_field(name="Канал", value=after.mention, inline=True)
            embed.add_field(name="До", value=before.name, inline=True)
            embed.add_field(name="После", value=after.name, inline=True)
            await self.send_log(after.guild, embed)

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if message.author.bot or not message.guild:
            return
            
        embed = discord.Embed(
            title="🗑️ Удалено сообщение",
            color=0xe74c3c,
            timestamp=datetime.now()
        )
        embed.add_field(name="Автор", value=message.author.mention, inline=True)
        embed.add_field(name="Канал", value=message.channel.mention, inline=True)
        
        if len(message.content) > 0:
            content = message.content[:1024] + "..." if len(message.content) > 1024 else message.content
            embed.add_field(name="Содержимое", value=content, inline=False)
        
        await self.send_log(message.guild, embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if before.author.bot or before.content == after.content or not before.guild:
            return
            
        embed = discord.Embed(
            title="✏️ Изменено сообщение",
            color=0xf39c12,
            timestamp=datetime.now()
        )
        embed.add_field(name="Автор", value=before.author.mention, inline=True)
        embed.add_field(name="Канал", value=before.channel.mention, inline=True)
        
        before_content = before.content[:500] + "..." if len(before.content) > 500 else before.content
        after_content = after.content[:500] + "..." if len(after.content) > 500 else after.content
        
        embed.add_field(name="До", value=before_content or "*пусто*", inline=False)
        embed.add_field(name="После", value=after_content or "*пусто*", inline=False)
        embed.add_field(name="Ссылка", value=f"[Перейти]({after.jump_url})", inline=True)
        
        await self.send_log(before.guild, embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        embed = discord.Embed(
            title="🔨 Пользователь забанен",
            description=f"{user.mention} ({user})",
            color=0xe74c3c,
            timestamp=datetime.now()
        )
        embed.add_field(name="ID", value=user.id, inline=True)
        
        try:
            async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.ban):
                if entry.target.id == user.id:
                    embed.add_field(name="Модератор", value=entry.user.mention, inline=True)
                    if entry.reason:
                        embed.add_field(name="Причина", value=entry.reason, inline=False)
                    break
        except:
            pass
            
        await self.send_log(guild, embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild, user):
        embed = discord.Embed(
            title="🔓 Пользователь разбанен",
            description=f"{user.mention} ({user})",
            color=0x00ff00,
            timestamp=datetime.now()
        )
        embed.add_field(name="ID", value=user.id, inline=True)
        
        try:
            async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.unban):
                if entry.target.id == user.id:
                    embed.add_field(name="Модератор", value=entry.user.mention, inline=True)
                    if entry.reason:
                        embed.add_field(name="Причина", value=entry.reason, inline=False)
                    break
        except:
            pass
            
        await self.send_log(guild, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        if member.guild:
            try:
                async for entry in member.guild.audit_logs(limit=5, action=discord.AuditLogAction.kick):
                    if entry.target.id == member.id:
                        embed = discord.Embed(
                            title="👢 Пользователь кикнут",
                            description=f"{member.mention} ({member})",
                            color=0xe67e22,
                            timestamp=datetime.now()
                        )
                        embed.add_field(name="Модератор", value=entry.user.mention, inline=True)
                        if entry.reason:
                            embed.add_field(name="Причина", value=entry.reason, inline=False)
                        await self.send_log(member.guild, embed)
                        break
            except:
                pass

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if before.channel != after.channel and member.guild:
            embed = discord.Embed(
                title="🎤 Изменение голосового статуса",
                color=0x9b59b6,
                timestamp=datetime.now()
            )
            embed.add_field(name="Пользователь", value=member.mention, inline=True)
            
            if not before.channel and after.channel:
                embed.add_field(name="Действие", value="Подключился", inline=True)
                embed.add_field(name="Канал", value=after.channel.name, inline=True)
            elif before.channel and not after.channel:
                embed.add_field(name="Действие", value="Отключился", inline=True)
                embed.add_field(name="Канал", value=before.channel.name, inline=True)
            else:
                embed.add_field(name="Действие", value="Переместился", inline=True)
                embed.add_field(name="Из", value=before.channel.name, inline=True)
                embed.add_field(name="В", value=after.channel.name, inline=True)
            
            await self.send_log(member.guild, embed)

    # Логирование команд бота
    async def log_bot_command(self, ctx, command, target=None, amount=None, reason=None):
        if not ctx.guild:
            return
            
        embed = discord.Embed(
            title="🤖 Команда бота выполнена",
            color=0x7289da,
            timestamp=datetime.now()
        )
        embed.add_field(name="Команда", value=command, inline=True)
        embed.add_field(name="Пользователь", value=ctx.author.mention, inline=True)
        embed.add_field(name="Канал", value=ctx.channel.mention, inline=True)
        
        if target:
            embed.add_field(name="Цель", value=target.mention, inline=True)
        if amount:
            embed.add_field(name="Количество", value=amount, inline=True)
        if reason:
            embed.add_field(name="Причина", value=reason, inline=False)
            
        await self.send_log(ctx.guild, embed)

async def setup(bot):
    await bot.add_cog(Logs(bot))