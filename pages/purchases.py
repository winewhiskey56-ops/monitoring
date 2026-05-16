import streamlit as st
import io
import json
import pandas as pd
from pypdf import PdfReader
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import google.generativeai as genai

# Инициализация ИИ Gemini
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
else:
    st.error("В Secrets не найден GEMINI_API_KEY!")

def get_drive_service():
    try:
        if "gcp_service_account" not in st.secrets:
            st.error("В настройках Secrets не найден блок [gcp_service_account]!")
            return None
        creds = Credentials.from_service_account_info(
            dict(st.secrets["gcp_service_account"]), 
            scopes=['https://www.googleapis.com/auth/drive.readonly']
        )
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"Ошибка авторизации Google: {e}")
        return None

# Функция для правильного извлечения текста из разных форматов файлов
def extract_text_from_bytes(file_bytes, file_name):
    lower_name = file_name.lower()
    try:
        # 1. Если это Excel (XLSX или XLS)
        if lower_name.endswith('.xlsx') or lower_name.endswith('.xls'):
            df_dict = pd.read_excel(io.BytesIO(file_bytes), sheet_name=None)
            excel_text = []
            for sheet, df in df_dict.items():
                excel_text.append(f"Лист: {sheet}\n" + df.to_string(index=False))
            return "\n".join(excel_text)
            
        # 2. Если это PDF
        elif lower_name.endswith('.pdf'):
            reader = PdfReader(io.BytesIO(file_bytes))
            pdf_text = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    pdf_text.append(text)
            return "\n".join(pdf_text)
            
        # 3. Если это обычный текст или CSV
        else:
            return file_bytes.decode('utf-8', errors='ignore')
    except Exception as e:
        return f"[Ошибка чтения содержимого файла {file_name}: {e}]"

# Кэшируем сбор данных с Диска на 10 минут
@st.cache_data(ttl=600)
def load_all_invoices_text(folder_id):
    service = get_drive_service()
    if not service:
        return ""
    
    try:
        query = f"'{folder_id}' in parents and trashed = false"
        results = service.files().list(q=query, fields="files(id, name, mimeType)").execute()
        items = results.get('files', [])
        
        if not items:
            st.warning("В указанной папке Google Диска не найдено файлов!")
            return ""
            
        all_text_content = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for idx, item in enumerate(items):
            file_id = item['id']
            file_name = item['name']
            status_text.info(f"Обработка файла ({idx+1}/{len(items)}): {file_name}")
            
            # Скачиваем файл с Диска в бинарный поток
            request = service.files().get_media(fileId=file_id)
            file_stream = io.BytesIO()
            downloader = MediaIoBaseDownload(file_stream, request)
            done = False
            while done is False:
                _, done = downloader.next_chunk()
                
            file_bytes = file_stream.getvalue()
            
            # Вытаскиваем нормальный текст в зависимости от расширения
            parsed_text = extract_text_from_bytes(file_bytes, file_name)
            
            all_text_content.append(f"=== НАЧАЛО НАКЛАДНОЙ: {file_name} ===\n{parsed_text}\n=== КОНЕЦ НАКЛАДНОЙ ===")
            progress_bar.progress((idx + 1) / len(items))
            
        status_text.success("Все накладные успешно загружены и обработаны!")
        return "\n\n".join(all_text_content)
    except Exception as e:
        st.error(f"Ошибка при сборе накладных с Диска: {e}")
        return ""

def analyze_prices_with_ai(products_list, invoices_text):
    if not invoices_text:
        st.error("База накладных пуста. Нечего анализировать.")
        return None
        
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    # Полностью безопасная сборка промпта БЕЗ f-строк, чтобы избежать SyntaxError
    prompt = (
        "Ты — профессиональный аудитор и эксперт по закупкам в винной индустрии.\n"
        "Твоя задача — сопоставить список запрашиваемых товаров с текстами накладных и найти их закупочные цены.\n\n"
        "ПРАВИЛА ПОИСКА:\n"
        "1. Используй умный контекстный поиск. Названия могут отличаться (например, 'Macallan 12 Y.O.' в списке и 'Макаллан Шато 12л 0.7' в накладной — это одно и то же).\n"
        "2. Игнорируй мелкие различия в дефисах, кавычках, регистрах букв и языках.\n"
        "3. Если один и тот же товар встречается в нескольких накладных, выведи строку с САМОЙ СВЕЖЕЙ ценой (ориентируйся по датам в названиях файлов или внутри текста).\n\n"
        "СПИСОК ТОВАРОВ ДЛЯ ПРОВЕРКИ:\n" + str(products_list) + "\n\n"
        "ТЕКСТЫ НАКЛАДНЫХ ДЛЯ АНАЛИЗА:\n" + str(invoices_text) + "\n\n"
        "ОТВЕТ ВЫДАЙ СТРОГО В ФОРМАТЕ JSON-массива (без слов ```json в начале). Структура ответа:\n"
        "[\n"
        "  {\"product\": \"Название из запроса\", \"found_name\": \"Название из накладной\", \"price\": 1500.0, \"invoice\": \"имя_файла.xlsx\", \"status\": \"Найдено\"}\n"
        "]"
    )
    
    try:
        response = model.generate_content(prompt)
        clean_text = response.text.strip().replace("
```json", "").replace("```", "")
        return json.loads(clean_text)
    except Exception as e:
        st.error(f"Ошибка парсинга ответа ИИ: {e}")
        if 'response' in locals():
            st.text_area("Сырой ответ ИИ для отладки:", value=response.text, height=150)
        return None

# --- ИНТЕРФЕЙС СТРИМЛИТА ---
st.title("📊 Умный экспресс-анализ закупочных цен")

FOLDER_ID = st.text_input("ID папки Google Диска со счетами (XLSX, PDF, TXT):", value="")

products_input = st.text_area(
    "Введите список позиций алкоголя (каждая с новой строки):",
    value="Виски Macallan 12\nВодка Белуга\nAperol Spritz",
    height=200
)

if st.button("Запустить сканирование цен"):
    if not FOLDER_ID:
        st.warning("Пожалуйста, введите ID папки Google Диска.")
    else:
        # 1. Загружаем и парсим все файлы (благодаря кэшу это сработает быстро при повторных кликах)
        invoices_database = load_all_invoices_text(FOLDER_ID)
            
        if invoices_database:
            # 2. Отправляем весь массив данных в Gemini за один заход
            with st.spinner("ИИ сопоставляет позиции и рассчитывает цены..."):
                results = analyze_prices_with_ai(products_input, invoices_database)
                
            if results:
                st.success("Массовый анализ успешно завершен!")
                # Переводим в DataFrame для красивого отображения таблицы в Streamlit
                st.dataframe(pd.DataFrame(results), use_container_width=True)
