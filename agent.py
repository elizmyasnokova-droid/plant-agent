"""
Plant Agent — Claude + tool use.
"""
import json
import logging
from anthropic import AsyncAnthropic

import database as db
from weather import get_weather

logger = logging.getLogger(__name__)
client = AsyncAnthropic()

SYSTEM_PROMPT = """Ты — опытный ботаник и агроном, специализирующийся на комнатных и садовых растениях.

═══ ПРИНЦИПЫ ═══

🔬 НАУЧНАЯ ТОЧНОСТЬ
• Только проверенные, агрономически обоснованные рекомендации
• Если недостаточно информации — задай уточняющий вопрос
• Несколько диагнозов — перечисли с вероятностью (%)

🩺 ДИАГНОСТИКА
• Анализируй симптомы системно: сначала частые причины
• Учитывай: освещение, полив, влажность, сезон, возраст
• Если проблема серьёзная — предупреди честно

📸 АНАЛИЗ ФОТО
• Определяй вид с уверенностью в % (например: «Монстера деликатесная, 95%»)
• Описывай видимые признаки проблем
• Давай конкретный план действий

📸 СОХРАНЕНИЕ ФОТО
• Если в начале сообщения есть [photo_file_id: XXXXX] — это Telegram ID фото
• Когда добавляешь растение через фото — после add_plant сразу вызови save_plant_photo

🌤️ ПОГОДА И ПОЛИВ
• Используй инструмент get_weather когда пользователь спрашивает о поливе или уходе
• Учитывай температуру: жарко (>28°C) = поливай чаще, холодно (<15°C) = реже
• Если запрашиваешь погоду — передавай координаты пользователя если они есть

💾 КОЛЛЕКЦИЯ
• Используй инструменты для управления растениями
• При добавлении растения — уточняй интервал полива

📔 ЖУРНАЛ УХОДА
• Когда говорит «удобрил», «пересадил», «обрезал» — логируй через log_care_action
• Типы: полив, удобрение, пересадка, обрезка, лечение, заметка

═══ ФОРМАТ ═══
• Эмодзи для структуры (🌿 🔍 💧 ⚠️ ✅)
• Конкретные цифры (температура, влажность, частота)
• Короткие вопросы — короткие ответы
• Отвечай на языке пользователя"""

TOOLS = [
    {
        "name": "get_plants",
        "description": "Список всех растений пользователя",
        "input_schema": {"type": "object", "properties": {"user_id": {"type": "integer"}}, "required": ["user_id"]},
    },
    {
        "name": "add_plant",
        "description": "Добавить новое растение",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "integer"},
                "name": {"type": "string"},
                "nickname": {"type": "string"},
                "location": {"type": "string"},
                "watering_interval_days": {"type": "integer", "default": 7},
                "notes": {"type": "string"},
            },
            "required": ["user_id", "name"],
        },
    },
    {
        "name": "water_plant",
        "description": "Отметить полив растения",
        "input_schema": {
            "type": "object",
            "properties": {"plant_id": {"type": "integer"}, "notes": {"type": "string"}},
            "required": ["plant_id"],
        },
    },
    {
        "name": "get_watering_schedule",
        "description": "Расписание полива: просрочено, сегодня, скоро",
        "input_schema": {"type": "object", "properties": {"user_id": {"type": "integer"}}, "required": ["user_id"]},
    },
    {
        "name": "update_plant",
        "description": "Обновить информацию о растении",
        "input_schema": {
            "type": "object",
            "properties": {
                "plant_id": {"type": "integer"},
                "nickname": {"type": "string"},
                "location": {"type": "string"},
                "watering_interval_days": {"type": "integer"},
                "notes": {"type": "string"},
            },
            "required": ["plant_id"],
        },
    },
    {
        "name": "delete_plant",
        "description": "Удалить растение",
        "input_schema": {"type": "object", "properties": {"plant_id": {"type": "integer"}}, "required": ["plant_id"]},
    },
    {
        "name": "save_plant_photo",
        "description": "Сохранить фото к растению",
        "input_schema": {
            "type": "object",
            "properties": {"plant_id": {"type": "integer"}, "photo_file_id": {"type": "string"}},
            "required": ["plant_id", "photo_file_id"],
        },
    },
    {
        "name": "log_care_action",
        "description": "Записать действие ухода: удобрение, пересадка, обрезка, лечение, заметка",
        "input_schema": {
            "type": "object",
            "properties": {
                "plant_id": {"type": "integer"},
                "user_id": {"type": "integer"},
                "action_type": {"type": "string", "enum": ["удобрение", "пересадка", "обрезка", "лечение", "заметка", "полив"]},
                "notes": {"type": "string"},
            },
            "required": ["plant_id", "user_id", "action_type"],
        },
    },
    {
        "name": "get_care_history",
        "description": "История ухода за растением",
        "input_schema": {
            "type": "object",
            "properties": {"plant_id": {"type": "integer"}, "limit": {"type": "integer", "default": 10}},
            "required": ["plant_id"],
        },
    },
    {
        "name": "get_weather",
        "description": "Получить текущую погоду и рекомендацию по поливу с учётом температуры",
        "input_schema": {
            "type": "object",
            "properties": {
                "latitude": {"type": "number", "description": "Широта (если известна)"},
                "longitude": {"type": "number", "description": "Долгота (если известна)"},
            },
        },
    },
]


