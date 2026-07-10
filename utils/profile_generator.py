import os
import io
import aiohttp
import asyncio
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps
import discord

class ProfileCardGenerator:
    def __init__(self):
        self.session = None
        self.PIL_AVAILABLE = True
        
        try:
            # Проверяем доступность шрифтов
            self.load_fonts()
        except ImportError:
            self.PIL_AVAILABLE = False
            print("⚠️ PIL не установлен. Карточки профиля не будут генерироваться.")
    
    def load_fonts(self):
        """Загрузка шрифтов"""
        try:
            # Пытаемся использовать системные шрифты
            self.title_font = ImageFont.truetype("arial.ttf", 36)
            self.subtitle_font = ImageFont.truetype("arial.ttf", 24)
            self.stats_font = ImageFont.truetype("arial.ttf", 20)
            self.small_font = ImageFont.truetype("arial.ttf", 16)
            self.level_font = ImageFont.truetype("arial.ttf", 30)
        except:
            # Используем стандартный шрифт как запасной вариант
            self.title_font = ImageFont.load_default()
            self.subtitle_font = ImageFont.load_default()
            self.stats_font = ImageFont.load_default()
            self.small_font = ImageFont.load_default()
            self.level_font = ImageFont.load_default()
    
    async def get_session(self):
        """Получение или создание aiohttp сессии"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def download_image(self, url):
        """Асинхронная загрузка изображения"""
        try:
            session = await self.get_session()
            async with session.get(url) as response:
                if response.status == 200:
                    image_data = await response.read()
                    return Image.open(io.BytesIO(image_data))
        except Exception as e:
            print(f"❌ Ошибка загрузки изображения {url}: {e}")
        return None
    
    def create_progress_bar(self, width, height, progress, color=(0, 255, 0), bg_color=(50, 50, 50)):
        """Создание прогресс-бара"""
        bar = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(bar)
        
        # Фон прогресс-бара
        draw.rounded_rectangle([0, 0, width, height], radius=height//2, fill=bg_color)
        
        # Заполненная часть
        fill_width = int(width * progress)
        if fill_width > 0:
            draw.rounded_rectangle([0, 0, fill_width, height], radius=height//2, fill=color)
        
        # Обводка
        draw.rounded_rectangle([0, 0, width, height], radius=height//2, outline=(255, 255, 255, 200), width=2)
        
        return bar
    
    def get_level_color(self, level):
        """Получить цвет уровня в зависимости от его значения"""
        if level <= 10:
            return (0, 150, 255)  # Голубой
        elif level <= 25:
            return (0, 200, 100)  # Зеленый
        elif level <= 35:
            return (180, 0, 255)  # Фиолетовый
        elif level <= 50:
            return (255, 165, 0)  # Оранжевый
        else:
            return (255, 50, 50)  # Красный
    
    def create_level_badge(self, level, size=80):
        """Создание круглого значка уровня"""
        # Создаем основное изображение для значка
        badge = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(badge)
        
        # Получаем цвет уровня
        level_color = self.get_level_color(level)
        
        # Создаем градиентный фон
        for i in range(size):
            # Вычисляем интенсивность цвета
            intensity = 150 + int(105 * i / size)
            r = min(255, level_color[0] + int((255 - level_color[0]) * i / size))
            g = min(255, level_color[1] + int((255 - level_color[1]) * i / size))
            b = min(255, level_color[2] + int((255 - level_color[2]) * i / size))
            color = (r, g, b, 255)
            draw.line([(i, 0), (i, size)], fill=color)
        
        # Создаем маску для круга
        mask = Image.new('L', (size, size), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse([0, 0, size, size], fill=255)
        
        # Применяем маску к значку
        badge.putalpha(mask)
        
        # Добавляем белую обводку
        draw_outer = ImageDraw.Draw(badge)
        draw_outer.ellipse([0, 0, size-1, size-1], outline=(255, 255, 255, 255), width=3)
        
        # Добавляем внутреннюю обводку
        inner_size = size - 8
        draw_outer.ellipse([4, 4, inner_size, inner_size], outline=(255, 255, 255, 180), width=2)
        
        # Текст уровня
        text = str(level)
        
        # Пытаемся загрузить жирный шрифт
        try:
            font = ImageFont.truetype("arialbd.ttf", 30)
        except:
            try:
                font = ImageFont.truetype("arial.ttf", 30)
            except:
                font = ImageFont.load_default()
        
        # Вычисляем размер текста
        try:
            text_bbox = font.getbbox(text)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]
        except:
            text_width = len(text) * 15
            text_height = 30
        
        # Позиция текста по центру
        text_x = (size - text_width) // 2
        text_y = (size - text_height) // 2 - 2  # Смещение для лучшего визуального центра
        
        # Добавляем тень текста
        draw.text((text_x + 1, text_y + 1), text, font=font, fill=(0, 0, 0, 180))
        # Основной текст
        draw.text((text_x, text_y), text, font=font, fill=(255, 255, 255, 255))
        
        return badge
    
    def apply_rounded_mask(self, image, radius=20):
        """Применение скругленных углов к изображению"""
        mask = Image.new('L', image.size, 0)
        draw = ImageDraw.Draw(mask)
        draw.rounded_rectangle([0, 0, image.size[0], image.size[1]], radius=radius, fill=255)
        
        result = Image.new('RGBA', image.size, (0, 0, 0, 0))
        result.paste(image, (0, 0), mask)
        return result
    
    def create_avatar_mask(self, size):
        """Создание круглой маски для аватара"""
        mask = Image.new('L', (size, size), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse([0, 0, size, size], fill=255)
        return mask
    
    async def create_profile_card(self, member, user_data, banner_url=None, progress_percent=0):
        """Создание карточки профиля"""
        if not self.PIL_AVAILABLE:
            return None
        
        # Размеры карточки
        card_width = 800
        card_height = 300
        
        # Создаем базовое изображение
        card = Image.new('RGBA', (card_width, card_height), (30, 30, 46, 255))
        draw = ImageDraw.Draw(card)
        
        # Загружаем баннер если есть
        banner = None
        if banner_url:
            banner = await self.download_image(banner_url)
        
        if banner:
            # Масштабируем и обрезаем баннер
            banner_ratio = banner.width / banner.height
            target_ratio = card_width / (card_height * 0.7)
            
            if banner_ratio > target_ratio:
                # Баннер шире - обрезаем по бокам
                new_height = card_height
                new_width = int(new_height * banner_ratio)
                banner = banner.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                # Обрезаем по центру
                left = (new_width - card_width) // 2
                right = left + card_width
                banner = banner.crop((left, 0, right, card_height))
            else:
                # Баннер выше - обрезаем сверху и снизу
                new_width = card_width
                new_height = int(new_width / banner_ratio)
                banner = banner.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                # Обрезаем сверху
                top = 0
                bottom = min(new_height, card_height)
                banner = banner.crop((0, top, new_width, bottom))
            
            # Затемняем баннер для лучшей читаемости текста
            overlay = Image.new('RGBA', (card_width, card_height), (0, 0, 0, 150))
            banner.paste(overlay, (0, 0), overlay)
            
            # Применяем скругленные углы
            banner = self.apply_rounded_mask(banner, radius=20)
            
            # Накладываем баннер на карточку
            card.paste(banner, (0, 0), banner)
        
        # Создаем градиентный оверлей снизу
        gradient = Image.new('RGBA', (card_width, 150), (0, 0, 0, 0))
        draw_grad = ImageDraw.Draw(gradient)
        for i in range(150):
            alpha = int(255 * (i / 150))
            draw_grad.line([(0, i), (card_width, i)], fill=(0, 0, 0, alpha))
        
        card.alpha_composite(gradient, (0, card_height - 150))
        
        # Загрузка аватара пользователя
        avatar_url = str(member.avatar.url) if member.avatar else str(member.default_avatar.url)
        avatar = await self.download_image(avatar_url)
        
        if avatar:
            avatar_size = 120
            # Масштабирование аватара
            avatar = avatar.resize((avatar_size, avatar_size), Image.Resampling.LANCZOS)
            
            # Создание круглой маски
            mask = self.create_avatar_mask(avatar_size)
            
            # Применяем маску
            avatar.putalpha(mask)
            
            # Добавление обводки аватара
            border_size = 6
            bordered_size = avatar_size + border_size * 2
            bordered_avatar = Image.new('RGBA', (bordered_size, bordered_size), (0, 0, 0, 0))
            draw_border = ImageDraw.Draw(bordered_avatar)
            
            # Белая обводка
            draw_border.ellipse([0, 0, bordered_size, bordered_size], fill=(255, 255, 255, 255))
            
            # Накладывание аватара с маской
            bordered_avatar.paste(avatar, (border_size, border_size), avatar)
            
            # Добавление аватара на карточку
            card.alpha_composite(bordered_avatar, (40, card_height - avatar_size - 60))
        
        # Извлечение данных пользователя
        balance = user_data[2]
        xp = user_data[3]
        level = user_data[4]
        
        # Позиции для текста
        text_x = 180 if avatar else 40
        text_y = card_height - 180
        
        # Имя пользователя
        draw.text((text_x, text_y), str(member.display_name), 
                  font=self.title_font, fill=(255, 255, 255, 255))
        
        # Уровень и опыт
        next_level_xp = (level ** 2) * 50
        current_level_xp = ((level - 1) ** 2) * 50
        xp_needed = next_level_xp - xp if xp < next_level_xp else 0
        
        level_text = f"Уровень {level} | {xp} XP"
        draw.text((text_x, text_y + 45), level_text, 
                  font=self.subtitle_font, fill=(200, 200, 200, 255))
        
        # Баланс
        balance_text = f"{balance:,} монет"
        draw.text((text_x, text_y + 85), balance_text, 
                  font=self.stats_font, fill=(255, 215, 0, 255))
        
        # Прогресс до следующего уровня
        if xp_needed > 0:
            progress = (xp - current_level_xp) / (next_level_xp - current_level_xp)
            progress = max(0, min(1, progress))  # Ограничиваем от 0 до 1
            progress_text = f"До уровня {level + 1}: {xp_needed} XP"
            
            # Создаем прогресс-бар
            progress_bar = self.create_progress_bar(300, 20, progress, color=(0, 200, 255))
            card.alpha_composite(progress_bar, (text_x, text_y + 115))
            
            # Текст прогресса
            draw.text((text_x + 310, text_y + 115), progress_text, 
                      font=self.small_font, fill=(180, 180, 180, 255))
        
        # Достижения
        if progress_percent > 0:
            achievements_text = f"Достижения: {progress_percent}%"
            draw.text((text_x, text_y + 145), achievements_text, 
                      font=self.stats_font, fill=(255, 165, 0, 255))
        
        # Значок уровня в правом верхнем углу (круглый с обводкой)
        level_badge = self.create_level_badge(level, 75)
        card.alpha_composite(level_badge, (card_width - 90, 20))
        
        # ID пользователя внизу справа
        id_text = f"ID: {member.id}"
        try:
            text_bbox = draw.textbbox((0, 0), id_text, font=self.small_font)
            text_width = text_bbox[2] - text_bbox[0]
        except:
            text_width = len(id_text) * 8
        
        draw.text((card_width - text_width - 20, card_height - 30), id_text,
                  font=self.small_font, fill=(150, 150, 150, 200))
        
        # Сохраняем во временный файл
        temp_dir = "temp_cards"
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)
        
        temp_path = os.path.join(temp_dir, f"profile_{member.id}_{int(datetime.now().timestamp())}.png")
        card.save(temp_path, "PNG")
        
        return temp_path
    
    async def close(self):
        """Закрытие сессии"""
        if self.session and not self.session.closed:
            await self.session.close()

profile_generator = ProfileCardGenerator()

def cleanup_old_cards(max_age_hours=24):
    """Удаление старых временных файлов карточек"""
    try:
        temp_dir = "temp_cards"
        if not os.path.exists(temp_dir):
            return
        
        current_time = datetime.now().timestamp()
        for filename in os.listdir(temp_dir):
            filepath = os.path.join(temp_dir, filename)
            if os.path.isfile(filepath):
                file_age = current_time - os.path.getmtime(filepath)
                if file_age > max_age_hours * 3600:
                    os.remove(filepath)
    except Exception as e:
        print(f"Ошибка очистки старых карточек: {e}")