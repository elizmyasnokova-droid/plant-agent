"""
Погода через Open-Meteo — бесплатно, без API ключа.
"""
import aiohttp
import logging

logger = logging.getLogger(__name__)

# Координаты по умолчанию — Москва
DEFAULT_LAT = 55.75
DEFAULT_LON = 37.62


async def get_weather(lat: float = DEFAULT_LAT, lon: float = DEFAULT_LON) -> dict:
    """Получить текущую погоду. Возвращает dict с температурой и влажностью."""
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,relative_humidity_2m,weather_code"
        f"&timezone=auto"
    )
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                data = await resp.json()
        current = data["current"]
        temp = current["temperature_2m"]
        humidity = current["relative_humidity_2m"]
        code = current["weather_code"]

        # Простое описание по WMO коду
        if code == 0:
            desc = "ясно ☀️"
        elif code in (1, 2, 3):
            desc = "облачно ⛅"
        elif code in range(51, 68):
            desc = "дождь 🌧️"
        elif code in range(71, 78):
            desc = "снег ❄️"
        elif code in range(80, 83):
            desc = "ливень 🌦️"
        elif code in (95, 96, 99):
            desc = "гроза ⛈️"
        else:
            desc = "переменная облачность"

        # Рекомендация по поливу
        if temp >= 28:
            watering_advice = "🌡️ Жарко! Поливай на 30–50% чаще обычного."
        elif temp >= 22:
            watering_advice = "🌤️ Тепло — придерживайся обычного расписания."
        elif temp >= 15:
            watering_advice = "🍃 Прохладно — можно поливать чуть реже."
        else:
            watering_advice = "🧥 Холодно — сократи полив, растения медленнее усваивают воду."

        return {
            "temperature": temp,
            "humidity": humidity,
            "description": desc,
            "watering_advice": watering_advice,
            "summary": f"{temp}°C, {desc}, влажность {humidity}%",
        }
    except Exception as e:
        logger.warning(f"Weather fetch failed: {e}")
        return {
            "temperature": None,
            "summary": "погода недоступна",
            "watering_advice": "Нет данных о погоде.",
        }
