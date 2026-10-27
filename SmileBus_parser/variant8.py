import re
import time
import random
from datetime import date, timedelta

import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# from proxy.py import find_working_proxy

# Названия городов в ссылках на сайте пишутся по-английски
CITIES = {"Минск": "minsk", "Мозырь": "mozyr", "Речица": "rechica"}

class Log:
    def __init__(self, file="log.txt"):
        self.file = file
        open(file, "w", encoding="utf-8").close()

    def add(self, msg, t0=None):
        
        line = f"{msg} - {time.time() - t0:.2f} сек" if t0 else msg
        with open(self.file, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        # еще выводим в консоль
        print(line, flush=True)


class Parser:
    def __init__(self, routes=None, proxy=None):
        # настройки браузера: открываем Chrome на весь экран
        opt = Options()
        opt.add_argument("--start-maximized")
        # if proxy:
        #     opt.add_argument(f"--proxy-server=http://{proxy}")
        #     print(f" Парсер с прокси: {proxy}")
        # else:
        #     print(" Парсер без прокси")
        self.drive = webdriver.Chrome(options=opt)
        self.w = WebDriverWait(self.drive, 30)
        self.log = Log("log.txt")
        # если маршруты не передали, берём два из задания
        self.routes = routes or [("Минск", "Мозырь"), ("Минск", "Речица")]
        # сюда складываем все найденные билеты
        self.data_rows = []

    def close_cook(self):
        for word in ("Принять", "Согласен", "Отклонить"):
            buttons = self.drive.find_elements(By.XPATH, f"//button[contains(., '{word}')]")
            if buttons:
                try:
                    buttons[0].click()
                    time.sleep(0.3)
                except Exception:
                    # если не получилось нажать - ниче, идём дальше
                    pass
                break

    def open_page(self, c_from, c_to):
        # открываем страницу нужного маршрута
        self.drive.get(f"https://smilebus.by/routes/{CITIES[c_from]}/{CITIES[c_to]}")
        # ждём пока появится поле с датой или любая кнопка, значит страница прогрузилась
        self.w.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".date-pick__wrapper input, button")))
        time.sleep(1.5)
        self.close_cook()
        print("Маршрут:", self.drive.current_url, flush=True)

    def pick_date(self, d):
        # cell - id ячейки календаря, у каждого дня есть атрибут data-id вида "2026-10-24".
        t0, cell, ok = time.time(), f"{d.year}-{d.month}-{d.day}", False
        # поле даты - это input с атрибутом readonly, вручную в него печатать нельзя, можно только выбирать в календаре
        inp = self.drive.find_element(By.CSS_SELECTOR, ".date-pick__wrapper input[readonly]")
        # календарь не всегда открывается с первого клика, поэтому 3 попытки
        for _ in range(3):
            ActionChains(self.drive).move_to_element(inp).click().perform()
            try:
                # проверяем что календарь действительно открылся
                self.w.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".vdpOuterWrap, .vdpComponent")))
                ok = True
                break
            except Exception:
                time.sleep(1)
        # если за 3 попытки не открылся - пропускаем эту дату
        if not ok:
            self.log.add("pick_date календарь не открылся", t0)
            return False
        done = False
        # календарь показывает только один месяц, а нужная дата может быть в следующих. Поэтому в цикле: ищем день, если не нашли - листаем на месяц вперёд.
        for _ in range(3):
            # ищем ячейку нужного дня, :not(.outOfRange) убирает не те дни
            # из соседних месяцев, которые тоже видны в таблице календаря
            cells = self.drive.find_elements(By.CSS_SELECTOR, f'td.vdpCell[data-id="{cell}"]:not(.outOfRange)')
            if not cells:
                # запасной вариант поиска без фильтра, если классы другие
                cells = self.drive.find_elements(By.CSS_SELECTOR, f'td[data-id="{cell}"]')
            if cells:
                cl = cells[0].get_attribute("class") or ""
                # у прошедших дат и дат, на которые билеты ещё не продаются,в классе есть disabled - на такие кликать нельзя
                if "disabled" in cl or "outOfRange" in cl:
                    break
                cells[0].click()
                done = True
                break
            # нужного дня на экране нет, тогда нажимаем стрелку следующего месяц
            arrows = self.drive.find_elements(By.CSS_SELECTOR, ".vdpArrowNext")
            if not arrows:
                break
            ActionChains(self.drive).move_to_element(arrows[0]).click().perform()
            time.sleep(0.4)
        self.log.add("pick_date", t0)
        return done

    def press_find(self):
        t0 = time.time()
        # ищем кнопку по тексту "Найти"
        btn = self.w.until(EC.presence_of_element_located((By.XPATH, "//button[contains(., 'Найти')]")))
        # ждём пока кнопка станет активной: сайт иногда ещё грузится, и кнопка в это время disabled или у неё класс "loading"
        self.w.until(lambda x: btn.is_enabled() and "loading" not in (btn.get_attribute("class") or "") and btn.get_attribute("disabled") is None)
        time.sleep(0.3)
        try:
            # обычный клик мышкой
            ActionChains(self.drive).move_to_element(btn).click().perform()
        except Exception:
            # если что-то перекрывает кнопку и клик не прошёл - кликаем через javascript
            self.drive.execute_script("arguments[0].click();", btn)
        try:
            # после нажатия кнопка получает класс "loading", пока сайт ищет рейсы. Ждём пока этот класс пропадёт - значит результаты загрузились
            self.w.until(lambda x: "loading" not in (x.find_element(By.XPATH, "//button[contains(., 'Найти')]").get_attribute("class") or ""))
        except Exception:
            pass
        time.sleep(random.uniform(2, 4))
        self.log.add("press_find", t0)

    def find_tickets(self, c_from, c_to, d):
        t0 = time.time()
        self.open_page(c_from, c_to)
        if not self.pick_date(d):
            # если дату выбрать не получилось, возвращаем None
            self.log.add(f"find_tickets (даты {d} нет)", t0)
            return None
        self.press_find()
        self.log.add("find_tickets", t0)
        # возвращаем весь видимый текст страницы - из него потом достанем время и цену
        return self.drive.find_element(By.TAG_NAME, "body").text

    def get_trips(self, page_text, c_from, c_to, d, direction):
        # cnt - сколько рейсов нашли, used - уже встреченные (чтобы не было повторов)
        t0, cnt, used = time.time(), 0, set()
        # текст страницы режем на куски по пустым строкам: одна карточка рейса = один кусок
        for part in re.split(r"\n{2,}", page_text):
            # ищем время вида 12:30
            tm = re.findall(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", part)
            # в нормальной карточке два времени (отправление и прибытие),
            # если меньше - это не рейс, а какой-то другой текст на странице
            if len(tm) < 2:
                continue
            # ищем цену: число и после него "р." или "руб" или "BYN", например "38 р."
            pr = re.findall(r"(?:Цена\s*[:\s]*)?(\d+[.,]\d+|\d+)\s*(?:руб\.?|BYN|р\.)", part, flags=re.I)
            price = None
            if pr:
                try:
                    # запятую меняем на точку, чтобы получилось число с точкой
                    val = float(pr[0].replace(",", "."))
                    # проверка на ошибочные данные: цена на такой маршрут
                    # не может быть меньше 1 и больше 200 рублей
                    if 1 <= val <= 100:
                        price = val
                except ValueError:
                    pass
            # приводим время к одному виду "08:05" (с нулём впереди),
            # первое время в куске - отправление, второе - прибытие
            dep = f"{int(tm[0][0]):02d}:{tm[0][1]}"
            arr = f"{int(tm[1][0]):02d}:{tm[1][1]}"
            # ключ рейса, если такой уже был - пропускаем (удаление дубликатов)
            key = (dep, arr, price)
            if key in used:
                continue
            used.add(key)
            # добавляем рейс в общий список
            self.data_rows.append({"route": f"{c_from}-{c_to}", "direction": direction, "date": d, "departure_time": dep, "arrival_time": arr, "price": price})
            cnt += 1
        print(f"{d} {direction} {c_from}-{c_to}: +{cnt}", flush=True)
        self.log.add("get_trips", t0)

    def run(self):
        t0 = time.time()
        today = date.today()
        # собираем данные на 30 дней вперёд (так как сайт показывает билеты только на 30 дней)
        last_day = today + timedelta(days=30)
        d = today
        while d <= last_day:
            for a, b in self.routes:
                try:
                    pt = self.find_tickets(a, b, d)
                    if pt:
                        self.get_trips(pt, a, b, d, "туда")
                except Exception as e:
                    print(f"Пропуск {a}-{b} туда {d}: {e}", flush=True)
                    self.log.add(f"ошибка {a}-{b} туда {d}: {e}")
                # обратный билет берём на дату + 7 дней,
                # а города меняем местами (b -> a)
                back_day = d + timedelta(days=7)
                # не выходим за пределы 30 дней
                if (back_day - today).days <= 30:
                    try:
                        pt = self.find_tickets(b, a, back_day)
                        if pt:
                            self.get_trips(pt, b, a, back_day, "обратно")
                    except Exception as e:
                        print(f"Пропуск {b}-{a} обратно {back_day}: {e}", flush=True)
                        self.log.add(f"ошибка {b}-{a} обратно {back_day}: {e}")
            d += timedelta(days=1)
        try:
            self.drive.quit()
        except Exception:
            pass
        self.log.add("run", t0)
        return pd.DataFrame(self.data_rows)


class DataWork:
    def __init__(self, log):
        self.log = log

    def clear_data(self, df):
        t0 = time.time()
        # если данных нет, то и чистить нечего
        if df.empty:
            return df
        # убираем полностью одинаковые строки
        df = df.drop_duplicates()
        # price приводим к числу
        df["price"] = pd.to_numeric(df["price"], errors="coerce")
        # выкидываем строки, где нет времени отправления или даты
        df = df.dropna(subset=["departure_time", "date"])
        # убираем ошибочные цены
        df = df[(df["price"].isna()) | ((df["price"] > 0) & (df["price"] < 500))]
        # ещё раз удаляем дубли, но теперь по главным признакам рейса:
        # один и тот же рейс (маршрут + направление + дата + время) не может повторяться
        df = df.drop_duplicates(subset=["route", "direction", "date", "departure_time"])
        self.log.add("clear_data", t0)
        return df

    def prepare(self, df):
        t0 = time.time()
        if df.empty:
            return df
        # copy() чтобы pandas не ругался на изменение куска таблицы
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"])
        # из даты получаем день недели и номер месяца
        df["weekday"] = df["date"].dt.day_name()
        df["month"] = df["date"].dt.month
        # возвращаем дату в обычный вид 
        df["date"] = df["date"].dt.date
        self.log.add("prepare", t0)
        return df

    def save_to_csv(self, df, name):
        t0 = time.time()
        df.to_csv(name, index=False, encoding="utf-8-sig")
        self.log.add(f"save_to_csv {name}", t0)


if __name__ == "__main__":
    all_time = time.time()
    # working_proxy = find_working_proxy()
    # bot = Parser(proxy=working_proxy)
    bot = Parser()
    dw = DataWork(bot.log)
    # если сбор упадёт с ошибкой, то всё равно сохраним то, что успели собрать
    try:
        data = bot.run()
    except Exception as e:
        print("Ошибка сбора:", e, flush=True)
        data = pd.DataFrame(bot.data_rows)
    if data.empty:
        print("Данных нет")
    else:
        # сначала сохраняем сырые данные, потом очищенные и обработанные
        dw.save_to_csv(data, "raw_data.csv")
        dw.save_to_csv(dw.prepare(dw.clear_data(data)), "tickets.csv")
    print(f"\nГотово за {time.time() - all_time:.1f} сек, строк: {len(data)}")
    print("Файлы: raw_data.csv, tickets.csv, log.txt")
