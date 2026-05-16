import streamlit as st
import io
import json
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import google.generativeai as genai

# Инициализируем ИИ (используем стабильную и быструю модель Flash)
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

# Кэшируем загрузку данных с Диска, чтобы не качать файлы при каждом клике
@st.cache_data(ttl=600)  # Кэш на 10 минут
def load_all_invoices_text(folder_id):
    service = get_drive_service()
    if not service:
        return ""
    
    try:
        # Ищем все файлы в указанной папке (PDF, Excel, TXT и т.д.)
        query = f"'{folder_id}' in parents and trashed = false"
        results = service.files().list(q=query, fields="files(id, name, mimeType)").execute()
        items = results.get('files', [])
        
        if not items:
            st.warning("В указанной папке Google Диска не найдено файлов!")
            return ""
            
        all_text_content = []
        progress_bar = st.progress(0)
        st.info(f"Начался сбор накладных из Диска... Найдено файлов: {len(items)}")
        
        for idx, item in enumerate(items):
            file_id = item['id']
            file_name = item['name']
            
            # Скачиваем файл в память
            request = service.files().get_media(fileId=file_id)
            file_stream = io.BytesIO()
            downloader = MediaIoBaseDownload(file_stream, request)
            done = False
            while done is False:
                status, done = downloader.next_chunk()
                
            file_stream.seek(0)
            
            # Читаем как текст (для простоты структуры, ИИ отлично понимает сырые данные)
            # Если файлы бинарные (PDF/XLSX), Google Drive API умеет их конвертировать,
            # но пока заберем текстовую составляющую или метаданные.
            try:
                text_data = file_stream.read().decode('utf-8', errors='ignore')
            except:
                text_data = f"[Файл: {file_name} (бинарные данные)]"
                
            all_text_content.append(f"=== НАЧАЛО НАКЛАДНОЙ: {file_name} ===\n{text_data}\n=== КОНЕЦ НАКЛАДНОЙ ===")
            progress_bar.progress((idx + 1) / len(items))
            
        return "\n\n".join(all_text_content)
    except Exception as e:
        st.error(f"Ошибка при сборе накладных: {e}")
        return ""

def analyze_prices_with_ai(products_list, invoices_text):
    if not invoices_text:
        st.error("Текст накладных пуст. Нечего анализировать.")
        return None
        
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    prompt = f"""
    Ты — профессиональный аудитор и менеджер по закупкам в винотеке. 
    Твоя задача — найти закупочные цены для списка товаров из предоставленных текстов накладных.
    
    Используй гибкий интеллектуальный поиск: названия могут немного отличаться (русс/англ, сокращения, объемы 0.7 и 0.75л). 
    Если товар найден, бери самую свежую (последнюю по дате или тексту) цену.

    СПИСОК ТОВАРОВ ДЛЯ ПОИСКА:
    {products_list}

    ТЕКСТ НАКЛАДНЫХ С ДИСКА:
    {invoices_text}

    Выдай ответ СТРОГО в формате JSON-массива объектов, без markdown-разметки (без ```json), чтобы код мог его прочитать.
    Формат ответа:
    [
      {{"product": "Название из твоего списка", "found_name": "Название из накладной", "price": 1500.0, "invoice": "имя_файла.txt", "status": "Найдено"}},
      {{"product": "Название 2", "found_name": "-", "price": 0.0, "invoice": "-", "status": "Не найдено"}}
    ]
    """
    
    try:
        response = model.generate_content(prompt)
        # Чистим ответ от случайных кавычек ИИ
        clean_text = response.text.strip().replace("
```json", "").replace("```", "")
        return json.loads(clean_text)
    except Exception as e:
        st.error(f"Ошибка ИИ-анализа: {e}")
        return None

# --- ИНТЕРФЕЙС СТРИМЛИТА ---
st.title("📊 Интеллектуальный анализ закупочных цен")

# Сюда вставляешь ID папки со своего Гугл Диска (из ссылки)
FOLDER_ID = st.text_input("ID папки Google Диска со счетами:", value="ВСТАВЬ_СЮДА_ID_ПАПКИ")

# Поле для ввода списка товаров
products_input = st.text_area(
    "Введите список товаров для проверки (каждый товар с новой строки):",
    value="Виски Macallan 12\nВодка Белуга\nВино Шато Марго",
    height=200
)

if st.button("Запустить мега-поиск цен"):
    if FOLDER_ID == "ВСТАВЬ_СЮДА_ID_ПАПКИ" or not FOLDER_ID:
        st.warning("Пожалуйста, введите реальный ID папки Диска.")
    else:
        # Шаг 1: Быстро качаем всё в память один раз
        with st.spinner("Скачиваем и индексируем накладные..."):
            invoices_database = load_all_invoices_text(FOLDER_ID)
            
        if invoices_database:
            # Шаг 2: Отдаем ИИ массив данных на массовый разбор
            with st.spinner("ИИ сопоставляет позиции и ищет цены..."):
                results = analyze_prices_with_ai(products_input, invoices_database)
                
            if results:
                st.success("Анализ завершен!")
                # Выводим красивую итоговую таблицу
                st.table(results)
