"""
Модуль экспорта результатов анализа в презентабельный Excel-файл (.xlsx).
Создает два листа:
1. "Сводный отчет": общие метрики, статистика по критериям, сильные/слабые стороны, рекомендации.
2. "Детализация": построчные оценки по каждому диалогу, баллы и комментарии по каждому критерию чек-листа.
"""

from pathlib import Path
from typing import List, Dict, Any
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from evaluator import DialogueEvaluation
from aggregator import AggregateSummary


class ExcelExporter:
    # Цветовая палитра
    COLOR_HEADER_BG = "1F4E79"        # Темно-синий
    COLOR_HEADER_TEXT = "FFFFFF"      # Белый
    COLOR_ACCENT = "2E75B6"           # Синий акцент
    COLOR_PASS_BG = "E2EFDA"          # Светло-зеленый (успех)
    COLOR_PASS_TEXT = "375623"        # Темно-зеленый
    COLOR_FAIL_BG = "FCE4D6"          # Светло-красный (провал)
    COLOR_FAIL_TEXT = "C65911"        # Темно-оранжевый/красный
    COLOR_ZEBRA = "F2F4F7"            # Светло-серый фон четных строк
    COLOR_SECTION_BG = "D9E1F2"       # Светло-синий фон подзаголовков

    @classmethod
    def export(
        cls,
        evaluations: List[DialogueEvaluation],
        summary: AggregateSummary,
        output_path: str | Path,
        config: Dict[str, Any]
    ):
        wb = openpyxl.Workbook()
        # Удаляем дефолтный лист
        wb.remove(wb.active)

        # 1. Лист со сводным отчетом
        ws_summary = wb.create_sheet(title="Сводный отчет")
        cls._build_summary_sheet(ws_summary, summary, config)

        # 2. Лист с детализацией
        ws_details = wb.create_sheet(title="Детализация")
        cls._build_details_sheet(ws_details, evaluations, config)

        # Сохраняем файл
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        wb.save(out_p)

    @classmethod
    def _get_borders(cls):
        thin_border = Border(
            left=Side(style="thin", color="D9D9D9"),
            right=Side(style="thin", color="D9D9D9"),
            top=Side(style="thin", color="D9D9D9"),
            bottom=Side(style="thin", color="D9D9D9")
        )
        return thin_border

    @classmethod
    def _build_summary_sheet(cls, ws, summary: AggregateSummary, config: Dict[str, Any]):
        ws.views.sheetView[0].showGridLines = True
        thin_border = cls._get_borders()

        # Заголовок отчета
        ws.merge_cells("A1:G1")
        title_cell = ws["A1"]
        title_cell.value = "АНАЛИТИЧЕСКИЙ ОТЧЕТ КОНТРОЛЯ КАЧЕСТВА ДИАЛОГОВ"
        title_cell.font = Font(name="Calibri", size=16, bold=True, color="FFFFFF")
        title_cell.fill = PatternFill(start_color=cls.COLOR_HEADER_BG, fill_type="solid")
        title_cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[1].height = 40

        # Подзаголовок с мета-информацией
        ws.merge_cells("A2:G2")
        meta_cell = ws["A2"]
        llm_cfg = config.get("llm", {})
        meta_cell.value = (
            f"Локальная модель: {llm_cfg.get('model', 'N/A')} | "
            f"Провайдер: {llm_cfg.get('provider', 'N/A').upper()} | "
            f"Порог прохождения: {config.get('passing_score_percentage', 70)}%"
        )
        meta_cell.font = Font(name="Calibri", size=10, italic=True, color="FFFFFF")
        meta_cell.fill = PatternFill(start_color=cls.COLOR_ACCENT, fill_type="solid")
        meta_cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[2].height = 24

        # Карточки ключевых KPI (Строки 4-5)
        kpi_metrics = [
            ("Всего диалогов", f"{summary.total_dialogues}", "A4", "B4", "A5", "B5"),
            ("Прошли порог", f"{summary.passed_dialogues} ({summary.pass_rate}%)", "C4", "D4", "C5", "D5"),
            ("Не прошли порог", f"{summary.failed_dialogues}", "E4", "E4", "E5", "E5"),
            ("Средний балл качества", f"{summary.avg_score_percentage}%", "F4", "G4", "F5", "G5"),
        ]

        for title, val, t_start, t_end, v_start, v_end in kpi_metrics:
            if t_start != t_end:
                ws.merge_cells(f"{t_start}:{t_end}")
            if v_start != v_end:
                ws.merge_cells(f"{v_start}:{v_end}")

            cell_t = ws[t_start]
            cell_t.value = title
            cell_t.font = Font(name="Calibri", size=10, bold=True, color="595959")
            cell_t.alignment = Alignment(horizontal="center", vertical="center")
            cell_t.fill = PatternFill(start_color="F2F2F2", fill_type="solid")

            cell_v = ws[v_start]
            cell_v.value = val
            cell_v.font = Font(name="Calibri", size=14, bold=True, color=cls.COLOR_HEADER_BG)
            cell_v.alignment = Alignment(horizontal="center", vertical="center")
            cell_v.fill = PatternFill(start_color="E9EEF4", fill_type="solid")

        ws.row_dimensions[4].height = 20
        ws.row_dimensions[5].height = 30

        # Секция 1: Статистика по критериям чек-листа
        start_row = 7
        ws.merge_cells(f"A{start_row}:G{start_row}")
        sec1 = ws[f"A{start_row}"]
        sec1.value = "1. СТАТИСТИКА СОБЛЮДЕНИЯ КРИТЕРИЕВ ЧЕК-ЛИСТА"
        sec1.font = Font(name="Calibri", size=12, bold=True, color=cls.COLOR_HEADER_BG)
        sec1.fill = PatternFill(start_color=cls.COLOR_SECTION_BG, fill_type="solid")
        ws.row_dimensions[start_row].height = 25

        headers_criteria = ["ID критерия", "Наименование критерия", "Вес", "Макс. балл", "Средний балл", "Выполнение %", "Оценка качества"]
        cur_row = start_row + 1
        ws.row_dimensions[cur_row].height = 22

        for col_idx, h in enumerate(headers_criteria, 1):
            cell = ws.cell(row=cur_row, column=col_idx, value=h)
            cell.font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
            cell.fill = PatternFill(start_color=cls.COLOR_ACCENT, fill_type="solid")
            cell.alignment = Alignment(horizontal="center", vertical="center")

        for c in summary.criteria_stats:
            cur_row += 1
            ws.row_dimensions[cur_row].height = 20

            status_str = "Отлично" if c.avg_percentage >= 80 else ("В норме" if c.avg_percentage >= 65 else "Требует внимания")
            status_color = cls.COLOR_PASS_TEXT if c.avg_percentage >= 70 else cls.COLOR_FAIL_TEXT

            row_data = [c.criterion_id, c.criterion_name, c.weight, c.max_score, c.avg_score, f"{c.avg_percentage}%", status_str]
            for col_idx, val in enumerate(row_data, 1):
                cell = ws.cell(row=cur_row, column=col_idx, value=val)
                cell.border = thin_border
                align = "center" if col_idx in [1, 3, 4, 5, 6, 7] else "left"
                cell.alignment = Alignment(horizontal=align, vertical="center")
                cell.font = Font(name="Calibri", size=10)
                if col_idx == 7:
                    cell.font = Font(name="Calibri", size=10, bold=True, color=status_color)

        # Секция 2: Аналитическое резюме и выводы модели
        cur_row += 2
        ws.merge_cells(f"A{cur_row}:G{cur_row}")
        sec2 = ws[f"A{cur_row}"]
        sec2.value = "2. АНАЛИТИЧЕСКОЕ ЗАКЛЮЧЕНИЕ И РЕКОМЕНДАЦИИ РУКОВОДСТВУ"
        sec2.font = Font(name="Calibri", size=12, bold=True, color=cls.COLOR_HEADER_BG)
        sec2.fill = PatternFill(start_color=cls.COLOR_SECTION_BG, fill_type="solid")
        ws.row_dimensions[cur_row].height = 25

        # Общий вывод
        cur_row += 1
        ws.merge_cells(f"A{cur_row}:G{cur_row}")
        lbl_concl = ws[f"A{cur_row}"]
        lbl_concl.value = "Общий вывод:"
        lbl_concl.font = Font(name="Calibri", size=10, bold=True)
        cur_row += 1
        ws.merge_cells(f"A{cur_row}:G{cur_row}")
        concl_val = ws[f"A{cur_row}"]
        concl_val.value = summary.overall_conclusion
        concl_val.alignment = Alignment(wrap_text=True, vertical="top")
        concl_val.font = Font(name="Calibri", size=10, italic=True)
        ws.row_dimensions[cur_row].height = 50

        # Сильные стороны
        cur_row += 1
        ws.merge_cells(f"A{cur_row}:G{cur_row}")
        lbl_str = ws[f"A{cur_row}"]
        lbl_str.value = "Ключевые сильные стороны:"
        lbl_str.font = Font(name="Calibri", size=10, bold=True, color=cls.COLOR_PASS_TEXT)
        for s in summary.strengths:
            cur_row += 1
            ws.merge_cells(f"A{cur_row}:G{cur_row}")
            c_str = ws[f"A{cur_row}"]
            c_str.value = f"  • {s}"
            c_str.alignment = Alignment(wrap_text=True, vertical="center")
            c_str.font = Font(name="Calibri", size=10)

        # Системные ошибки
        cur_row += 1
        ws.merge_cells(f"A{cur_row}:G{cur_row}")
        lbl_weak = ws[f"A{cur_row}"]
        lbl_weak.value = "Системные зоны роста и ошибки:"
        lbl_weak.font = Font(name="Calibri", size=10, bold=True, color=cls.COLOR_FAIL_TEXT)
        for w in summary.systemic_mistakes:
            cur_row += 1
            ws.merge_cells(f"A{cur_row}:G{cur_row}")
            c_w = ws[f"A{cur_row}"]
            c_w.value = f"  • {w}"
            c_w.alignment = Alignment(wrap_text=True, vertical="center")
            c_w.font = Font(name="Calibri", size=10)

        # Рекомендации
        cur_row += 1
        ws.merge_cells(f"A{cur_row}:G{cur_row}")
        lbl_rec = ws[f"A{cur_row}"]
        lbl_rec.value = "Управленческие рекомендации:"
        lbl_rec.font = Font(name="Calibri", size=10, bold=True, color=cls.COLOR_HEADER_BG)
        for r in summary.management_recommendations:
            cur_row += 1
            ws.merge_cells(f"A{cur_row}:G{cur_row}")
            c_r = ws[f"A{cur_row}"]
            c_r.value = f"  • {r}"
            c_r.alignment = Alignment(wrap_text=True, vertical="center")
            c_r.font = Font(name="Calibri", size=10)

        # Ширина колонок
        col_widths = {"A": 16, "B": 35, "C": 10, "D": 12, "E": 14, "F": 15, "G": 20}
        for col_l, width in col_widths.items():
            ws.column_dimensions[col_l].width = width

    @classmethod
    def _build_details_sheet(cls, ws, evaluations: List[DialogueEvaluation], config: Dict[str, Any]):
        ws.views.sheetView[0].showGridLines = True
        thin_border = cls._get_borders()

        checklist = config.get("checklist", [])

        # Формируем динамические заголовки
        headers = [
            "ID диалога",
            "Статус",
            "Оценка (%)",
            "Балл / Макс",
            "Краткое содержание диалога",
        ]

        # Для каждого критерия добавляем колонку балла и колонку обоснования/цитаты
        for item in checklist:
            headers.append(f"[{item['id']}] Балл")
            headers.append(f"[{item['id']}] Комментарий и Цитата")

        headers.extend([
            "Общий комментарий к диалогу",
            "Рекомендация менеджеру",
            "Исходный транскрипт"
        ])

        # Запись строки заголовков
        ws.row_dimensions[1].height = 28
        for col_idx, h_text in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_idx, value=h_text)
            cell.font = Font(name="Calibri", size=10, bold=True, color=cls.COLOR_HEADER_TEXT)
            cell.fill = PatternFill(start_color=cls.COLOR_HEADER_BG, fill_type="solid")
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        # Запись данных по каждому диалогу
        for row_idx, ev in enumerate(evaluations, 2):
            ws.row_dimensions[row_idx].height = 45
            is_zebra = (row_idx % 2 == 0)
            base_fill = PatternFill(start_color=cls.COLOR_ZEBRA if is_zebra else "FFFFFF", fill_type="solid")

            row_values = [
                ev.dialogue_id,
                "ПРОЙДЕН" if ev.is_passed else "НЕ ПРОЙДЕН",
                f"{ev.score_percentage}%",
                f"{ev.total_score} / {ev.max_possible_score}",
                ev.summary,
            ]

            # Создаем быстрый словарь критериев диалога
            c_dict = {c.criterion_id: c for c in ev.criteria}
            for item in checklist:
                c_id = item["id"]
                c_eval = c_dict.get(c_id)
                if c_eval:
                    row_values.append(f"{c_eval.score}/{c_eval.max_score}")
                    comm = c_eval.comment
                    if c_eval.quote:
                        comm += f' (Цитата: "{c_eval.quote}")'
                    row_values.append(comm)
                else:
                    row_values.append("-")
                    row_values.append("-")

            row_values.extend([
                ev.overall_comment,
                ev.recommendation,
                ev.dialogue_text
            ])

            for col_idx, val in enumerate(row_values, 1):
                cell = ws.cell(row=row_idx, column=col_idx, value=val)
                cell.border = thin_border
                cell.fill = base_fill
                cell.font = Font(name="Calibri", size=9)

                # Выравнивание
                if col_idx in [1, 2, 3, 4] or (col_idx > 5 and (col_idx - 5) % 2 == 1 and col_idx <= 5 + len(checklist) * 2):
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                else:
                    cell.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)

                # Выделение статуса Пройден / Не пройден
                if col_idx == 2:
                    if ev.is_passed:
                        cell.fill = PatternFill(start_color=cls.COLOR_PASS_BG, fill_type="solid")
                        cell.font = Font(name="Calibri", size=9, bold=True, color=cls.COLOR_PASS_TEXT)
                    else:
                        cell.fill = PatternFill(start_color=cls.COLOR_FAIL_BG, fill_type="solid")
                        cell.font = Font(name="Calibri", size=9, bold=True, color=cls.COLOR_FAIL_TEXT)

        # Автонастройка ширины колонок
        for col_idx in range(1, len(headers) + 1):
            col_letter = get_column_letter(col_idx)
            header_name = headers[col_idx - 1]
            if "ID" in header_name:
                ws.column_dimensions[col_letter].width = 16
            elif "Статус" in header_name:
                ws.column_dimensions[col_letter].width = 15
            elif "Оценка" in header_name or "Балл" in header_name:
                ws.column_dimensions[col_letter].width = 14
            elif "Комментарий" in header_name or "содержание" in header_name:
                ws.column_dimensions[col_letter].width = 38
            elif "транскрипт" in header_name.lower():
                ws.column_dimensions[col_letter].width = 45
            else:
                ws.column_dimensions[col_letter].width = 25

        # Закрепление верхней строки
        ws.freeze_panes = "B2"
