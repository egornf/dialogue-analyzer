"""
Главный исполняемый скрипт локального анализа диалогов из Excel с помощью LLM.
Запуск:
  python main.py --input calls.xlsx --output results.xlsx
  python main.py --mock (для тестирования пайплайна без запущенного LLM-сервера)
"""

import argparse
import json
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from llm_client import LocalLLMClient
from dialog_parser import DialogueParser
from evaluator import DialogueEvaluator
from aggregator import DialogueAggregator
from excel_exporter import ExcelExporter


def load_config(config_path: str) -> dict:
    p = Path(config_path)
    if not p.exists():
        raise FileNotFoundError(f"Файл конфигурации не найден: {config_path}")
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(
        description="Локальный анализ телефонных разговоров/чатов из Excel с помощью LLM по чек-листу."
    )
    parser.add_argument(
        "-i", "--input",
        default="sample_dialogues.xlsx",
        help="Путь к исходному Excel-файлу с транскриптами (по умолчанию: sample_dialogues.xlsx)"
    )
    parser.add_argument(
        "-o", "--output",
        default="analysis_result.xlsx",
        help="Путь для сохранения итогового Excel-файла (по умолчанию: analysis_result.xlsx)"
    )
    parser.add_argument(
        "-c", "--config",
        default="config.json",
        help="Путь к файлу конфигурации и чек-листа (по умолчанию: config.json)"
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Запуск в режиме Mock (эмуляция ответов LLM без локального GPU/движка для тестирования)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Ограничить количество обрабатываемых диалогов (для быстрой проверки)"
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Переопределить модель LLM (например, qwen2.5:7b, llama3.1:8b)"
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default=None,
        help="Переопределить URL локального сервера (например, http://localhost:11434)"
    )
    parser.add_argument(
        "--provider",
        type=str,
        choices=["ollama", "openai", "mock"],
        default=None,
        help="Провайдер API (ollama или openai/vllm/lmstudio)"
    )

    args = parser.parse_args()

    print("=" * 70)
    print("🚀 СИСТЕМА ЛОКАЛЬНОГО АНАЛИЗА ДИАЛОГОВ (LLM OKK)")
    print("=" * 70)

    # 1. Загрузка конфигурации
    try:
        config = load_config(args.config)
        print(f"✓ Загружен конфиг: {args.config} (критериев в чек-листе: {len(config.get('checklist', []))})")
    except Exception as e:
        print(f"❌ Ошибка загрузки конфига: {e}")
        sys.exit(1)

    # Переопределение параметров из CLI
    llm_cfg = config.get("llm", {})
    provider = args.provider or llm_cfg.get("provider", "ollama")
    base_url = args.base_url or llm_cfg.get("base_url", "http://localhost:11434")
    model = args.model or llm_cfg.get("model", "qwen2.5:7b")
    timeout = llm_cfg.get("timeout_seconds", 120)
    temperature = llm_cfg.get("temperature", 0.1)
    is_mock = args.mock or (provider == "mock")

    # Обновляем конфиг
    config["llm"]["provider"] = provider
    config["llm"]["base_url"] = base_url
    config["llm"]["model"] = model

    # 2. Инициализация LLM клиента
    client = LocalLLMClient(
        provider=provider,
        base_url=base_url,
        model=model,
        temperature=temperature,
        timeout=timeout,
        is_mock=is_mock
    )

    print(f"• Режим работы: {'[MOCK ТЕСТИРОВАНИЕ]' if is_mock else f'Локальный LLM [{provider.upper()}]'}")
    print(f"• Модель: {model}")
    if not is_mock:
        print(f"• Сервер: {base_url}")
        print("• Проверка подключения к локальному движку...")
        conn = client.check_connection()
        if conn.get("status") == "error":
            print(f"❌ {conn.get('message')}")
            print("\n💡 Подсказка: для тестового прогона без запущенной модели используйте ключ: --mock")
            sys.exit(1)
        elif conn.get("status") == "ok":
            if "available_models" in conn:
                print(f"✓ Подключение успешно. Доступные модели: {', '.join(conn['available_models'][:5])}")
                if not conn.get("model_present"):
                    print(f"⚠️ Внимание: модель '{model}' не найдена в списке загруженных моделей Ollama.")
            else:
                print("✓ Подключение к локальному серверу успешно.")

    # 3. Загрузка и парсинг Excel
    input_file = Path(args.input)
    if not input_file.exists():
        print(f"❌ Файл не найден: {input_file}")
        print("💡 Создайте исходный файл или используйте тестовый генератор: python create_sample_excel.py")
        sys.exit(1)

    print(f"\n📂 Загрузка диалогов из: {input_file}")
    try:
        dialogues = DialogueParser.parse_excel(input_file)
        print(f"✓ Успешно распознано диалогов: {len(dialogues)}")
    except Exception as e:
        print(f"❌ Ошибка разбора Excel-файла: {e}")
        sys.exit(1)

    if args.limit and args.limit < len(dialogues):
        dialogues = dialogues[:args.limit]
        print(f"ℹ️ Установлен лимит: обработка первых {len(dialogues)} диалогов.")

    if not dialogues:
        print("❌ Не найдено диалогов для анализа.")
        sys.exit(1)

    # 4. Подиалоговая оценка через LLM
    evaluator = DialogueEvaluator(client, config)
    evaluations = []
    passing_pct = config.get("passing_score_percentage", 70.0)

    print("\n🔍 НАЧАЛО ПОДИАЛОГОВОГО АНАЛИЗА:")
    print("-" * 70)
    t_start = time.time()

    for idx, d in enumerate(dialogues, 1):
        print(f"[{idx}/{len(dialogues)}] Обработка диалога '{d.dialogue_id}'...", end="", flush=True)
        t_d0 = time.time()
        try:
            ev = evaluator.evaluate_dialogue(d)
            evaluations.append(ev)
            dt = round(time.time() - t_d0, 1)
            status_symbol = "✅" if ev.is_passed else "❌"
            print(f" {status_symbol} {ev.score_percentage}% ({ev.total_score}/{ev.max_possible_score}) [{dt}c]")
        except Exception as e:
            print(f" ⚠️ Ошибка обработки: {e}")

    elapsed_eval = round(time.time() - t_start, 1)
    print("-" * 70)
    print(f"✓ Завершен анализ {len(evaluations)} диалогов за {elapsed_eval} сек.")

    if not evaluations:
        print("❌ Ни один диалог не был успешно оценен.")
        sys.exit(1)

    # 5. Совокупный анализ и агрегация
    print("\n📊 Формирование сводного агрегированного отчета и выводов...")
    aggregator = DialogueAggregator(client)
    try:
        summary = aggregator.aggregate(evaluations)
        print("✓ Сводная статистика и заключение сформированы.")
    except Exception as e:
        print(f"⚠️ Ошибка при агрегации: {e}")
        sys.exit(1)

    # 6. Экспорт в итоговый Excel
    print(f"\n💾 Экспорт в Excel: {args.output}")
    try:
        ExcelExporter.export(evaluations, summary, args.output, config)
        print(f"✓ Успешно сохранен двухстраничный файл: {Path(args.output).resolve()}")
    except Exception as e:
        print(f"❌ Ошибка экспорта в Excel: {e}")
        sys.exit(1)

    # 7. Вывод краткого резюме в консоль
    print("\n" + "=" * 70)
    print("📈 КРАТКИЕ ИТОГИ АНАЛИЗА:")
    print("=" * 70)
    print(f"• Всего диалогов: {summary.total_dialogues}")
    print(f"• Прошли порог ({passing_pct}%): {summary.passed_dialogues} ({summary.pass_rate}%)")
    print(f"• Средний балл качества: {summary.avg_score_percentage}%")
    print(f"• Сильнейший критерий: {summary.strongest_criterion}")
    print(f"• Зона роста (слабый критерий): {summary.weakest_criterion}")
    print(f"\n📝 Заключение:\n{summary.overall_conclusion}")
    print("=" * 70)
    print(f"✨ Готово! Подробный отчет со всеми критериями и цитатами доступен в: {args.output}\n")


if __name__ == "__main__":
    main()
