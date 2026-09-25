"""
Модуль подиалоговой оценки разговоров на основе чек-листа.
Формирует изолированные запросы в LLM и парсит структурированные оценки.
"""

from dataclasses import dataclass, asdict
from typing import List, Dict, Any
from dialog_parser import DialogueItem
from llm_client import LocalLLMClient


@dataclass
class CriterionResult:
    criterion_id: str
    criterion_name: str
    score: float
    max_score: float
    weight: float
    comment: str
    quote: str


@dataclass
class DialogueEvaluation:
    dialogue_id: str
    dialogue_text: str
    criteria: List[CriterionResult]
    total_score: float
    max_possible_score: float
    score_percentage: float
    is_passed: bool
    summary: str
    overall_comment: str
    recommendation: str
    metadata: Dict[str, Any]


class DialogueEvaluator:
    def __init__(self, llm_client: LocalLLMClient, config: Dict[str, Any]):
        self.client = llm_client
        self.config = config
        self.checklist = config.get("checklist", [])
        self.passing_percentage = config.get("passing_score_percentage", 70.0)

    def _build_system_prompt(self) -> str:
        criteria_desc = []
        for idx, item in enumerate(self.checklist, 1):
            criteria_desc.append(
                f"{idx}. ID: '{item['id']}' | Название: '{item['name']}' | "
                f"Макс. балл: {item.get('max_score', 10)}\n   Описание: {item.get('description', '')}"
            )
        criteria_str = "\n".join(criteria_desc)

        return (
            "Ты — независимый, объективный и строгий эксперт по контролю качества (ОКК) клиентских и телефонных переговоров.\n"
            "Твоя задача: детально проанализировать предоставленный транскрипт диалога и оценить его строго по критериям чек-листа.\n\n"
            "### ЧЕК-ЛИСТ КРИТЕРИЕВ ОЦЕНКИ:\n"
            f"{criteria_str}\n\n"
            "### ТРЕБОВАНИЯ К ОЦЕНКЕ:\n"
            "1. По каждому критерию выставь целочисленный балл от 0 до максимального балла критерия.\n"
            "2. Для каждого критерия напиши краткое, но емкое обоснование (почему выставлен именно такой балл) и при наличии приведи прямую цитату из текста диалога.\n"
            "3. Напиши краткое саммари диалога (о чем был разговор и чем закончился).\n"
            "4. Напиши общий комментарий по диалогу и 1 конкретную рекомендацию менеджеру.\n"
            "5. Ответ ОБЯЗАТЕЛЬНО должен быть валидным JSON-объектом следующей структуры:\n"
            "{\n"
            '  "dialogue_summary": "Краткое описание сути диалога",\n'
            '  "criteria_evaluations": [\n'
            '    {\n'
            '      "criterion_id": "greeting",\n'
            '      "criterion_name": "Приветствие и представление",\n'
            '      "score": 10,\n'
            '      "comment": "Обоснование оценки",\n'
            '      "quote": "Цитата из диалога (если есть)"\n'
            '    }\n'
            '  ],\n'
            '  "overall_dialogue_comment": "Общий комментарий к работе сотрудника в этом звонке",\n'
            '  "recommendation_for_manager": "Конкретная точка роста"\n'
            "}"
        )

    def evaluate_dialogue(self, dialogue: DialogueItem) -> DialogueEvaluation:
        """
        Выполняет изолированный запрос к LLM для оценки одного диалога.
        """
        system_prompt = self._build_system_prompt()
        user_prompt = (
            f"Оцени следующий разговор (ID: {dialogue.dialogue_id}):\n\n"
            f"--- НАЧАЛО ТРАНСКРИПТА ---\n"
            f"{dialogue.text}\n"
            f"--- КОНЕЦ ТРАНСКРИПТА ---\n\n"
            f"Верни ответ строго в формате JSON по схеме."
        )

        resp_json = self.client.chat_json(system_prompt, user_prompt)

        # Собираем критерии и сопоставляем с конфигурацией
        raw_evals = {e.get("criterion_id"): e for e in resp_json.get("criteria_evaluations", [])}
        
        criterion_results: List[CriterionResult] = []
        total_weighted_score = 0.0
        max_possible_weighted = 0.0

        for item in self.checklist:
            c_id = item["id"]
            max_s = float(item.get("max_score", 10))
            weight = float(item.get("weight", 1.0))
            eval_data = raw_evals.get(c_id, {})

            score = float(eval_data.get("score", 0.0))
            # Ограничиваем рамками [0, max_score]
            score = max(0.0, min(score, max_s))
            comment = str(eval_data.get("comment", "Оценка выставлена")).strip()
            quote = str(eval_data.get("quote", "")).strip()

            total_weighted_score += score * weight
            max_possible_weighted += max_s * weight

            criterion_results.append(
                CriterionResult(
                    criterion_id=c_id,
                    criterion_name=item["name"],
                    score=score,
                    max_score=max_s,
                    weight=weight,
                    comment=comment,
                    quote=quote
                )
            )

        pct = (total_weighted_score / max_possible_weighted * 100) if max_possible_weighted > 0 else 0.0
        is_passed = pct >= self.passing_percentage

        return DialogueEvaluation(
            dialogue_id=dialogue.dialogue_id,
            dialogue_text=dialogue.text,
            criteria=criterion_results,
            total_score=round(total_weighted_score, 2),
            max_possible_score=round(max_possible_weighted, 2),
            score_percentage=round(pct, 1),
            is_passed=is_passed,
            summary=resp_json.get("dialogue_summary", ""),
            overall_comment=resp_json.get("overall_dialogue_comment", ""),
            recommendation=resp_json.get("recommendation_for_manager", ""),
            metadata=dialogue.metadata
        )
