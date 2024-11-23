import asyncio
from html import unescape
import itertools
import logging
import re
from playwright.async_api import async_playwright
from openpyxl import Workbook
import pdb

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("ebay_scraper.log"), logging.StreamHandler()],
)


async def split_list_by_delimiter(lst, delimiter):
    result = []
    current_sublist = []
    for item in lst:
        if item == delimiter:
            if current_sublist:
                result.append(current_sublist)
                current_sublist = []
        else:
            current_sublist.append(item)

    if current_sublist:
        result.append(current_sublist)
    return result


async def select_variant(page, variants):
    for i, value in enumerate(variants):
        try:
            DROPDOWN_BUTTON_SELECTOR = "button.listbox-button__control"

            logging.info(f"Попытка выбрать вариант '{value}' на уровне {i + 1}.")

            buttons = await page.query_selector_all(DROPDOWN_BUTTON_SELECTOR)
            logging.info(f"Найдено {len(buttons)} кнопок для выбора на уровне {i + 1}.")

            if len(buttons) <= i:
                logging.info("Кнопки не найдены. Повторяю поиск после ожидания...")
                await asyncio.sleep(3)
                buttons = await page.query_selector_all(DROPDOWN_BUTTON_SELECTOR)

            if len(buttons) <= i:
                raise ValueError(
                    f"Кнопка раскрывающегося меню для уровня {i + 1} не найдена."
                )

            button = buttons[i]

            # Получаем значение атрибута value кнопки
            button_value = await button.get_attribute("value")

            # Проверка: если значение кнопки уже совпадает с вариантом, пропускаем
            if button_value and button_value.strip() == value.strip():
                logging.info(
                    f"Кнопка на уровне {i + 1} уже содержит выбранное значение '{value}'. Пропускаем клик."
                )
                continue

            logging.info(f"Попытка нажать кнопку {i + 1}-го уровня.")
            await button.click()
            logging.info(
                f"Кнопка раскрывающегося меню для уровня {i + 1} успешно нажата."
            )

            # Ждём появления выпадающего списка
            await asyncio.sleep(1)  # Небольшая пауза для обновления DOM
            await page.wait_for_selector(
                f'div[role="listbox"]:has-text("{value}")',
                state="visible",
                timeout=60000,
            )
            logging.info(
                f"Появился список для выбора. Попытка выбрать вариант '{value}'."
            )

            option = await page.query_selector(
                f'div[role="option"]:has-text("{value}")'
            )
            if option is None:
                raise ValueError(f"Опция '{value}' не найдена.")
            await option.click()
            logging.info(f"Вариант '{value}' на уровне {i + 1} успешно выбран.")
        except Exception as e:
            logging.error(
                f"Ошибка при выборе варианта '{value}' на уровне {i + 1}: {str(e)}"
            )
            raise ValueError(
                f"Ошибка при выборе варианта '{value}' (уровень {i + 1}): {str(e)}"
            )

    try:
        logging.info("Попытка получить цену товара.")
        price_element = page.locator(
            'div[data-testid="x-price-primary"] span.ux-textspans'
        )
        await price_element.wait_for(
            state="visible", timeout=10000
        )  # Ждем видимости цены
        price_text = await price_element.inner_text()
        logging.info(f"Цена успешно получена: {price_text}")

        # Удалить 'US $' и конвертировать в float

        return price_text

    except Exception as e:
        logging.error(f"Ошибка при получении цены: {str(e)}")
        raise ValueError(f"Ошибка при получении цены: {str(e)}")


