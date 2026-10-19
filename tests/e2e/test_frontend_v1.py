import base64
import os
import tempfile
import threading
import unittest
from pathlib import Path

from MapApp.server import create_server


@unittest.skipUnless(os.environ.get("RUN_BROWSER_E2E") == "1", "set RUN_BROWSER_E2E=1")
class FrontendV1BrowserTest(unittest.TestCase):
    def test_main_demo_sync_refresh_history_and_restart_ready_ui(self):
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait

        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        with tempfile.TemporaryDirectory() as directory:
            server = create_server(
                port=0,
                demo=True,
                database_path=Path(directory) / "browser.db",
                tile_fetcher=lambda _z, _x, _y: (png, "image/png"),
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            options = webdriver.ChromeOptions()
            options.add_argument("--headless=new")
            options.add_argument("--window-size=1440,1000")
            options.add_argument("--ignore-certificate-errors")
            chrome_binary = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
            if chrome_binary.exists():
                options.binary_location = str(chrome_binary)

            driver = None
            try:
                driver = webdriver.Chrome(options=options)
                driver.get(f"http://127.0.0.1:{server.server_address[1]}/")
                wait = WebDriverWait(driver, 15)
                wait.until(lambda browser: browser.execute_script("return window.__findHubReady === true"))
                self.assertEqual(driver.find_element(By.ID, "device-count").text, "0")

                driver.find_element(By.ID, "sync-devices").click()
                wait.until(
                    lambda browser: "SUCCEEDED" in browser.find_element(By.ID, "status").text
                    and browser.find_element(By.ID, "device-count").text == "2"
                )

                driver.find_element(By.ID, "refresh-all").click()
                wait.until(
                    lambda browser: "SUCCEEDED" in browser.find_element(By.ID, "status").text
                    and browser.find_element(By.ID, "report-count").text == "2"
                )
                self.assertIn("há ", driver.find_element(By.CSS_SELECTOR, ".report small").text)
                wait.until(
                    lambda browser: len(browser.find_elements(By.CSS_SELECTOR, ".leaflet-interactive")) >= 2
                )

                driver.find_elements(By.XPATH, "//button[normalize-space()='Histórico']")[0].click()
                wait.until(lambda browser: browser.find_element(By.ID, "report-count").text == "4")
                self.assertGreaterEqual(
                    len(driver.find_elements(By.CSS_SELECTOR, ".leaflet-overlay-pane path[fill='none']")),
                    1,
                )

                driver.find_elements(By.XPATH, "//button[normalize-space()='Atualizar']")[0].click()
                wait.until(
                    lambda browser: "SUCCEEDED" in browser.find_element(By.ID, "status").text
                    and browser.find_element(By.ID, "report-count").text == "2"
                )
                self.assertNotIn("demo-keys", driver.page_source)
                screenshot = os.environ.get("BROWSER_E2E_SCREENSHOT")
                if screenshot:
                    driver.save_screenshot(screenshot)
            finally:
                if driver is not None:
                    driver.quit()
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