async def execute_tool(name: str, input_data: dict) -> str:
    try:
        if name == "get_plants":
            plants = await db.get_plants(input_data["user_id"])
            return json.dumps(plants or "Растений нет", ensure_ascii=False, default=str)

        elif name == "add_plant":
            plant_id = await db.add_plant(**input_data)
            return json.dumps({"success": True, "plant_id": plant_id}, ensure_ascii=False)

        elif name == "water_plant":
            await db.water_plant(input_data["plant_id"], input_data.get("notes"))
            return json.dumps({"success": True, "message": "Полив отмечен ✅"})

        elif name == "get_watering_schedule":
            schedule = await db.get_watering_schedule(input_data["user_id"])
            return json.dumps(schedule, ensure_ascii=False, default=str)

        elif name == "update_plant":
            plant_id = input_data.pop("plant_id")
            await db.update_plant(plant_id, **input_data)
            return json.dumps({"success": True})

        elif name == "delete_plant":
            await db.delete_plant(input_data["plant_id"])
            return json.dumps({"success": True})

        elif name == "save_plant_photo":
            await db.update_plant(input_data["plant_id"], photo_file_id=input_data["photo_file_id"])
            return json.dumps({"success": True, "message": "Фото сохранено"})

        elif name == "log_care_action":
            await db.log_care_action(
                input_data["plant_id"], input_data["user_id"],
                input_data["action_type"], input_data.get("notes"),
            )
            return json.dumps({"success": True})

        elif name == "get_care_history":
            history = await db.get_care_history(input_data["plant_id"], input_data.get("limit", 10))
            return json.dumps(history, ensure_ascii=False, default=str)

        elif name == "get_weather":
            lat = input_data.get("latitude")
            lon = input_data.get("longitude")
            weather = await get_weather(lat, lon) if lat and lon else await get_weather()
            return json.dumps(weather, ensure_ascii=False)

        return f"Инструмент '{name}' не найден"
    except Exception as e:
        logger.error(f"Tool '{name}' error: {e}")
        return json.dumps({"error": str(e)})


async def chat(user_id: int, message: str, history: list[dict],
               image_base64: str = None, image_media_type: str = "image/jpeg") -> str:

    if image_base64:
        user_content = [
            {"type": "image", "source": {"type": "base64", "media_type": image_media_type, "data": image_base64}},
            {"type": "text", "text": message or "Что это за растение? Есть ли проблемы?"},
        ]
    else:
        user_content = message

    messages = history + [{"role": "user", "content": user_content}]

    for _ in range(5):
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )
        if response.stop_reason == "end_turn":
            return "".join(b.text for b in response.content if hasattr(b, "text")).strip()

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    logger.info(f"Tool: {block.name}")
                    result = await execute_tool(block.name, block.input)
                    tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": result})
            messages.append({"role": "user", "content": tool_results})
        else:
            break

    return "Извини, произошла ошибка. Попробуй ещё раз."
