import streamlit as st
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from thefuzz import fuzz
import time

# --- НАСТРОЙКИ ---
ORENBURG_LENTA_COOKIE = "orenburg"
ORENBURG_METRO_ID = "68"
MATCH_THRESHOLD = 75  # Процент схожести названий для признания совпадения

def get_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    try:
        # Для работы в Streamlit Cloud
        options.binary_location = "/usr/bin/chromium"
        service = Service("/usr/bin/chromedriver")
        driver = webdriver.Chrome(service=service, options=options)
    except:
        # Для локальной разработки
        from webdriver_manager.chrome import ChromeDriverManager
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    return driver

# --- ПАРСЕРЫ ---

def get_simplewine_items():
    """Собирает акционные позиции с первой страницы SimpleWine"""
    driver = get_driver()
    items = []
    try:
        driver.get("https://simplewine.ru/catalog/wine/filter/availability-is-y/apply/")
        time.sleep(5)
        cards = driver.find_elements(By.CSS_SELECTOR, ".product-card")
        
        for card in cards[:10]: # Берем первые 10 для теста скорости
            try:
                name = card.find_element(By.CSS_SELECTOR, ".product-card__name").text
                price_new = card.find_element(By.CSS_SELECTOR, ".product-card__price-current").text
                try:
                    price_old = card.find_element(By.CSS_SELECTOR, ".product-card__price-old").text
                except:
                    price_old = price_new
                
                items.append({
                    "name": name,
                    "simple_price": int(''.join(filter(str.isdigit, price_new))),
                    "simple_old": int(''.join(filter(str.isdigit, price_old)))
                })
            except: continue
    finally:
        driver.quit()
    return items

def search_competitor(wine_name, shop_url, price_selector, cookie_type=None):
    """Универсальный поиск по названию у конкурента"""
    driver = get_driver()
    try:
        if cookie_type == "lenta":
            driver.get("https://lenta.com/")
            driver.add_cookie({"name": "city", "value": ORENBURG_LENTA_COOKIE})
        elif cookie_type == "metro":
            driver.get("https://online.metro-cc.ru/")
            driver.add_cookie({"name": "metro_store_id", "value": ORENBURG_METRO_ID})

        driver.get(f"{shop_url}{wine_name}")
        time.sleep(4)
        
        # Берем первый найденный товар
        price_elem = driver.find_element(By.CSS_SELECTOR, price_selector)
        price_val = int(''.join(filter(str.isdigit, price_elem.text)))
        return price_val
    except:
        return None
    finally:
        driver.quit()

# --- ИНТЕРФЕЙС STREAMLIT ---

st.set_page_config(layout="wide", page_title="Wine Monitor Orenburg")
st.title("🍷 Мониторинг: SimpleWine vs Оренбург")

if st.button("🚀 Запустить полное сравнение"):
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # 1. Получаем базу от SimpleWine
    status_text.text("Сбор данных SimpleWine...")
    source_items = get_simplewine_items()
    progress_bar.progress(20)
    
    if not source_items:
        st.error("Не удалось получить данные SimpleWine. Проверьте соединение.")
    else:
        results = []
        total = len(source_items)
        
        for i, item in enumerate(source_items):
            status_text.text(f"Сравниваем ({i+1}/{total}): {item['name']}")
            
            # Поиск в Ленте
            lenta_price = search_competitor(item['name'], 
                                         "https://lenta.com/search/?searchText=", 
                                         ".price-label__integer", "lenta")
            
            # Поиск в Metro
            metro_price = search_competitor(item['name'], 
                                          "https://online.metro-cc.ru/search?q=", 
                                          ".product-unit-prices__actual-wrapper", "metro")
            
            # Логика скидки Simple
            discount = item['simple_old'] - item['simple_price']
            
            results.append({
                "Позиция": item['name'],
                "Simple: Цена (без скидки)": f"{item['simple_old']} ₽",
                "Simple: Скидка": f"{discount} ₽" if discount > 0 else "Нет",
                "Simple: Итоговая": f"{item['simple_price']} ₽",
                "Лента (Оренбург)": f"{lenta_price} ₽" if lenta_price else "—",
                "Metro (Оренбург)": f"{metro_price} ₽" if metro_price else "—"
            })
            progress_bar.progress(20 + int((i+1)/total * 80))

        # Вывод таблицы
        status_text.success("Анализ завершен!")
        df = pd.DataFrame(results)
        
        st.subheader("Сводная таблица цен")
        st.dataframe(df, use_container_width=True)
        
        # Экспорт
        csv = df.to_csv(index=False).encode('utf-8-sig')
        st.download_button("📥 Скачать отчет в CSV", csv, "wine_report_orenburg.csv", "text/csv")

st.info("Примечание: Парсинг занимает время из-за эмуляции поведения пользователя в Оренбурге для каждого магазина.")
