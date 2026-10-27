# proxy_finder.py
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

PROXY_URL = "https://advanced.name/freeproxy/6adf909473849"


def get_all_proxies(url=PROXY_URL):
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")

    driver = webdriver.Chrome(options=opts)
    try:
        driver.get(url)
        time.sleep(2)
        text = driver.find_element(By.XPATH, "/html/body/pre").text
        proxies = [p.strip() for p in text.strip().split("\n") if p.strip()]
        print(f" Получено адресов: {len(proxies)}")
        return proxies
    except Exception as e:
        print(f"Не удалось скачать список: {e}")
        return []
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def clean_list(proxies, limit=100, timeout=2):
    #Проверяю прокси через Chrome, возвращаю рабочие
    print(f" К проверке: {min(limit, len(proxies))} из {len(proxies)}")
    clear = []

    for proxy in proxies[:limit]:
        proxy = proxy.strip().strip('"').strip("'")
        if ":" not in proxy:
            continue

        print(f" {proxy} ... ", end="", flush=True)
        try:
            opts = Options()
            opts.add_argument("--headless=new")
            opts.add_argument("--disable-gpu")
            opts.add_argument("--no-sandbox")
            opts.add_argument(f"--proxy-server=http://{proxy}")

            driver = webdriver.Chrome(options=opts)
            driver.set_page_load_timeout(timeout)
            driver.get("https://www.google.com")
            driver.quit()
            print("OK")
            clear.append(proxy)
        except Exception:
            print("нет")
            try:
                driver.quit()
            except Exception:
                pass

    print(f" Рабочих: {len(clear)}")
    return clear


def find_working_proxy(url=PROXY_URL, limit=20):
    #Вернуть первый рабочий прокси или None
    proxies = get_all_proxies(url)
    if not proxies:
        return None
    good = clean_list(proxies, limit=limit)
    return good[0] if good else None


if __name__ == "__main__":
    proxies = get_all_proxies()
    good = clean_list(proxies, limit=100)

    with open("proxy_list.txt", "w", encoding="utf-8") as f:
        for p in good:
            f.write(p + "\n")

    print(f"\nСохранено в proxy_list.txt: {len(good)} шт.")
