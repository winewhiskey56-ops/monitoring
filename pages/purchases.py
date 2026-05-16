import streamlit as st
import io
import json
import base64
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

def extract_text_from_bytes(file_bytes, file_name):
    lower_name = file_name.lower()
    try:
        if lower_name.endswith('.xlsx') or lower_name.endswith('.xls'):
            df_dict = pd.read_excel(io.BytesIO(file_bytes), sheet_name=None)
            excel_text = []
            for sheet, df in df_dict.items():
                excel_text.append(f"Лист: {sheet}\n" + df.to_string(index=False))
            return "\n".join(excel_text)
        elif lower_name.endswith('.pdf'):
            reader = PdfReader(io.BytesIO(file_bytes))
            pdf_text = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    pdf_text.append(text)
            return "\n".join(pdf_text)
        else:
            return file_bytes.decode('utf-8', errors='ignore')
    except Exception as e:
        return f"[Ошибка чтения файла {file_name}: {e}]"

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
            status_text.info(f"Загрузка файла ({idx+1}/{len(items)}): {file_name}")
            
            request = service.files().get_media(fileId=file_id)
            file_stream = io.BytesIO()
            downloader = MediaIoBaseDownload(file_stream, request)
            done = False
            while done is False:
                _, done = downloader.next_chunk()
                
            file_bytes = file_stream.getvalue()
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
    
    # Инструкция для ИИ зашифрована в Base64, чтобы обойти баг компилятора Python 3.14/Streamlit
    b64_instruction = (
        "VNGrID8g0L/RgNC+0YTQtdGB0YHQuNC+0L3QsNC70YzQvdGL0Lkg0LDRg9C00LjRgtC+0YAg0Lgg"
        "0Y3QutGB0L/QtdGA0YIg0L/QviDQt9Cw0LrRg9C/0LrQsNC8INCyINCy0LjQvdC90L7QuSDRgdGE"
        "0LXRgNC1Lg0K0KLQstC+0Y8g0LfQsNC00LDRh9CwINC0YHQvtC/0L7RgdGC0LDQstC40YLRjCDR"
        "gdC/0LjRgdC+0Log0LfQsNC/0YDQv9GI0LjQstCw0LXQvNGL0YUg0YLQvtCy0LDRgNC+0LIg0YHQ"
        "DRGC0LXQutGB0YLQsNC80Lgg0L3QsNC60LvQsNC00L3RvizRNSDQuCDQvdCw0LnRgtC4INC40YUg"
        "0LfQsNC60YPQv9C+0YfQvdGL0LUg0YbQtdC90YsuDQoNCtCf0KDQkNCS0JjQm9CQLgDQnCeCeCeQ"
        "0JjQodCf0J7Qm9Cs0JfQo9CZINCj0JzQndCr0Mkg0JrQntCd0KLQldCa0KHQotCd0CrQmSDQn9Ce"
        "0JjQodCaLiDQndCw0LfQstCw0L3QuNGPINC80L7Qs9GD0YIg0L7RgtC70LjRh9Cw0YLRjNGB0Y8g"
        "0L7RgiDRgdC/0LjRgdC60LAg0L3QsNGA0YPRgdGB0LrQvtC8INC40LvQuCDQsNC90LPQu9C40LnR"
        "gdC60L7QvCwg0L7QsdGK0LXQvNGLIDAuNyDQuCAwLjc1INC90L7RgdC40YLRjCDRgNCw0LfQvdGL"
        "0Lkg0YXRgNCw0LrRgtC10YAuINCh0L7Qv9C+0YHRgtCw0LLQu9GP0Lkg0LjRhSDRg9C80L3Qvi4N"
        "CjIuINCV0YHQu9C4INC+0LTQuNC9INC4INGC0L7RgiDQttC1INGC0LvtstCw0YAg0LLRgdGC0YDQ"
        "N9GH0LDQtdGC0YHRjyDQsiDQvdC10YHQutC+0LvRjNC60LDRhSDRgdC60LvQsNC00L3Ri9GFLCDQ"
        "stGL0LLQtdC00Lgg0YHRgtGA0L7QutGDINGBINGB0LDQvNC+0Lkg0YHQstC10LbQtdC5INGG0L5Q"
        "vdC+0LkuDQoNCtCe0KLQktCV0KLCDQktCr0JTQkNCZINCh0KLQoNCe0JPQniDQkiDQpNCe0KDQnN"
        "CQ0KLQniBKU09OLdC80LDRgdGB0LjQstCwINCx0LXQtyDRgdC70L7QsiBgYGBqc29uINC60LDQut"
        "C+0Lkt0LvQuNCx0L4g0YDQstC30LzQtdGC0LrQuC4g0KHRgtGA0YPQutGC0YPRgNCwINC+0YLR"
        "stC10YLQsDoNClsNClsgIHsicHJvZHVjdCI6ICLQndCw0LfQstCw0L3QuNC1INC40Lcg0LfQsNC/"
        "0YDQvtGB0LAiLCAiZm91bmRfbmFtZSI6ICLQndCw0LfQstCw0L3QuNC1INC40Lcg0L3QsNC60bDQ"
        "dNC90L7QuSIsICJwcmljZSI6IDE1MDAuMCwgImludm9pY2UiOiAiaW15YV9mYWlsYS54bHN4Iiwg"
        "InN0YXR1cyI6ICLQndCw0LnQtNC10L3QviJ9DQpd"
    )
    
    try:
        # Расшифровываем инструкцию перед отправкой в Gemini
        instruction = base64.b64decode(b64_instruction.encode('utf-8')).decode('utf-8', errors='ignore')
    except:
        instruction = "Найди цены для списка товаров в текстах накладных. Верни строго JSON массив."

    prompt = (
        instruction + "\n\n"
        "СПИСОК ТОВАРОВ ДЛЯ ПРОВЕРКИ:\n" + str(products_list) + "\n\n"
        "ТЕКСТЫ НАКЛАДНЫХ ДЛЯ АНАЛИЗА:\n" + str(invoices_text)
    )
    
    try:
        response = model.generate_content(prompt)
        clean_text = response.text.strip().replace("```json", "").replace("
```", "")
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
        invoices_database = load_all_invoices_text(FOLDER_ID)
            
        if invoices_database:
            with st.spinner("ИИ сопоставляет позиции и рассчитывает цены..."):
                results = analyze_prices_with_ai(products_input, invoices_database)
                
            if results:
                st.success("Массовый анализ успешно завершен!")
                st.dataframe(pd.DataFrame(results), use_container_width=True)
