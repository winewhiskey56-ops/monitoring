import streamlit as st
import io
import json
import pandas as pd
from pypdf import PdfReader
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import google.generativeai as genai

st.title("🔍 Быстрый поиск закупочной цены")

if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
else:
    st.error("В Secrets не найден GEMINI_API_KEY!")

FOLDER_ID = st.secrets.get("google_folder_id") or st.secrets.get("folder_id")

if not FOLDER_ID:
    st.error("Ошибка: В st.secrets не найден ID папки")

# --- МАГИЯ СКОРОСТИ: КЭШИРОВАНИЕ ЗАГРУЗКИ И ПАРСИНГА ДОКУМЕНТОВ ---
# Данные сохраняются в памяти на 1 час (3600 секунд)
@st.cache_data(ttl=3600, show_spinner="Полное сканирование Google Диска... Это происходит ОДИН РАЗ, затем поиск будет мгновенным.")
def load_and_parse_all_invoices(folder_id, gcp_secrets):
    creds = Credentials.from_service_account_info(dict(gcp_secrets), scopes=['https://www.googleapis.com/auth/drive.readonly'])
    service = build('drive', 'v3', credentials=creds)
    
    query = f"'{folder_id}' in parents and trashed = false"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    items = results.get('files', [])
    
    parsed_documents = []
    
    if not items:
        return parsed_documents

    for item in items:
        f_id = item['id']
        f_name = item['name']
        
        try:
            request = service.files().get_media(fileId=f_id)
            file_stream = io.BytesIO()
            downloader = MediaIoBaseDownload(file_stream, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
                
            file_bytes = file_stream.getvalue()
            lower_name = f_name.lower()
            text_content = ""
            
            if lower_name.endswith('.xlsx') or lower_name.endswith('.xls'):
                df_dict = pd.read_excel(io.BytesIO(file_bytes), sheet_name=None)
                sheets_text = []
                for df in df_dict.values():
                    sheets_text.append(df.to_string(index=False))
                text_content = "\n".join(sheets_text)
            elif lower_name.endswith('.pdf'):
                reader = PdfReader(io.BytesIO(file_bytes))
                pdf_text = []
                for page in reader.pages:
                    if page.extract_text():
                        pdf_text.append(page.extract_text())
                text_content = "\n".join(pdf_text)
            else:
                text_content = file_bytes.decode('utf-8', errors='ignore')
                
            if text_content.strip():
                parsed_documents.append({"name": f_name, "text": text_content})
        except Exception:
            continue # Пропускаем битые файлы
            
    return parsed_documents

# Кнопка для ручного сброса кэша (если залил свежую накладную и хочешь увидеть её сразу)
if st.sidebar.button("🔄 Обновить базу накладных (сбросить кэш)"):
    st.cache_data.clear()
    st.sidebar.success("Кэш очищен! Следующий поиск обновит данные с Диска.")

product_search = st.text_input("Введите название товара для проверки цены:")

if st.button("Найти цену в накладных"):
    if not product_search:
        st.warning("Пожалуйста, введите название товара.")
    elif not FOLDER_ID:
        st.error("Невозможно запустить поиск без ID папки.")
    elif "gcp_service_account" not in st.secrets:
        st.error("В Secrets не найден блок [gcp_service_account]!")
    else:
        try:
            # Загружаем документы (быстро возьмутся из кэша, если уже скачивались)
            all_docs = load_and_parse_all_invoices(FOLDER_ID, st.secrets["gcp_service_account"])
            
            if not all_docs:
                st.warning("В вашей папке на Google Диске нет доступных файлов или не удалось их прочесть.")
            else:
                search_term = product_search.lower().strip()
                filtered_texts = []
                
                # Быстрый поиск совпадений по кэшированному тексту в памяти
                for doc in all_docs:
                    if search_term in doc["text"].lower():
                        filtered_texts.append(f"=== ФАЙЛ: {doc['name']} ===\n{doc['text']}\n")
                
                if not filtered_texts:
                    st.info(f"Совпадений по ключевому слову '{product_search}' не найдено ни в одном документе.")
                else:
                    full_invoices_text = "\n".join(filtered_texts)
                    with st.spinner(f"ИИ анализирует накладные со снайперской точностью ({len(filtered_texts)} шт.)..."):
                        model = genai.GenerativeModel(
                            'gemini-2.5-flash',
                            generation_config={"response_mime_type": "application/json"}
                        )
                        
                        prompt = "Ты менеджер базы данных винного магазина. Найди упоминания товара, его цену и дату документа.\n"
                        prompt += f"Искомый товар: {product_search}\n\n"
                        prompt += f"ТЕКСТЫ НАКЛАДНЫХ:\n{full_invoices_text}\n\n"
                        prompt += "ОБЯЗАТЕЛЬНО найди в тексте каждого документа дату его составления/проведения (обычно вверху накладной рядом с номером).\n"
                        prompt += "Если товар найден в нескольких файлах, выведи все упоминания (историю цен).\n"
                        prompt += "Ответь строго в формате JSON-массива объектов с ключами: product, found_name, price, date, invoice, status. В ключе date укажи найденную дату документа."
                        
                        response = model.generate_content(prompt)
                        clean_text = response.text.strip()
                        
                        result_data = json.loads(clean_text)
                        if result_data:
                            st.success(f"История цен по запросу: {product_search}")
                            
                            # Превращаем в датафрейм и красиво сортируем колонки
                            df_result = pd.DataFrame(result_data)
                            columns_order = ["product", "found_name", "price", "date", "invoice", "status"]
                            # На случай, если ИИ пропустил какую-то колонку
                            existing_columns = [col for col in columns_order if col in df_result.columns]
                            
                            st.dataframe(df_result[existing_columns], use_container_width=True)
                        else:
                            st.info("Позиция с таким названием не обнаружена в выбранных накладных.")
                            
        except Exception as top_err:
            st.error(f"Ошибка выполнения поиска: {top_err}")
