"""
Модуль совокупного анализа и агрегации результатов по всем разговорам.
Выполняет математический расчет KPI и синтезирующий запрос к LLM для формирования итоговых выводов.
"""

from dataclasses import dataclass
from typing import List, Dict, Any
from evaluator import DialogueEvaluation
from llm_client import LocalLLMClient


@dataclass
class CriterionAggregate:
    criterion_id: str
    criterion_name: str
    avg_score: float
    max_score: float
    avg_percentage: float
    weight: float


@dataclass
class AggregateSummary:
    total_dialogues: int
    passed_dialogues: int
    failed_dialogues: int
    pass_rate: float
    avg_score_percentage: float
    criteria_stats: List[CriterionAggregate]
    strongest_criterion: str
    weakest_criterion: str
    overall_conclusion: str
    strengths: List[str]
    systemic_mistakes: List[str]
    management_recommendations: List[str]


class DialogueAggregator:
    def __init__(self, llm_client: LocalLLMClient):
        self.client = llm_client

    def aggregate(self, evaluations: List[DialogueEvaluation]) -> AggregateSummary:
        if not evaluations:
            raise ValueError("Список оценок диалогов пуст. Нечего агрегировать.")

        total = len(evaluations)
        passed = sum(1 for e in evaluations if e.is_passed)
        failed = total - passed
        pass_rate = round((passed / total * 100), 1)
        avg_score_pct = round(sum(e.score_percentage for e in evaluations) / total, 1)

        # Статистика по каждому критерию
        criteria_totals: Dict[str, Dict[str, Any]] = {}
        for ev in evaluations:
            for c in ev.criteria:
                if c.criterion_id not in criteria_totals:
                    criteria_totals[c.criterion_id] = {
                        "name": c.criterion_name,
                        "scores": [],
                        "max_score": c.max_score,
                        "weight": c.weight
                    }
                criteria_totals[c.criterion_id]["scores"].append(c.score)

        criteria_stats: List[CriterionAggregate] = []
        for cid, data in criteria_totals.items():
            avg_s = sum(data["scores"]) / len(data["scores"])
            avg_pct = (avg_s / data["max_score"] * 100) if data["max_score"] > 0 else 0.0
            criteria_stats.append(
                CriterionAggregate(
                    criterion_id=cid,
                    criterion_name=data["name"],
                    avg_score=round(avg_s, 2),
                    max_score=data["max_score"],
                    avg_percentage=round(avg_pct, 1),
                    weight=data["weight"]
                )
            )

        # Сортировка по успешности выполнения
        sorted_by_pct = sorted(criteria_stats, key=lambda x: x.avg_percentage, reverse=True)
        strongest = f"{sorted_by_pct[0].criterion_name} ({sorted_by_pct[0].avg_percentage}%)"
        weakest = f"{sorted_by_pct[-1].criterion_name} ({sorted_by_pct[-1].avg_percentage}%)"

        # Формируем сводный аналитический запрос к LLM
        llm_insights = self._generate_llm_synthesis(evaluations, criteria_stats, avg_score_pct, pass_rate)

        return AggregateSummary(
            total_dialogues=total,
            passed_dialogues=passed,
            failed_dialogues=failed,
            pass_rate=pass_rate,
            avg_score_percentage=avg_score_pct,
            criteria_stats=criteria_stats,
            strongest_criterion=strongest,
            weakest_criterion=weakest,
            overall_conclusion=llm_insights.get("overall_conclusion", ""),
            strengths=llm_insights.get("strengths", []),
            systemic_mistakes=llm_insights.get("systemic_mistakes", []),
            management_recommendations=llm_insights.get("management_recommendations", [])
        )

    def _generate_llm_synthesis(
        self,
        evaluations: List[DialogueEvaluation],
        criteria_stats: List[CriterionAggregate],
        avg_score_pct: float,
        pass_rate: float
    ) -> Dict[str, Any]:
        """
        Финальный синтезирующий запрос к LLM для обобщенного заключения по всему массиву данных.
        """
        stats_lines = [
            f"- {c.criterion_name}: средний балл {c.avg_score}/{c.max_score} ({c.avg_percentage}%)"
            for c in criteria_stats
        ]
        stats_str = "\n".join(stats_lines)

        # Выбираем примеры слабых и сильных диалогов для контекста модели
        sorted_evals = sorted(evaluations, key=lambda e: e.score_percentage)
        worst_samples = sorted_evals[:2]
        best_samples = sorted_evals[-2:]

        samples_text = "Примеры замечаний из худших диалогов:\n"
        for w in worst_samples:
            samples_text += f"- [{w.dialogue_id}]: {w.overall_comment} (Рекомендация: {w.recommendation})\n"

        samples_text += "\nПримеры комментариев из лучших диалогов:\n"
        for b in best_samples:
            samples_text += f"- [{b.dialogue_id}]: {b.overall_comment}\n"

        system_prompt = (
            "Ты — руководитель отдела контроля качества и бизнес-аналитик.\n"
            "Твоя задача — проанализировать сводную статистику проверенных звонков/диалогов компании "
            "и сформировать емкое управленческое заключение для руководства."
        )

        user_prompt = (
            "СВОДНЫЙ АНАЛИЗ МАССИВА ДИАЛОГОВ:\n\n"
            f"Всего проанализировано диалогов: {len(evaluations)}\n"
            f"Средний балл соответствия чек-листу: {avg_score_pct}%\n"
            f"Процент диалогов, прошедших порог качества: {pass_rate}%\n\n"
            f"Статистика по критериям:\n{stats_str}\n\n"
            f"{samples_text}\n\n"
            "Верни ответ строго в формате JSON со следующими полями:\n"
            "{\n"
            '  "overall_conclusion": "Обобщенное аналитическое заключение по всему массиву (2-3 предложения)",\n'
            '  "strengths": ["Сильная сторона 1", "Сильная сторона 2", "Сильная сторона 3"],\n'
            '  "systemic_mistakes": ["Системная ошибка 1", "Системная ошибка 2", "Системная ошибка 3"],\n'
            '  "management_recommendations": ["Рекомендация 1", "Рекомендация 2", "Рекомендация 3"]\n'
            "}"
        )

        try:
            return self.client.chat_json(system_prompt, user_prompt)
        except Exception as e:
            # Fallback на случай сетевых сбоев
            return {
                "overall_conclusion": f"Анализ завершен. Средний балл качества составил {avg_score_pct}%, порог успешно преодолен в {pass_rate}% диалогов.",
                "strengths": [f"Лучший показатель: {criteria_stats[0].criterion_name if criteria_stats else 'Стандарты соблюдены'}"],
                "systemic_mistakes": ["Требуется дополнительное внимание к слабым критериям чек-листа."],
                "management_recommendations": ["Провести выборочный разбор диалогов с баллами ниже порога."]
            }