async def parse_ebay_seller(seller_url):
    """
    Scrapes product data from an eBay seller's page and saves it to an Excel file.

    :param seller_url: URL of the eBay seller's page
    """
    logging.info("Starting eBay seller scraping...")

    try:
        # Launch the Playwright browser
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            logging.info("Browser launched in headless mode.")
            page = await browser.new_page(locale="en-US")

            # Open the seller's URL
            await page.goto(seller_url)
            logging.info(f"Navigated to {seller_url}")

            # Scroll the page to load all items (if applicable)
            last_height = None
            while True:
                current_height = await page.evaluate("document.body.scrollHeight")
                if last_height == current_height:
                    break
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(2)  # Give time for content to load
                last_height = current_height
            logging.info("Page scrolling completed.")

            # Select product elements
            await page.wait_for_selector("ul.srp-results.srp-list")
            items = await page.query_selector_all("ul.srp-results.srp-list li.s-item")

            logging.info(f"Found {len(items)} items on the page.")

            # Create an Excel workbook and add headers
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "eBay Seller Data"
            sheet.append(
                [
                    "наименование товара",
                    "цена",
                    "категория",
                    "фото -1",
                    "фото -2",
                    "фото -3",
                    "фото -4",
                    "фото -5",
                    "фото -6",
                    "фото -7",
                    "фото -8",
                    "фото -9",
                    "фото -10",
                    "сылка на товар",
                    "сылка на продавца",
                    "колтчство товара",
                    "бренд ",
                    "кондиция товара",
                ]
            )

            # Extract data for each product
            for item in items:
                try:
                    # Extract product details
                    title = await item.query_selector(".s-item__title")
                    title_text = await title.inner_text() if title else "N/A"

                    price = await item.query_selector("span.s-item__price")
                    price_text = await price.inner_text() if price else "N/A"

                    # Extract product link

                    item_url = await item.query_selector("a.s-item__link")
                    item_url_href = (
                        await item_url.get_attribute("href") if item_url else "N/A"
                    )
                    if not item_url_href:
                        logging.warning("Item URL not found, skipping this item.")
                        continue

                    context = await browser.new_context()
                    item_page = await context.new_page()
                    await item_page.goto(item_url_href, wait_until="domcontentloaded")

                    category_elem = await item_page.query_selector(
                        "ul li a.seo-breadcrumb-text span"
                    )
                    category_name = (
                        await category_elem.inner_text() if category_elem else "N/A"
                    )

                    # Extract available quantity text

                    quantity_element = await item_page.query_selector(
                        "#qtyAvailability .ux-textspans--SECONDARY"
                    )
                    quantity_text = (
                        await quantity_element.inner_text()
                        if quantity_element
                        else "N/A"
                    )

                    # Replace your existing condition element code with:
                    condition_element = await item_page.query_selector(
                        ".x-item-condition-text .ux-textspans"
                    )
                    condition_text = (
                        await condition_element.inner_text()
                        if condition_element
                        else "N/A"
                    )

                    # Extract brand text
                    brand_element = await item_page.query_selector(
                        "dl[data-testid='ux-labels-values'].ux-labels-values--brand dd span.ux-textspans"
                    )
                    brand_text = (
                        await brand_element.inner_text() if brand_element else "N/A"
                    )

                    # Extract all images
                    images = await item_page.query_selector_all(
                        "button.ux-image-grid-item img"
                    )

                    image_urls = []
                    for img in images:
                        src = await img.get_attribute(
                            "src"
                        )  # Используем await для асинхронного вызова
                        if src:
                            image_urls.append(src)
                    if len(image_urls) < 10:
                        image_urls.extend(["N/A"] * (10 - len(image_urls)))

                    # Add this where you're processing item details
                    async def get_listbox_values(page):
                        values = []
                        # Find all elements with class 'listbox__value'
                        value_elements = await page.query_selector_all(
                            ".listbox__value"
                        )

                        # Extract text from each element
                        for element in value_elements:
                            value_text = await element.inner_text()
                            if value_text:  # Only add non-empty values
                                values.append(value_text.strip())

                        return values

                    # In your main item processing loop, add:
                    try:
                        # Your existing code...

                        # Get all listbox values
                        listbox_values = await get_listbox_values(item_page)
                        logging.info(f"Found variants: {listbox_values}")

                        listbox_values = await split_list_by_delimiter(
                            listbox_values, "Select"
                        )
                        if listbox_values:

                            for combo in itertools.product(*listbox_values):
                                title_name = f"{title_text} : {combo}"
                                logging.info(f"Processing combo : {combo}")

                                price_variant = await select_variant(item_page, combo)
                                if price_variant:
                                    price_text = price_variant
                                logging.info(f"Processing item: {title_name}")
                                row = (
                                    [title_name, price_text, category_name]
                                    + image_urls[:10]
                                    + [
                                        item_url_href,
                                        seller_url,
                                        quantity_text,
                                        brand_text,
                                        condition_text,
                                    ]
                                )

                                sheet.append(row)
                                logging.info(f"Added item: {title_text}")

                        else:
                            row = (
                                [title_text, price_text, category_name]
                                + image_urls[:10]
                                + [
                                    item_url_href,
                                    seller_url,
                                    quantity_text,
                                    brand_text,
                                    condition_text,
                                ]
                            )

                        sheet.append(row)
                        logging.info(f"Added item: {title_text}")

                    except Exception as e:
                        logging.error(f"Error processing item variants: {e}")

                    # Закрываем контекст
                    await item_page.close()

                except Exception as e:
                    logging.error(f"Error processing item: {e}")

            # Save the Excel file
            output_file = "ebay_seller_data_playwright.xlsx"
            workbook.save(output_file)
            logging.info(f"Data successfully saved to {output_file}")

            # Close the browser
            await browser.close()
            logging.info("Browser closed.")
    except Exception as e:
        logging.critical(f"An unexpected error occurred: {e}")


# Specify the seller's URL
seller_url = "https://www.ebay.com/sch/i.html?_trksid=p3692&_ssn=satmaximum"

# Run the asynchronous function
if __name__ == "__main__":
    try:
        asyncio.run(parse_ebay_seller(seller_url))
    except Exception as e:
        logging.critical(f"Failed to execute the script: {e}")
