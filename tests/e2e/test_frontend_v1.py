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
        from selenium.webdriver.common.keys import Keys
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
                self.assertEqual(len(driver.find_elements(By.CSS_SELECTOR, ".empty-state")), 2)
                self.assertIn("Nenhum device no cache", driver.find_element(By.ID, "device-list").text)
                self.assertIn("Nenhuma localização no mapa", driver.find_element(By.ID, "report-list").text)
                self.assertTrue(driver.find_element(By.ID, "map-empty").is_displayed())
                self.assertTrue(driver.find_element(By.ID, "fit-reports").get_attribute("disabled"))
                self.assertEqual(driver.find_element(By.ID, "map-summary").text, "Nenhum report visível")

                driver.execute_script("document.activeElement.blur()")
                driver.find_element(By.TAG_NAME, "body").send_keys(Keys.TAB)
                wait.until(
                    lambda browser: browser.execute_script(
                        "return document.activeElement.classList.contains('skip-link')"
                    )
                )
                skip_link = driver.find_element(By.CSS_SELECTOR, ".skip-link")
                self.assertTrue(skip_link.is_displayed())
                skip_link.send_keys(Keys.ENTER)
                wait.until(lambda browser: browser.current_url.endswith("#map"))

                driver.find_element(By.ID, "sync-devices").click()
                wait.until(
                    lambda browser: "SUCCEEDED" in browser.find_element(By.ID, "status").text
                    and browser.find_element(By.ID, "device-count").text == "2"
                )
                self.assertIn("success", driver.find_element(By.ID, "status").get_attribute("class"))
                self.assertEqual(len(driver.find_elements(By.CSS_SELECTOR, "#device-list .empty-state")), 0)
                self.assertEqual(len(driver.find_elements(By.CSS_SELECTOR, "#report-list .empty-state")), 1)
                self.assertIn("Atualize as localizações", driver.find_element(By.ID, "map-empty-detail").text)
                device_buttons = driver.find_elements(By.CSS_SELECTOR, ".device-actions button")
                self.assertTrue(all(button.get_attribute("aria-label") for button in device_buttons))

                driver.find_element(By.ID, "refresh-all").click()
                wait.until(
                    lambda browser: "SUCCEEDED" in browser.find_element(By.ID, "status").text
                    and browser.find_element(By.ID, "report-count").text == "2"
                )
                self.assertIn("success", driver.find_element(By.ID, "status").get_attribute("class"))
                self.assertEqual(len(driver.find_elements(By.CSS_SELECTOR, "#report-list .empty-state")), 0)
                self.assertFalse(driver.find_element(By.ID, "map-empty").is_displayed())
                self.assertIsNone(driver.find_element(By.ID, "fit-reports").get_attribute("disabled"))
                self.assertIn("2 reports visíveis", driver.find_element(By.ID, "map-summary").text)
                driver.find_element(By.ID, "fit-reports").click()
                self.assertEqual(
                    driver.execute_script("return document.activeElement.id"),
                    "map",
                )
                self.assertIn("há ", driver.find_element(By.CSS_SELECTOR, ".report small").text)
                first_report = driver.find_element(By.CSS_SELECTOR, ".report")
                self.assertEqual(first_report.tag_name, "button")
                self.assertTrue(first_report.get_attribute("aria-label").startswith("Centralizar "))
                first_report.send_keys(Keys.ENTER)
                self.assertEqual(
                    driver.execute_script("return document.activeElement.className"),
                    "report",
                )
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

    def test_responsive_panel_across_desktop_tablet_and_phone(self):
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
                database_path=Path(directory) / "responsive.db",
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
                toggle = driver.find_element(By.ID, "panel-toggle")
                responsive_screenshot_dir = os.environ.get("BROWSER_RESPONSIVE_SCREENSHOT_DIR")
                screenshot_directory = None
                if responsive_screenshot_dir:
                    screenshot_directory = Path(responsive_screenshot_dir)
                    screenshot_directory.mkdir(parents=True, exist_ok=True)

                def save_responsive_screenshot(filename):
                    if screenshot_directory:
                        driver.save_screenshot(str(screenshot_directory / filename))

                def set_viewport(width, height):
                    driver.execute_cdp_cmd(
                        "Emulation.setDeviceMetricsOverride",
                        {
                            "width": width,
                            "height": height,
                            "deviceScaleFactor": 1,
                            "mobile": False,
                        },
                    )
                    driver.execute_async_script(
                        "const done = arguments[0]; requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(done, 300)));"
                    )

                def responsive_layers_visible(browser):
                    return browser.execute_script(
                        """
                        const panel = document.querySelector('#device-panel');
                        const toggle = document.querySelector('#panel-toggle');
                        const panelRect = panel.getBoundingClientRect();
                        const toggleRect = toggle.getBoundingClientRect();
                        const panelTop = document.elementFromPoint(panelRect.left + 8, panelRect.top + 8);
                        const toggleTop = document.elementFromPoint(
                          toggleRect.left + toggleRect.width / 2,
                          toggleRect.top + toggleRect.height / 2
                        );
                        return panelRect.width > 0 && panelRect.height > 0
                          && toggleRect.width > 0 && toggleRect.height > 0
                          && panel.contains(panelTop) && toggle.contains(toggleTop);
                        """
                    )

                for width, expected_panel_width, screenshot_name in (
                    (1440, 420, "kezpo-desktop-max.png"),
                    (1300, 400, "kezpo-desktop-wide.png"),
                    (1200, 380, "kezpo-desktop.png"),
                ):
                    set_viewport(width, 900)
                    self.assertEqual(
                        driver.execute_script("return getComputedStyle(arguments[0]).display", toggle),
                        "none",
                    )
                    self.assertAlmostEqual(
                        driver.find_element(By.ID, "device-panel").rect["width"],
                        expected_panel_width,
                        delta=1,
                    )
                    self.assertTrue(
                        driver.execute_script(
                            "return document.documentElement.scrollWidth <= window.innerWidth"
                        )
                    )
                    save_responsive_screenshot(screenshot_name)

                set_viewport(900, 900)
                wait.until(
                    lambda browser: browser.execute_script(
                        "return getComputedStyle(document.querySelector('#panel-toggle')).display"
                    ) == "flex"
                )
                self.assertEqual(
                    driver.execute_script(
                        "return getComputedStyle(document.querySelector('#device-panel')).position"
                    ),
                    "absolute",
                )
                self.assertNotIn(
                    "panel-collapsed",
                    driver.find_element(By.TAG_NAME, "body").get_attribute("class"),
                )
                wait.until(responsive_layers_visible)
                panel_rect = driver.find_element(By.ID, "device-panel").rect
                map_empty_rect = driver.find_element(By.ID, "map-empty").rect
                map_summary_rect = driver.find_element(By.ID, "map-summary").rect
                map_key_rect = driver.find_element(By.CSS_SELECTOR, ".map-key").rect
                panel_right = panel_rect["x"] + panel_rect["width"]
                self.assertGreaterEqual(map_empty_rect["x"], panel_right)
                self.assertGreaterEqual(map_summary_rect["x"], panel_right)
                self.assertLessEqual(
                    map_summary_rect["y"] + map_summary_rect["height"],
                    map_key_rect["y"],
                )
                save_responsive_screenshot("kezpo-tablet.png")

                toggle.click()
                wait.until(lambda browser: "panel-collapsed" in browser.find_element(By.TAG_NAME, "body").get_attribute("class"))
                self.assertEqual(toggle.get_attribute("aria-expanded"), "false")
                wait.until(
                    lambda browser: abs(
                        browser.execute_script(
                            "const r=document.querySelector('#map-empty').getBoundingClientRect(); return r.left+r.width/2-window.innerWidth/2"
                        )
                    ) < 2
                )
                toggle.click()
                wait.until(lambda browser: "panel-collapsed" not in browser.find_element(By.TAG_NAME, "body").get_attribute("class"))

                set_viewport(700, 900)
                wait.until(
                    lambda browser: len(
                        browser.execute_script(
                            "return getComputedStyle(document.querySelector('.actions')).gridTemplateColumns.split(' ')"
                        )
                    ) == 2
                )
                map_rect = driver.find_element(By.ID, "map").rect
                panel_rect = driver.find_element(By.ID, "device-panel").rect
                self.assertGreaterEqual(panel_rect["y"], map_rect["y"] + map_rect["height"] - 2)
                self.assertTrue(
                    driver.execute_script("return document.documentElement.scrollWidth <= window.innerWidth")
                )
                save_responsive_screenshot("kezpo-phone-wide.png")

                toggle.click()
                wait.until(
                    lambda browser: browser.execute_script(
                        "return document.querySelector('#map').getBoundingClientRect().height >= window.innerHeight - 1"
                    )
                )
                toggle.click()
                wait.until(lambda browser: "panel-collapsed" not in browser.find_element(By.TAG_NAME, "body").get_attribute("class"))

                set_viewport(390, 844)
                wait.until(
                    lambda browser: browser.execute_script(
                        "return getComputedStyle(document.querySelector('.actions')).gridTemplateColumns.split(' ').length"
                    ) == 1
                )
                self.assertTrue(
                    driver.execute_script("return document.documentElement.scrollWidth <= window.innerWidth")
                )
                wait.until(responsive_layers_visible)
                save_responsive_screenshot("kezpo-phone.png")

                driver.execute_cdp_cmd(
                    "Emulation.setEmulatedMedia",
                    {
                        "features": [
                            {"name": "prefers-reduced-motion", "value": "reduce"},
                        ]
                    },
                )
                wait.until(
                    lambda browser: browser.execute_script(
                        "return matchMedia('(prefers-reduced-motion: reduce)').matches"
                    )
                )
                self.assertTrue(
                    driver.execute_script(
                        """
                        return getComputedStyle(document.querySelector('#panel-toggle'))
                          .transitionDuration.split(',')
                          .every(value => parseFloat(value) <= 0.001);
                        """
                    )
                )
                toggle.click()
                self.assertIn(
                    "panel-collapsed",
                    driver.find_element(By.TAG_NAME, "body").get_attribute("class"),
                )
                toggle.click()
            finally:
                if driver is not None:
                    driver.quit()
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
