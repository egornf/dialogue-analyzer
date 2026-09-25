"""
Интерактивный веб-интерфейс для анализа диалогов на базе Streamlit.
Запуск:
  streamlit run app.py
"""

import json
import tempfile
from pathlib import Path
import streamlit as st
import pandas as pd

from dialog_parser import DialogueParser
from llm_client import LocalLLMClient
from evaluator import DialogueEvaluator
from aggregator import DialogueAggregator
from excel_exporter import ExcelExporter
from generate_sample_data import generate_sample_file

st.set_page_config(
    page_title="Анализ разговоров | Локальная LLM",
    page_icon="🎙️",
    layout="wide"
)

# Стилизация
st.markdown("""
<style>
    .metric-card {
        background-color: #f8f9fa;
        border-radius: 10px;
        padding: 15px;
        border-left: 5px solid #1F4E79;
        box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    }
</style>
""", unsafe_allow_html=True)

# Загрузка базовой конфигурации
CONFIG_PATH = Path("config.json")
if CONFIG_PATH.exists():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        default_config = json.load(f)
else:
    default_config = {"llm": {}, "checklist": [], "passing_score_percentage": 70.0}

st.title("🎙️ Локальный анализ разговоров из Excel с помощью LLM")
st.caption("Автономный ОКК (контроль качества): построчная оценка транскриптов по чек-листу и агрегированная сводка.")

# Боковая панель с настройками
with st.sidebar:
    st.header("⚙️ Настройки LLM")
    provider = st.selectbox("Провайдер", ["ollama", "openai"], index=0, help="Ollama или OpenAI-совместимый (LM Studio, vLLM)")
    default_url = "http://localhost:11434" if provider == "ollama" else "http://localhost:1234/v1"
    base_url = st.text_input("URL сервера", value=default_url)
    model = st.text_input("Модель", value="qwen2.5:7b", help="Например: qwen2.5:7b, llama3.1:8b, mistral:7b")
    temperature = st.slider("Температура (креативность)", 0.0, 1.0, 0.1, 0.05)
    
    use_mock = st.checkbox("Режим демонстрации (Mock)", value=False, help="Позволяет протестировать весь пайплайн и формирование Excel без запуска локальной LLM")
    
    st.divider()
    st.header("📋 Чек-лист оценки")
    passing_pct = st.number_input("Порог сдачи (%)", min_value=1.0, max_value=100.0, value=float(default_config.get("passing_score_percentage", 70.0)))
    
    checklist_data = default_config.get("checklist", [])
    st.write(f"Активных критериев в чек-листе: **{len(checklist_data)}**")
    
    with st.expander("👀 Посмотреть текущие критерии"):
        for c in checklist_data:
            st.markdown(f"• **{c['name']}** (макс. {c.get('max_score', 10)} б., вес {c.get('weight', 1.0)})  \n  _{c.get('description', '')}_")

    with st.expander("✏️ Редактировать чек-лист (JSON)"):
        st.caption("Вы можете изменить названия, описания или добавить новые критерии:")
        checklist_raw = st.text_area(
            "Список критериев в формате JSON:",
            value=json.dumps(checklist_data, ensure_ascii=False, indent=2),
            height=260
        )
        if st.button("💾 Сохранить новый чек-лист"):
            try:
                parsed_checklist = json.loads(checklist_raw)
                default_config["checklist"] = parsed_checklist
                default_config["passing_score_percentage"] = passing_pct
                with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                    json.dump(default_config, f, ensure_ascii=False, indent=2)
                st.success("Чек-лист успешно сохранен в config.json!")
                st.rerun()
            except Exception as e:
                st.error(f"Ошибка сохранения: {e}")

