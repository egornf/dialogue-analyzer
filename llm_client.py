"""
Клиент для взаимодействия с локальной LLM.
Поддерживает:
- Ollama (/api/chat с параметром format: json)
- OpenAI-совместимый API (/v1/chat/completions - LM Studio, vLLM, LocalAI)
- Режим Mock для тестирования без запущенной модели
"""

import json
import re
import random
from typing import Dict, Any, Optional
import requests


class LocalLLMClient:
    def __init__(
        self,
        provider: str = "ollama",
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5:7b",
        temperature: float = 0.1,
        timeout: int = 120,
        is_mock: bool = False
    ):
        self.provider = provider.lower()
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.timeout = timeout
        self.is_mock = is_mock

    def check_connection(self) -> Dict[str, Any]:
        """Проверяет доступность локального сервера LLM."""
        if self.is_mock:
            return {"status": "ok", "message": "Используется Mock-режим (эмуляция ответов)"}

        try:
            if self.provider == "ollama":
                resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
                if resp.status_code == 200:
                    models_data = resp.json().get("models", [])
                    model_names = [m.get("name") for m in models_data]
                    return {
                        "status": "ok",
                        "available_models": model_names,
                        "model_present": any(self.model in name for name in model_names)
                    }
            else:
                resp = requests.get(f"{self.base_url}/models", timeout=5)
                if resp.status_code == 200:
                    return {"status": "ok"}

            return {"status": "warning", "message": f"Сервер ответил кодом {resp.status_code}"}
        except Exception as e:
            return {
                "status": "error",
                "message": (
                    f"Не удалось подключиться к {self.base_url}. Убедитесь, что локальный движок запущен "
                    f"(например, выполните в терминале: ollama serve или ollama run {self.model}). "
                    f"Детали ошибки: {str(e)}"
                )
            }

    def chat_json(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """
        Отправляет изолированный запрос к LLM с требованием вернуть строгий JSON.
        """
        if self.is_mock:
            return self._mock_response(user_prompt)

        if self.provider == "ollama":
            return self._chat_ollama(system_prompt, user_prompt)
        else:
            return self._chat_openai_compatible(system_prompt, user_prompt)

    def _chat_ollama(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "format": "json",
            "stream": False,
            "options": {
                "temperature": self.temperature
            }
        }

        response = requests.post(url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        raw_content = response.json().get("message", {}).get("content", "")
        return self._extract_json(raw_content)

    def _chat_openai_compatible(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        endpoint = f"{self.base_url}/chat/completions" if self.base_url.endswith("/v1") else f"{self.base_url}/v1/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "response_format": {"type": "json_object"},
            "temperature": self.temperature
        }

        response = requests.post(endpoint, json=payload, timeout=self.timeout)
        response.raise_for_status()
        res_data = response.json()
        raw_content = res_data["choices"][0]["message"]["content"]
        return self._extract_json(raw_content)

    def _extract_json(self, text: str) -> Dict[str, Any]:
        """
        Надежное извлечение JSON из текста (очистка markdown-блоков ```json ... ``` и пробелов).
        """
        text = text.strip()
        # Поиск блока ```json ... ```
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if match:
            text = match.group(1).strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Fallback: поиск первого { и последнего }
            first_brace = text.find("{")
            last_brace = text.rfind("}")
            if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
                sub_text = text[first_brace:last_brace + 1]
                return json.loads(sub_text)
            raise ValueError(f"Не удалось распарсить JSON из ответа модели:\n{text}")

    def _mock_response(self, user_prompt: str) -> Dict[str, Any]:
        """Генерация реалистичного ответа для демонстрации и тестирования пайплайна без GPU."""
        is_aggregate = "СВОДНЫЙ АНАЛИЗ" in user_prompt or "сводный" in user_prompt.lower()
        if is_aggregate:
            return {
                "overall_conclusion": "В целом менеджеры уверенно владеют приветствием и базовыми скриптами, однако ключевыми точками роста остаются выявление глубинных потребностей клиента и четкая фиксация следующего шага.",
                "strengths": [
                    "Вежливый и доброжелательный тон общения во всех диалогах",
                    "Четкое соблюдение регламента приветствия и презентации компании",
                    "Оперативное предоставление базовой информации по продукту"
                ],
                "systemic_mistakes": [
                    "Переход к презентации без предварительного уточнения задач и бюджета клиента",
                    "Слабая проработка возражения «дорого» (сразу переход к скидкам вместо ценности)",
                    "Размытые договоренности о следующем звонке («ну созвонимся на днях»)"
                ],
                "management_recommendations": [
                    "Внедрить тренинг по технике спин-вопросов для выявления скрытых потребностей.",
                    "Разработать матрицу аргументов ценности для отработки ценовых возражений.",
                    "Обязать менеджеров вносить конкретную дату и время следующего контакта в CRM."
                ]
            }

        # Эмуляция оценки конкретного диалога
        scores = {}
        criteria_list = [
            ("greeting", "Приветствие и представление"),
            ("need_discovery", "Выявление потребностей"),
            ("presentation", "Презентация решения / продукта"),
            ("objection_handling", "Работа с возражениями и вопросами"),
            ("next_steps", "Договоренность о следующем шаге"),
            ("etiquette_tone", "Вежливость и этика общения")
        ]
        
        c_results = []
        for cid, cname in criteria_list:
            score = random.randint(6, 10)
            c_results.append({
                "criterion_id": cid,
                "criterion_name": cname,
                "score": score,
                "comment": f"Критерий выполнен на {score}/10. Реплики соответствуют стандарту.",
                "quote": "Менеджер: Добрый день, компания Тест..." if cid == "greeting" else ""
            })

        return {
            "dialogue_summary": "Клиент интересовался стоимостью и условиями поставки. Менеджер ответил на вопросы и согласовал отправку КП.",
            "criteria_evaluations": c_results,
            "overall_dialogue_comment": "Диалог проведен на хорошем профессиональном уровне, контакт с клиентом установлен.",
            "recommendation_for_manager": "Уточнить специфику бизнеса клиента перед повторным звонком."
        }
