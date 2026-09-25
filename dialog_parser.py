"""
Модуль парсинга и сегментации исходного Excel-файла с транскриптами диалогов.
Поддерживает форматы:
1. Построчный (1 строка = 1 диалог) с колонками ID и Текст.
2. Репликовый (1 строка = 1 реплика с ID диалога, Спикером и Текстом).
3. Универсальный fallback с автоопределением колонок.
"""

from dataclasses import dataclass
from typing import List, Optional, Dict, Any
import pandas as pd
from pathlib import Path


@dataclass
class DialogueItem:
    dialogue_id: str
    text: str
    metadata: Dict[str, Any]


class DialogueParser:
    ID_CANDIDATES = [
        "id", "dialog_id", "dialogue_id", "call_id", "номер", "номер_звонка",
        "ид", "ид_диалога", "ид_звонка", "идентификатор", "conversation_id"
    ]
    TEXT_CANDIDATES = [
        "text", "transcript", "dialogue", "dialog", "conversation", "разговор",
        "диалог", "транскрипт", "текст", "содержание", "реплика", "сообщение"
    ]
    SPEAKER_CANDIDATES = [
        "speaker", "role", "caller", "спикер", "роль", "собеседник", "автор", "сторона"
    ]

    @staticmethod
    def _find_matching_column(columns: List[str], candidates: List[str]) -> Optional[str]:
        col_map = {str(c).strip().lower(): c for c in columns}
        for cand in candidates:
            if cand in col_map:
                return col_map[cand]
        # Partial match
        for cand in candidates:
            for clean_name, orig_name in col_map.items():
                if cand in clean_name:
                    return orig_name
        return None

    @classmethod
    def parse_excel(cls, file_path: str | Path, sheet_name: Optional[str] = None) -> List[DialogueItem]:
        """
        Загружает и сегментирует Excel файл в список объектов DialogueItem.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Файл не найден: {file_path}")

        # Считываем данные
        df = pd.read_excel(path, sheet_name=sheet_name if sheet_name else 0)
        if df.empty:
            raise ValueError(f"Excel-файл {file_path} пуст.")

        # Очищаем заголовки
        df.columns = [str(c).strip() for c in df.columns]

        id_col = cls._find_matching_column(list(df.columns), cls.ID_CANDIDATES)
        text_col = cls._find_matching_column(list(df.columns), cls.TEXT_CANDIDATES)
        speaker_col = cls._find_matching_column(list(df.columns), cls.SPEAKER_CANDIDATES)

        # Если колонку с текстом не нашли по имени, берем колонку с максимальной средней длиной строк
        if not text_col:
            str_cols = df.select_dtypes(include=["object", "string"]).columns
            if len(str_cols) > 0:
                text_col = max(str_cols, key=lambda c: df[c].astype(str).str.len().mean())
            else:
                text_col = df.columns[0]

        dialogues: List[DialogueItem] = []

        # Проверяем, сгруппирован ли файл по репликам
        if id_col and (df[id_col].duplicated().any() or speaker_col):
            # Формат: несколько строк на один диалог
            grouped = df.groupby(id_col, sort=False)
            for d_id, group in grouped:
                transcript_lines = []
                for _, row in group.iterrows():
                    speaker_prefix = ""
                    if speaker_col and pd.notna(row.get(speaker_col)):
                        speaker_prefix = f"[{row[speaker_col]}]: "
                    line_text = str(row[text_col]).strip() if pd.notna(row.get(text_col)) else ""
                    if line_text:
                        transcript_lines.append(f"{speaker_prefix}{line_text}")

                full_text = "\n".join(transcript_lines)
                meta = {
                    c: group.iloc[0][c] for c in group.columns 
                    if c not in [id_col, text_col, speaker_col] and pd.notna(group.iloc[0][c])
                }
                meta["lines_count"] = len(transcript_lines)
                dialogues.append(DialogueItem(dialogue_id=str(d_id), text=full_text, metadata=meta))
        else:
            # Формат: 1 строка = 1 диалог
            for idx, row in df.iterrows():
                if id_col and pd.notna(row.get(id_col)):
                    d_id = str(row[id_col]).strip()
                else:
                    d_id = f"Диалог #{idx + 1}"

                text_content = str(row[text_col]).strip() if pd.notna(row.get(text_col)) else ""
                if not text_content or text_content.lower() == "nan":
                    continue

                meta = {
                    c: row[c] for c in df.columns 
                    if c not in [id_col, text_col] and pd.notna(row[c])
                }
                dialogues.append(DialogueItem(dialogue_id=d_id, text=text_content, metadata=meta))

        return dialogues