# Основная область
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1. Загрузка файла диалогов")
    uploaded_file = st.file_uploader("Загрузите Excel (.xlsx)", type=["xlsx", "xls"])
    
    if st.button("Использовать демонстрационный файл с примерами"):
        sample_path = Path("sample_dialogs.xlsx")
        if not sample_path.exists():
            generate_sample_file(str(sample_path))
        with open(sample_path, "rb") as f:
            uploaded_file = f.read()
            st.session_state["sample_bytes"] = uploaded_file

with col2:
    st.subheader("2. Статус подключения")
    test_client = LocalLLMClient(
        provider=provider,
        base_url=base_url,
        model=model,
        temperature=temperature,
        is_mock=use_mock
    )
    conn = test_client.check_connection()
    if conn["status"] == "ok":
        st.success(f"Подключение готово: {conn.get('message', 'Сервер LLM доступен')}")
    else:
        st.warning(conn.get("message", "Нет связи с локальным сервером"))

# Обработка данных
raw_bytes = uploaded_file if isinstance(uploaded_file, bytes) else (uploaded_file.getvalue() if uploaded_file else st.session_state.get("sample_bytes"))

if raw_bytes:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp_in:
        tmp_in.write(raw_bytes)
        tmp_in_path = tmp_in.name

    dialogues = DialogueParser.parse_excel(tmp_in_path)
    st.info(f"Обнаружено диалогов в файле: **{len(dialogues)}**")

    # Превью диалогов
    with st.expander("Предпросмотр загруженных разговоров"):
        preview_data = [{"ID": d.dialogue_id, "Длина (симв.)": len(d.text), "Превью текста": d.text[:120] + "..."} for d in dialogues]
        st.dataframe(pd.DataFrame(preview_data), use_container_width=True)

    if st.button("🚀 Запустить анализ диалогов", type="primary"):
        prog_bar = st.progress(0, text="Инициализация анализа...")
        client = LocalLLMClient(
            provider=provider,
            base_url=base_url,
            model=model,
            temperature=temperature,
            is_mock=use_mock
        )
        evaluator = DialogueEvaluator(llm_client=client, config=default_config)
        
        evaluations = []
        for idx, d in enumerate(dialogues):
            prog_bar.progress((idx + 1) / len(dialogues), text=f"Анализ диалога {idx+1}/{len(dialogues)}: {d.dialogue_id}")
            ev = evaluator.evaluate_dialogue(d)
            evaluations.append(ev)

        prog_bar.progress(1.0, text="Формирование сводного отчета и агрегация...")
        aggregator = DialogueAggregator(llm_client=client)
        summary = aggregator.aggregate(evaluations)

        # Экспорт в Excel
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp_out:
            tmp_out_path = tmp_out.name
        ExcelExporter.export(evaluations, summary, tmp_out_path)

        st.success("🎉 Анализ успешно завершен!")

        # Отображение результатов
        st.divider()
        st.header("📊 Сводные результаты")
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Всего звонков", summary.total_dialogues)
        m2.metric("Успешных (Сдано)", f"{summary.passed_dialogues} ({summary.pass_rate}%)")
        m3.metric("Средний балл", f"{summary.avg_score_percentage}%")
        m4.metric("Сильный навык", summary.strongest_criterion)

        st.subheader("💡 Аналитическое заключение")
        st.info(summary.overall_conclusion)

        c_left, c_right = st.columns(2)
        with c_left:
            st.markdown("### 🏆 Сильные стороны")
            for s in summary.strengths:
                st.markdown(f"- {s}")
        with c_right:
            st.markdown("### ⚠️ Системные ошибки")
            for m in summary.systemic_mistakes:
                st.markdown(f"- {m}")

        st.markdown("### 📌 Управленческие рекомендации")
        for r in summary.management_recommendations:
            st.markdown(f"✔ **{r}**")

        st.divider()
        # Кнопка скачивания Excel
        with open(tmp_out_path, "rb") as f_res:
            st.download_button(
                label="📥 Скачать итоговый отчет в Excel (.xlsx)",
                data=f_res.read(),
                file_name="dialogue_analysis_report.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary"
            )
