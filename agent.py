"""
Plant Agent — Claude + tool use.
Handles text chat and photo analysis.
"""
import json
import logging
from anthropic import AsyncAnthropic

import database as db

logger = logging.getLogger(__name__)
client = AsyncAnthropic()

# ─────────────────────────────────────────────
# System prompt
# ─────────────────────────────────────────────

SYSTEM_PROMPT = """Ты — опытный ботаник и агроном, специализирующийся на комнатных и садовых растениях.
Ты помогаешь пользователям ухаживать за их растениями через Telegram.

═══ ТВОИ ПРИНЦИПЫ ═══

🔬 НАУЧНАЯ ТОЧНОСТЬ
• Давай только проверенные, агрономически обоснованные рекомендации
• Не давай совет, если недостаточно информации — сначала задай уточняющий вопрос
• Если видишь несколько возможных диагнозов — перечисли их с вероятностью

🩺 ДИАГНОСТИКА ПРОБЛЕМ
• Анализируй симптомы системно: сначала самые частые причины
• Учитывай: освещение, полив, влажность, сезон, возраст растения
• Отличай симптомы болезней от неправильного ухода
• Если проблема серьёзная — предупреди честно

📸 АНАЛИЗ ФОТО
• Определяй вид с уверенностью в процентах (например: «Монстера деликатесная, 95%»)
• Описывай видимые признаки проблем детально
• Давай конкретный план действий, а не общие фразы

💾 РАБОТА С КОЛЛЕКЦИЕЙ
• Используй инструменты для управления растениями пользователя
• Если пользователь упоминает своё растение — проверь, есть ли оно в базе
• При добавлении растения — всегда уточняй интервал полива

═══ ФОРМАТ ОТВЕТОВ ═══

• Используй эмодзи для структуры (🌿 🔍 💧 ⚠️ ✅)
• Для диагностики: **Диагноз → Причина → Лечение → Профилактика**
• Для ухода: конкретные цифры (температура, влажность, частота полива)
• Короткие вопросы — короткие ответы (не раздувай текст)
• Всегда отвечай на языке пользователя"""

# ─────────────────────────────────────────────
# Tool definitions
# ─────────────────────────────────────────────

TOOLS = [
    {
        "name": "get_plants",
        "description": "Получить список всех растений пользователя из базы данных",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "integer", "description": "Telegram user ID"}
            },
            "required": ["user_id"],
        },
    },
    {
        "name": "add_plant",
        "description": "Добавить новое растение в коллекцию пользователя",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "integer"},
                "name": {"type": "string", "description": "Вид или название растения"},
                "nickname": {"type": "string", "description": "Имя/прозвище растения"},
                "location": {"type": "string", "description": "Где стоит (подоконник, стол, балкон)"},
                "watering_interval_days": {
                    "type": "integer",
                    "description": "Интервал полива в днях",
                    "default": 7,
                },
                "notes": {"type": "string", "description": "Заметки об уходе"},
            },
            "required": ["user_id", "name"],
        },
    },
    {
        "name": "water_plant",
        "description": "Отметить полив растения. Обновляет дату последнего полива.",
        "input_schema": {
            "type": "object",
            "properties": {
                "plant_id": {"type": "integer"},
                "notes": {"type": "string", "description": "Заметки (например: 'полил с удобрением')"},
            },
            "required": ["plant_id"],
        },
    },
    {
        "name": "get_watering_schedule",
        "description": "Показать расписание полива: какие растения просрочены, нужны сегодня, или скоро",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "integer"}
            },
            "required": ["user_id"],
        },
    },
    {
        "name": "update_plant",
        "description": "Обновить информацию о растении (интервал полива, заметки, локацию и т.д.)",
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
        "description": "Удалить растение из коллекции пользователя",
        "input_schema": {
            "type": "object",
            "properties": {
                "plant_id": {"type": "integer"}
            },
            "required": ["plant_id"],
        },
    },
]


# ─────────────────────────────────────────────
# Tool executor
# ─────────────────────────────────────────────

async def execute_tool(name: str, input_data: dict) -> str:
    try:
        if name == "get_plants":
            plants = await db.get_plants(input_data["user_id"])
            if not plants:
                return "У пользователя нет растений в коллекции."
            return json.dumps(plants, ensure_ascii=False, default=str)

        elif name == "add_plant":
            plant_id = await db.add_plant(**input_data)
            return json.dumps(
                {"success": True, "plant_id": plant_id, "message": "Растение успешно добавлено"},
                ensure_ascii=False,
            )

        elif name == "water_plant":
            await db.water_plant(input_data["plant_id"], input_data.get("notes"))
            return json.dumps({"success": True, "message": "Полив отмечен ✅"})

        elif name == "get_watering_schedule":
            schedule = await db.get_watering_schedule(input_data["user_id"])
            return json.dumps(schedule, ensure_ascii=False, default=str)

        elif name == "update_plant":
            plant_id = input_data.pop("plant_id")
            await db.update_plant(plant_id, **input_data)
            return json.dumps({"success": True, "message": "Растение обновлено"})

        elif name == "delete_plant":
            await db.delete_plant(input_data["plant_id"])
            return json.dumps({"success": True, "message": "Растение удалено"})

        else:
            return f"Инструмент '{name}' не найден"

    except Exception as e:
        logger.error(f"Tool '{name}' error: {e}")
        return json.dumps({"error": str(e)})


# ─────────────────────────────────────────────
# Main agent function
# ─────────────────────────────────────────────

async def chat(
    user_id: int,
    message: str,
    history: list[dict],
    image_base64: str = None,
    image_media_type: str = "image/jpeg",
) -> str:
    """
    Run the plant agent. Returns assistant text response.
    Handles text + optional image input.
    Automatically uses tools when needed.
    """

    # Build user content
    if image_base64:
        user_content = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": image_media_type,
                    "data": image_base64,
                },
            },
            {
                "type": "text",
                "text": message or "Что это за растение? Есть ли проблемы с его здоровьем?",
            },
        ]
    else:
        user_content = message

    messages = history + [{"role": "user", "content": user_content}]

    # Agentic loop (max 5 iterations to avoid infinite loops)
    for iteration in range(5):
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        # No tool calls → return final text
        if response.stop_reason == "end_turn":
            return _extract_text(response.content)

        # Process tool calls
        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    logger.info(f"Tool call: {block.name}({block.input})")
                    result = await execute_tool(block.name, block.input)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        }
                    )

            messages.append({"role": "user", "content": tool_results})

        else:
            # Unexpected stop reason
            logger.warning(f"Unexpected stop_reason: {response.stop_reason}")
            return _extract_text(response.content)

    return "Извини, произошла ошибка при обработке запроса. Попробуй ещё раз."


def _extract_text(content_blocks) -> str:
    return "".join(
        block.text for block in content_blocks if hasattr(block, "text")
    ).strip()
