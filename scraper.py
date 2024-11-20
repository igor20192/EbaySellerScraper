import asyncio
from html import unescape
import logging
from playwright.async_api import async_playwright
from openpyxl import Workbook
import pdb

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("ebay_scraper.log"), logging.StreamHandler()],
)


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
            page = await browser.new_page()

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
            items = await page.query_selector_all(".s-item")
            logging.info(f"Found {len(items)} items on the page.")

            # Create an Excel workbook and add headers
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "eBay Seller Data"
            sheet.append(
                [
                    "Product Name",
                    "Price",
                    "Category",
                    "Photo 1",
                    "Photo 2",
                    "Photo 3",
                    "Product Link",
                    "Seller Link",
                    "Stock Quantity",
                    "Brand",
                    "Condition",
                ]
            )

            # Extract data for each product
            for item in items:
                try:
                    # Extract product details
                    title = await item.query_selector(".s-item__title")
                    title_text = await title.inner_text() if title else "N/A"

                    price = await item.query_selector(".s-item__price")
                    price_text = await price.inner_text() if price else "N/A"

                    category = await page.query_selector(".b-breadcrumb__text")
                    category_text = await category.inner_text() if category else "N/A"

                    # Extract product link
                    # Ensure the page is fully loaded before selecting items
                    await page.wait_for_selector(
                        ".s-item", timeout=10000
                    )  # Wait up to 10 seconds

                    # Attempt to extract the product link

                    item_url_href = await page.get_attribute("a.s-item__link", "href")
                    if item_url_href:
                        item_url_href = unescape(item_url_href)
                    # Extract up to 3 photos
                    photos = []
                    photo_elements = await item.query_selector_all(".s-item__image-img")
                    for photo in photo_elements[:3]:
                        photo_src = await photo.get_attribute("src")
                        if photo_src:
                            photos.append(photo_src)

                    condition = await item.query_selector(".SECONDARY_INFO")
                    condition_text = (
                        await condition.inner_text() if condition else "N/A"
                    )

                    # Append data to Excel
                    row = (
                        [title_text, price_text, category_text]
                        + photos
                        + [item_url_href, seller_url, "N/A", "N/A", condition_text]
                    )
                    sheet.append(row)
                    logging.info(f"Added item: {title_text}")
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
