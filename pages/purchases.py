import streamlit as st
import os
import io
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import google.generativeai as genai

# --- НАСТРОЙКИ ---
GEMINI_KEY = st.secrets["GEMINI_API_KEY"]
FOLDER_ID = st.secrets["FOLDER_ID"]
CREDS_FILE = "google_creds.json" # Файл ключа от Google Service Account

# Инициализируем Gemini
genai.configure(api_key=GEMINI_KEY)

# --- ФУНКЦИЯ ПОДКЛЮЧЕНИЯ К ГУГЛ ДИСКУ ---
def get_drive_service():
    try:
        # Берем настройки напрямую из секретов Streamlit
        creds_dict = dict(st.secrets["google_creds"])
        # Исправляем возможные проблемы с переносом строк в ключе
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        
        creds = Credentials.from_service_account_info(
            creds_dict, 
            scopes=['https://www.googleapis.com/auth/drive.readonly']
        )
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"Ошибка авторизации Google через Secrets: {e}")
        return None

# --- ПОИСК И ЗАКУПКА ЧЕРЕЗ ИИ ---
def analyze_invoices_with_ai(service, wine_name):
    try:
        # 1. Получаем список всех файлов в папке Гугл Диска
        query = f"'{FOLDER_ID}' in parents and trashed = false"
        results = service.files().list(q=query, fields="files(id, name, mimeType, webViewLink)").execute()
        files = results.get('files', [])
        
        if not files:
            return "📁 В указанной папке на Google Drive нет файлов.", []
            
        st.info(f"🔍 Проверяю документы на диске (всего файлов: {len(files)})...")
        
        # Запускаем модель Gemini Flash (она идеально подходит для работы с текстом и фото)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        found_records = []
        source_files = []
        
        # 2. Проходим по каждому файлу
        for f in files:
            # Скачиваем файл в память приложения
            request = service.files().get_media(fileId=f['id'])
            file_stream = io.BytesIO()
            downloader = MediaIoBaseDownload(file_stream, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            
            file_bytes = file_stream.getvalue()
            
            # Формируем запрос для Gemini
            prompt = f"""
            Ты — профессиональный бухгалтер-аналитик в винной сфере. 
            Твоя задача — найти в прикрепленном документе упоминание товара: "{wine_name}".
            Если товар найден, выпиши строго по пунктам:
            1. Дата закупки (или дата счета)
            2. Поставщик
            3. Количество закупленного товара
            4. Цена за одну бутылку (закупочная стоимость)
            
            Если этого товара в документе нет, ответь одной фразой: "Товар не найден".
            """
            
            # Передаем файл в Gemini в зависимости от формата
            try:
                response = model.generate_content([
                    prompt,
                    {"mime_type": f['mimeType'], "data": file_bytes}
                ])
                
                answer = response.text
                if "Товар не найден" not in answer:
                    found_records.append(f"📄 **Файл: {f['name']}**\n{answer}")
                    source_files.append({"name": f['name'], "link": f['webViewLink']})
            except Exception as e:
                # Если файл слишком тяжелый или формат не поддерживается, пропускаем его
                continue
                
        if found_records:
            full_report = "\n\n---\n\n".join(found_records)
            return full_report, source_files
        else:
            return f"❌ Ни в одном документе упоминаний вина «{wine_name}» не обнаружено.", []
            
    except Exception as e:
        return f"🔴 Ошибка при работе с диском или ИИ: {e}", []

# --- ИНТЕРФЕЙС СТРАНИЦЫ ---
st.title("🔎 Поиск закупочных цен по счетам (Gemini AI)")
st.write("Пиши название вина, а искусственный интеллект сам просмотрит все PDF, сканы и фото на Google Диске.")

wine_query = st.text_input("Введите название вина для поиска (например: Розе, Шато):", "")

if st.button("🚀 Найти в документах", type="primary"):
    if not wine_query:
        st.warning("Введите название товара!")
    else:
        drive_service = get_drive_service()
        if drive_service:
            with st.spinner("ИИ анализирует накладные... Это может занять около минуты."):
                report, links = analyze_invoices_with_ai(drive_service, wine_query)
                
                st.subheader("📊 Результаты анализа:")
                st.markdown(report)
                
                if links:
                    st.subheader("🔗 Ссылки на оригиналы документов:")
                    for l in links:
                        st.markdown(f"[{l['name']}]({l['link']})")
