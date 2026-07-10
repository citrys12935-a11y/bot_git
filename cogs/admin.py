import discord
from discord.ext import commands
from utils.checks import has_permission

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.hybrid_command(name='sync', description='Синхронизировать слеш-команды (только owner)')
    @has_permission('owner')  # Только owner может синхронизировать
    async def sync(self, ctx):
        """Синхронизировать слеш-команды"""
        try:
            # Синхронизируем глобальные команды
            synced = await self.bot.tree.sync()
            
            # Синхронизируем для текущего сервера
            if ctx.guild:
                await self.bot.tree.sync(guild=ctx.guild)
            
            embed = discord.Embed(
                title="✅ Команды синхронизированы",
                description=f"Синхронизировано {len(synced)} команд",
                color=0x00ff00
            )
            await ctx.send(embed=embed)
            
        except Exception as e:
            embed = discord.Embed(
                title="❌ Ошибка синхронизации",
                description=str(e),
                color=0xff0000
            )
            await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Admin(bot))