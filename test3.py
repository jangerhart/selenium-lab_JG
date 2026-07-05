from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

driver = webdriver.Chrome()
driver.get("https://ocp.cz.tmo/dashboard/request/create")

wait = WebDriverWait(driver, 10)

wait.until(EC.element_to_be_clickable((By.ID, "#IDToken1"))).send_keys("gerhartj")
wait.until(EC.element_to_be_clickable((By.ID, "#IDToken2"))).send_keys("SuperSecretPassword!")


time.sleep(3)
driver.quit()
