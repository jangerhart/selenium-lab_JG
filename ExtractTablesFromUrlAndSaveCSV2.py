import csv
import re
import time
from dataclasses import dataclass
from typing import Optional, List

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


BASE_URL = (
    "https://www.jcb-nahradni-dily.cz/hledani"
    "?query=*&page={page}&pageSize=48&section=searchresultcommoditiesprovider"
)

OUTPUT_CSV = "jcb_produkty.csv"

# Bezpečnostní pojistka: když nechceš projet všechno, nastav třeba 10.
# Pokud chceš projet celé, nech None.
MAX_PAGES = None  # např. 10

WAIT_SECONDS = 20


@dataclass
class Product:
    name: str
    price_with_vat: Optional[float]
    price_without_vat: Optional[float]
    availability: str
    code: str
    url: str


def setup_driver(headless: bool = True) -> webdriver.Chrome:
    opts = webdriver.ChromeOptions()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1400,900")
    opts.add_argument("--disable-gpu")
    # pokud by to padalo ve firemním prostředí, nech klidně pryč:
    # opts.add_argument("--no-sandbox")
    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(60)
    return driver


def try_accept_cookies(driver: webdriver.Chrome) -> None:
    """
    Weby typu FastCentrik často vyhodí cookies lištu.
    Zkusíme najít tlačítko typu 'Přijmout/Souhlasím' a kliknout.
    Když tam není, nic se neděje.
    """
    candidates_xpath = [
        "//button[contains(., 'Přijmout')]",
        "//button[contains(., 'Souhlas')]",
        "//a[contains(., 'Přijmout')]",
        "//a[contains(., 'Souhlas')]",
    ]
    for xp in candidates_xpath:
        try:
            el = WebDriverWait(driver, 2).until(EC.element_to_be_clickable((By.XPATH, xp)))
            el.click()
            time.sleep(0.3)
            return
        except Exception:
            pass


def normalize_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def parse_cz_price_to_float(price_str: str) -> Optional[float]:
    """
    '3 955,49' -> 3955.49
    """
    if not price_str:
        return None
    x = price_str.replace("\u00A0", " ").replace(" ", "").replace(",", ".")
    try:
        return float(x)
    except ValueError:
        return None


# Vzor textu produktu na kartě (typicky):
# "O-kroužek 10,89 Kč s DPH 9,00 Kč bez DPH skladem Do košíku kód: 2401/0111"
PRODUCT_RE = re.compile(
    r"^(?P<name>.+?)\s+"
    r"(?P<with_vat>[\d\s]+,\d+)\s*Kč\s*s\s*DPH\s+"
    r"(?P<without_vat>[\d\s]+,\d+)\s*Kč\s*bez\s*DPH\s+"
    r"(?P<availability>.+?)\s+Do\s+košíku\s+kód:\s*(?P<code>\S+)\s*$",
    re.IGNORECASE
)


def extract_products_on_page(driver: webdriver.Chrome) -> List[Product]:
    """
    Najde produktové položky na stránce podle toho, že:
    - je to <a> odkaz na produkt
    - a text obsahuje 'Do košíku' a 'kód:'
    """
    # počkáme, než se stránka "rozumně" načte (aspoň nadpis / tělo)
    WebDriverWait(driver, WAIT_SECONDS).until(
        EC.presence_of_element_located((By.XPATH, "//*[contains(., 'Výsledek hledání') or contains(., 'Hledám')]"))
    )

    # produktové odkazy (karty)
    anchors = driver.find_elements(
        By.XPATH,
        "//a[contains(., 'Do košíku') and (contains(., 'kód:') or contains(., 'Kód:'))]"
    )

    products: List[Product] = []

    for a in anchors:
        txt = normalize_ws(a.text)
        href = a.get_attribute("href") or ""

        # Některé odkazy v layoutu můžou omylem sedět – filtr na URL produktu
        # (produkty na webu vypadají jako /nejaky-nazev-123)
        if not re.search(r"/.+-\d+$", href):
            continue

        m = PRODUCT_RE.match(txt)
        if not m:
            # fallback: když se text liší, aspoň ulož základ a nech ceny prázdné
            # (lepší než přijít o data)
            code_match = re.search(r"kód:\s*(\S+)", txt, re.IGNORECASE)
            code = code_match.group(1) if code_match else ""
            products.append(Product(
                name=txt,
                price_with_vat=None,
                price_without_vat=None,
                availability="",
                code=code,
                url=href
            ))
            continue

        name = m.group("name").strip()
        with_vat = parse_cz_price_to_float(m.group("with_vat"))
        without_vat = parse_cz_price_to_float(m.group("without_vat"))
        availability = m.group("availability").strip()
        code = m.group("code").strip()

        products.append(Product(
            name=name,
            price_with_vat=with_vat,
            price_without_vat=without_vat,
            availability=availability,
            code=code,
            url=href
        ))

    # deduplikace podle URL (kdyby se něco chytlo 2×)
    uniq = {}
    for p in products:
        uniq[p.url] = p
    return list(uniq.values())


def scrape_all_to_csv():
    driver = setup_driver(headless=True)

    fieldnames = [
        "name",
        "price_with_vat",
        "price_without_vat",
        "availability",
        "code",
        "url",
        "page",
    ]

    total = 0
    page = 1

    try:
        with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            while True:
                if MAX_PAGES is not None and page > MAX_PAGES:
                    break

                url = BASE_URL.format(page=page)
                driver.get(url)
                try_accept_cookies(driver)

                products = extract_products_on_page(driver)

                # konec stránkování: stránka bez produktů
                if not products:
                    print(f"[STOP] page={page} -> 0 produktů (konec).")
                    break

                for p in products:
                    writer.writerow({
                        "name": p.name,
                        "price_with_vat": p.price_with_vat,
                        "price_without_vat": p.price_without_vat,
                        "availability": p.availability,
                        "code": p.code,
                        "url": p.url,
                        "page": page,
                    })

                total += len(products)
                print(f"[OK] page={page} -> {len(products)} produktů (celkem {total})")
                page += 1

    finally:
        driver.quit()

    print(f"Hotovo. Zapsáno {total} řádků do {OUTPUT_CSV}")


if __name__ == "__main__":
    scrape_all_to_csv()
