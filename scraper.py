import asyncio
from html import unescape
import itertools
import logging
import re
from typing import Dict, List
import playwright
from playwright.async_api import async_playwright, Page, Browser
from openpyxl import Workbook
import pdb

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("ebay_scraper.log"), logging.StreamHandler()],
)
TITLE_TABLES = [
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
CONCURRENT_TASK_LIMIT = 4


async def split_list_by_delimiter(lst, delimiter):
    """Split a list by separator."""
    logging.info("Разделение списка по разделителю.", exc_info=True)
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


async def find_buttons(page, selector, level):
    """Search for buttons by a given selector."""
    logging.info(f"Поиск кнопок на уровне {level}.", exc_info=True)
    buttons = await page.query_selector_all(selector)

    if not buttons:
        logging.info(
            f"Кнопки не найдены. Ожидание и повторный поиск на уровне {level}.",
            exc_info=True,
        )
        await asyncio.sleep(3)
        buttons = await page.query_selector_all(selector)

    if len(buttons) <= level:
        raise ValueError(f"Кнопка раскрывающегося меню для уровня {level} не найдена.")

    return buttons


async def select_option(page, button, value, level):
    """Select an option from the drop-down list."""
    try:
        logging.info(f"Получение значения кнопки на уровне {level}.", exc_info=True)
        button_value = await button.get_attribute("value")

        if button_value and button_value.strip() == value.strip():
            logging.info(
                f"Кнопка на уровне {level} уже содержит выбранное значение '{value}'. Пропускаем.",
                exc_info=True,
            )
            return

        logging.info(f"Нажимаем кнопку на уровне {level}.", exc_info=True)
        await button.click()

        # We are waiting for the drop-down list to appear
        await asyncio.sleep(1)
        await page.wait_for_selector(
            f'div[role="listbox"]:has-text("{value}")',
            state="visible",
            timeout=60000,
        )

        logging.info(f"Выбираем опцию '{value}' из выпадающего списка.", exc_info=True)
        option = await page.query_selector(f'div[role="option"]:has-text("{value}")')

        if option is None:
            logging.error(f"Опция '{value}' не найдена на уровне {level}.")
            raise ValueError(f"Опция '{value}' не найдена на уровне {level}.")

        await option.click()
        logging.info(
            f"Опция '{value}' успешно выбрана на уровне {level}.", exc_info=True
        )

    except Exception as e:
        logging.error(
            f"Ошибка при выборе опции '{value}' на уровне {level}: {str(e)}",
            exc_info=True,
        )
        raise


async def get_price(page):
    """Get the price of the product."""
    try:
        logging.info("Получение цены товара.", exc_info=True)
        price_element = page.locator(
            'div[data-testid="x-price-primary"] span.ux-textspans'
        )
        await price_element.wait_for(state="visible", timeout=10000)
        price_text = await price_element.inner_text()
        logging.info(f"Цена успешно получена: {price_text}", exc_info=True)
        return price_text
    except Exception as e:
        logging.error(f"Ошибка при получении цены: {str(e)}", exc_info=True)
        raise ValueError(f"Ошибка при получении цены: {str(e)}")


async def select_variant(page, variants):
    """Select product variants."""
    logging.info("Выбор вариантов товара.", exc_info=True)
    DROPDOWN_BUTTON_SELECTOR = "button.listbox-button__control"

    for i, value in enumerate(variants):
        try:
            buttons = await find_buttons(page, DROPDOWN_BUTTON_SELECTOR, i)
            button = buttons[i]
            await select_option(page, button, value, i + 1)
        except Exception as e:
            logging.error(
                f"Ошибка при обработке варианта '{value}' на уровне {i + 1}: {str(e)}",
                exc_info=True,
            )
            raise ValueError(
                f"Ошибка при обработке варианта '{value}' (уровень {i + 1}): {str(e)}"
            )

    return await get_price(page)


async def scroll_to_load(page: Page) -> None:
    """Scroll the page to load all items."""
    last_height = None
    while True:
        current_height = await page.evaluate("document.body.scrollHeight")
        if last_height == current_height:
            break
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(2)
        last_height = current_height


async def extract_text(element) -> str:
    """Extract inner text from a Playwright element."""
    return await element.inner_text() if element else "N/A"


async def extract_image_urls(page: Page) -> List[str]:
    """Extract up to 10 image URLs from a product page."""
    images = await page.query_selector_all("button.ux-image-grid-item img")
    image_urls = [await img.get_attribute("src") for img in images if img]
    if len(image_urls) < 10:
        image_urls[:10] + ["N/A"] * (10 - len(image_urls))
    return image_urls[:10]


async def get_listbox_values(page: Page):
    values = []
    # Find all elements with class 'listbox__value'
    value_elements = await page.query_selector_all(".listbox__value")

    # Extract text from each element
    for element in value_elements:
        value_text = await element.inner_text()
        if value_text:  # Only add non-empty values
            values.append(value_text.strip())

    return values


async def get_variant_values(item_page: Page):
    """Get product variants."""
    logging.info("Получение вариантов товара.", exc_info=True)
    try:
        listbox_values = await item_page.query_selector_all(".listbox__value")
        return [await element.inner_text() for element in listbox_values]
    except Exception as e:
        logging.error(f"Ошибка при извлечении значений вариантов: {e}", exc_info=True)
        return []


async def add_to_sheet(sheet: List[List[str]], product_data: Dict) -> None:
    """Await docstring generation..."""
    try:
        sheet.append(
            [
                product_data["title"],
                product_data["price"],
                product_data["category"],
            ]
            + product_data.get("image_urls", [])
            + [
                product_data["item_url_href"],
                product_data["seller_url"],
                product_data.get("quantity", "N/A"),
                product_data.get("brand", "N/A"),
                product_data.get("condition", "N/A"),
            ]
        )
    except KeyError as e:
        logging.error(f"Отсутствует ключ в данных продукта: {e}", exc_info=True)
    except Exception as e:
        logging.error(f"Ошибка при добавлении данных в лист: {e}", exc_info=True)


async def process_variants(
    item_page: Page, product_data: dict[str, tuple[str]], sheet: list
):
    """Processes product variants and writes the results to Excel."""
    logging.info("Обработка вариантов товара.", exc_info=True)
    try:
        variant_values = await get_variant_values(item_page)
        variant_values = await split_list_by_delimiter(variant_values, "Select")
        if variant_values:
            for combo in itertools.product(*variant_values):
                variant_data = product_data.copy()
                variant_data["title"] = f"{product_data['title']} : {combo}"
                pattern = r"\$\d+\.\d+\s+to\s+\$\d+\.\d+"
                if re.findall(pattern, variant_data["price"][0]):
                    price_variant = await select_variant(item_page, combo)
                    if price_variant:
                        variant_data["price"] = price_variant

                await add_to_sheet(sheet, variant_data)
                logging.info(
                    f"Вариант {variant_data['title']} обработан.", exc_info=True
                )
        else:
            await add_to_sheet(sheet, product_data)

    except Exception as e:
        logging.error(f"Ошибка при обработке вариантов: {e}", exc_info=True)


async def process_product_variants(
    item_page: Page, product_data: dict, sheet: List[str]
):
    """
    Processes product variants and writes results to Excel.


    Args:
        item_page (playwright.Page): Playwright page object for the product
        product_data (dict): Dictionary containing product details (title, category, etc.)
        sheet (Workbook): Openpyxl workbook object for writing data
    """

    try:
        await process_variants(item_page, product_data, sheet)
    except Exception as e:
        logging.error(f"Ошибка при обработке вариантов продукта: {e}", exc_info=True)
    finally:
        await item_page.close()


async def get_product_data(
    browser: Browser, page: Page, seller_url: str, sheet: list
) -> None:
    """Extracts product data from a product page."""
    logging.info("Извлечение данных о продукте.", exc_info=True)
    item_url = await page.query_selector("a.s-item__link")
    item_url_href = await item_url.get_attribute("href") if item_url else "N/A"

    title = (await extract_text(await page.query_selector(".s-item__title")),)
    price = (await extract_text(await page.query_selector("span.s-item__price")),)
    context = await browser.new_context(locale="en-US")

    new_page = await context.new_page()
    await new_page.goto(item_url_href, wait_until="domcontentloaded")

    category = await extract_text(
        await new_page.query_selector("ul li a.seo-breadcrumb-text span")
    )
    image_urls = await extract_image_urls(new_page)
    quantity = await extract_text(
        await new_page.query_selector("#qtyAvailability .ux-textspans--SECONDARY")
    )
    condition = await extract_text(
        await new_page.query_selector(".x-item-condition-text .ux-textspans")
    )
    brand = await extract_text(
        await new_page.query_selector(
            "dl[data-testid='ux-labels-values'].ux-labels-values--brand dd span.ux-textspans"
        )
    )
    product_data = {
        "title": title,
        "price": price,
        "category": category,
        "image_urls": image_urls,
        "item_url_href": item_url_href,
        "seller_url": seller_url,
        "quantity": quantity,
        "brand": brand,
        "condition": condition,
    }
    await process_product_variants(new_page, product_data, sheet)


async def process_products_in_batches(
    browser: Browser, items, seller_urls: str, sheet: List[str]
) -> None:
    """Processes products in batches."""
    logging.info("Обработка продуктов в пакетах...", exc_info=True)
    semaphore = asyncio.Semaphore(CONCURRENT_TASK_LIMIT)

    async def process_with_semaphore(browser, item, seller_urls, sheet):
        async with semaphore:
            await get_product_data(browser, item, seller_urls, sheet)

    tasks = [
        process_with_semaphore(browser, item, seller_urls, sheet) for item in items
    ]
    await asyncio.gather(*tasks)
    logging.info("Обработка продуктов в пакетах завершена.", exc_info=True)


async def safe_goto(page: Page, url, retries=3):
    """
    Safely navigates to a URL, handling network errors.

    :param page: Playwright page object
    :param url: URL to navigate to
    :param retries: Number of retries for network errors
    :return: None
    """
    logging.info(f"Navigating to {url}", exc_info=True)
    for attempt in range(retries):
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            logging.info(f"Successfully navigated to {url}")
            return  # Exit if successful
        except playwright._impl._errors.Error as e:
            if "net::ERR_NETWORK_CHANGED" in str(e):
                logging.error(
                    f"Network error encountered. Retry {attempt + 1} of {retries}",
                    exc_info=True,
                )
                await asyncio.sleep(3)  # Wait before retrying
            else:
                logging.error(
                    f"Unexpected error navigating to {url}: {e}", exc_info=True
                )
                raise  # Rethrow non-network errors
    logging.error(
        f"Failed to navigate to {url} after {retries} attempts", exc_info=True
    )
    raise RuntimeError(f"Failed to load {url} after {retries} attempts")


async def parse_ebay_seller(seller_url):
    """
    Scrapes product data from an eBay seller's page and saves it to an Excel file.

    :param seller_url: URL of the eBay seller's page
    """
    logging.info("Starting eBay seller scraping...", exc_info=True)

    try:
        # Launch the Playwright browser
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            logging.info("Browser launched in headless mode.", exc_info=True)
            page = await browser.new_page(locale="en-US")

            # Open the seller's URL
            await page.goto(seller_url)
            logging.info(f"Navigated to {seller_url}", exc_info=True)

            # Scroll the page to load all items (if applicable)
            await scroll_to_load(page)

            # Select product elements
            await page.wait_for_selector("ul.srp-results.srp-list")
            items = await page.query_selector_all("ul.srp-results.srp-list li.s-item")
            logging.info(f"Found {len(items)} items on the page.", exc_info=True)

            pagination_links = await page.eval_on_selector_all(
                ".pagination__items a.pagination__item",
                "elements => elements.map(e => e.href)",
            )
            logging.info(
                f"Found {len(pagination_links)} pagination links.", exc_info=True
            )
            # Create an Excel workbook and add headers
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "eBay Seller Data"
            sheet.append(TITLE_TABLES)

            # Extract data for each product
            for pagination_link in pagination_links:
                logging.info(
                    f"Processing pagination link: {pagination_link}", exc_info=True
                )
                new_page = await browser.new_page(locale="en-US")
                logging.info("New page created.", exc_info=True)
                new_page.context.new_page(locale="en-US")
                # await page.goto(pagination_link, wait_until="domcontentloaded")
                await safe_goto(new_page, pagination_link)
                if page.is_closed():
                    logging.info("Page was unexpectedly closed. Recreating...")
                    new_page = await browser.new_page(locale="en-US")
                await scroll_to_load(new_page)
                items = await page.query_selector_all(
                    "ul.srp-results.srp-list li.s-item"
                )
                logging.info(f"Found {len(items)} items on the page.", exc_info=True)
                try:
                    await process_products_in_batches(browser, items, seller_url, sheet)
                except Exception as e:
                    logging.error(f"Error processing products: {e}", exc_info=True)

            # Save the Excel file
            output_file = "ebay_seller_data_playwright.xlsx"
            workbook.save(output_file)
            logging.info(f"Data successfully saved to {output_file}", exc_info=True)

            # Close the browser
            await browser.close()
            logging.info("Browser closed.", exc_info=True)
    except Exception as e:
        logging.critical(f"An unexpected error occurred: {e}", exc_info=True)


# Specify the seller's URL
seller_url = "https://www.ebay.com/sch/i.html?_trksid=p3692&_ssn=satmaximum"

# Run the asynchronous function
if __name__ == "__main__":
    try:
        asyncio.run(parse_ebay_seller(seller_url))
    except Exception as e:
        logging.critical(f"Failed to execute the script: {e}", exc_info=True)
