import discord
from discord import app_commands
from discord.ext import commands
import time

class Utils(commands.Cog):
    """Утилиты и полезные команды"""
    
    def __init__(self, bot):
        self.bot = bot
        self.start_time = time.time()
    
    @commands.hybrid_command(name='ping', description='Проверить задержку бота')
    async def ping(self, ctx):
        """Показать пинг бота"""
        # Замеряем время отправки сообщения
        start = time.time()
        msg = await ctx.send("🏓 Измерение пинга...")
        end = time.time()
        
        # Вычисляем задержки
        api_latency = round((end - start) * 1000, 2)  # Время отправки сообщения
        websocket_latency = round(self.bot.latency * 1000, 2)  # Задержка WebSocket
        
        # Время работы бота
        uptime_seconds = int(time.time() - self.start_time)
        days, uptime_seconds = divmod(uptime_seconds, 86400)
        hours, uptime_seconds = divmod(uptime_seconds, 3600)
        minutes, seconds = divmod(uptime_seconds, 60)
        
        uptime_str = ""
        if days > 0:
            uptime_str += f"{days}д "
        if hours > 0:
            uptime_str += f"{hours}ч "
        if minutes > 0:
            uptime_str += f"{minutes}м "
        uptime_str += f"{seconds}с"
        
        embed = discord.Embed(
            title="🏓 Понг!",
            description="Статистика задержки бота",
            color=0x00ff00
        )
        
        embed.add_field(name="📡 Задержка WebSocket", value=f"{websocket_latency} мс", inline=True)
        embed.add_field(name="📨 Задержка API", value=f"{api_latency} мс", inline=True)
        embed.add_field(name="🕐 Время работы", value=uptime_str, inline=True)
        
        embed.add_field(
            name="📊 Статус", 
            value="✅ Отлично" if websocket_latency < 100 else 
                  "⚠️ Хорошо" if websocket_latency < 200 else 
                  "🔻 Медленно" if websocket_latency < 400 else 
                  "❌ Критично",
            inline=True
        )
        
        embed.add_field(
            name="🎮 Игроки", 
            value=f"👥 {len(self.bot.users):,}",
            inline=True
        )
        
        embed.add_field(
            name="🌐 Серверы", 
            value=f"🖥️ {len(self.bot.guilds)}",
            inline=True
        )
        
        embed.set_footer(text=f"ID бота: {self.bot.user.id}")
        
        await msg.edit(content="", embed=embed)
    
    @commands.hybrid_command(name='uptime', description='Время работы бота')
    async def uptime(self, ctx):
        """Показать время работы бота"""
        uptime_seconds = int(time.time() - self.start_time)
        
        days, uptime_seconds = divmod(uptime_seconds, 86400)
        hours, uptime_seconds = divmod(uptime_seconds, 3600)
        minutes, seconds = divmod(uptime_seconds, 60)
        
        uptime_str = ""
        if days > 0:
            uptime_str += f"**{days}** день(дней) "
        if hours > 0:
            uptime_str += f"**{hours}** час(ов) "
        if minutes > 0:
            uptime_str += f"**{minutes}** минут(ы) "
        uptime_str += f"**{seconds}** секунд(ы)"
        
        embed = discord.Embed(
            title="⏰ Время работы бота",
            description=f"Бот работает: {uptime_str}",
            color=0x00ff00
        )
        
        # Примерное время перезапуска (если были бы обновления)
        restart_time = time.strftime("%d.%m.%Y %H:%M:%S", time.localtime(self.start_time))
        embed.add_field(name="🔄 Последний запуск", value=restart_time, inline=True)
        
        # Статистика
        embed.add_field(name="🎮 Игроки", value=f"👥 {len(self.bot.users):,}", inline=True)
        embed.add_field(name="🌐 Серверы", value=f"🖥️ {len(self.bot.guilds)}", inline=True)
        
        embed.set_footer(text="Бот для Светогорска")
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Utils(bot))