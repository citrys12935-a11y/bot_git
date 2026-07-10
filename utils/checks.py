import discord
from discord.ext import commands
from utils.database import Database

def has_permission(*required_groups):
    """Декоратор для проверки прав по группам ролей"""
    async def predicate(ctx):
        # Если это слеш-команда, используем interaction
        if isinstance(ctx, discord.Interaction):
            author = ctx.user
            guild = ctx.guild
        else:
            # Если это обычная команда
            author = ctx.author
            guild = ctx.guild
        
        # Проверяем права администратора Discord (высший уровень)
        if author.guild_permissions.administrator:
            return True
        
        # Проверяем права владельца сервера
        if author.id == guild.owner_id:
            return True
        
        db = Database()
        
        # Получаем разрешенные роли для требуемых групп
        allowed_role_ids = db.get_roles_for_groups(guild.id, required_groups)
        user_role_ids = [role.id for role in author.roles]
        
        # Проверяем, есть ли у пользователя хотя бы одна разрешенная роль
        if set(allowed_role_ids) & set(user_role_ids):
            return True
        
        # Отправляем сообщение об ошибке
        error_msg = "❌ У вас недостаточно прав для выполнения этой команды!"
        
        if isinstance(ctx, discord.Interaction):
            if not ctx.response.is_done():
                await ctx.response.send_message(error_msg, ephemeral=True)
        else:
            await ctx.send(error_msg, ephemeral=True)
        
        return False
    
    return commands.check(predicate)

def is_room_owner():
    """Декоратор для проверки, является ли пользователь владельцем приватной комнаты"""
    async def predicate(ctx):
        # Этот декоратор можно использовать для дополнительных проверок
        # в будущем, если потребуется
        return True
    return commands.check(predicate)

def check_permission(author, guild, required_groups):
    """
    Функция для проверки прав по группам ролей (для использования внутри команд)
    
    Параметры:
    ----------
    author : discord.Member
        Пользователь для проверки
    guild : discord.Guild
        Сервер
    required_groups : list
        Список требуемых групп
        
    Возвращает:
    -----------
    bool
        True если есть права, False если нет
    """
    # Проверяем права администратора Discord
    if author.guild_permissions.administrator:
        return True
    
    # Проверяем, является ли пользователь владельцем сервера
    if guild.owner_id == author.id:
        return True
    
    db = Database()
    
    # Получаем разрешенные роли для требуемых групп
    allowed_role_ids = db.get_roles_for_groups(guild.id, required_groups)
    user_role_ids = [role.id for role in author.roles]
    
    # Проверяем, есть ли у пользователя хотя бы одна разрешенная роль
    return bool(set(allowed_role_ids) & set(user_role_ids))

def get_user_permission_level(author, guild):
    """
    Получить уровень прав пользователя
    
    Возвращает:
    -----------
    str
        Уровень прав пользователя (player, moderator, admin, high_admin, owner)
        или None если нет назначенных прав
    """
    # Проверяем владельца сервера
    if guild.owner_id == author.id:
        return 'owner'
    
    # Проверяем администратора Discord
    if author.guild_permissions.administrator:
        return 'owner'
    
    db = Database()
    
    # Проверяем группы от высшей к низшей
    groups = ['owner', 'high_admin', 'admin', 'moderator', 'player']
    
    for group in groups:
        allowed_role_ids = db.get_roles_for_groups(guild.id, [group])
        user_role_ids = [role.id for role in author.roles]
        
        if set(allowed_role_ids) & set(user_role_ids):
            return group
    
    return None

def is_high_admin():
    """Декоратор для проверки high_admin+ прав"""
    async def predicate(ctx):
        if check_permission(ctx.author, ctx.guild, ['high_admin', 'owner']):
            return True
        
        # Отправляем сообщение об ошибке
        error_msg = "❌ Только high_admin+ могут выполнять эту команду!"
        if isinstance(ctx, discord.Interaction):
            if not ctx.response.is_done():
                await ctx.response.send_message(error_msg, ephemeral=True)
        else:
            await ctx.send(error_msg, ephemeral=True)
        
        return False
    return commands.check(predicate)