# eBay Seller Scraper

A robust, asynchronous web scraper designed to extract detailed product information from eBay seller pages. This tool efficiently collects product data including titles, prices, categories, conditions, and variants, saving the information to Excel spreadsheets.

## Features

- Asynchronous processing for improved performance
- Comprehensive product data extraction
- Automatic pagination handling
- Robust error handling and retry mechanisms
- Rate limiting to prevent server overload
- Excel spreadsheet output
- Detailed logging system

## Requirements

- Python 3.10+
- Playwright
- OpenPyXL
- AsyncIO


## Installation

1. Clone the repository:
```bash
git https://github.com/igor20192/EbaySellerScraper.git
cd EbaySellerScraper
pip install playwright openpyxl asyncio
playwright install chromium
from scraper import parse_ebay_seller
```
# Basic usage
await parse_ebay_seller("https://www.ebay.com/str/sellername")

# Custom output file
await parse_ebay_seller("https://www.ebay.com/str/sellername", "output.xlsx")

This README provides:
1. A clear project description
2. Key features and capabilities
3. Installation instructions
4. Usage examples
5. Technical details about data extraction
6. Important information about error handling and performance
7. Clear limitations and disclaimers

You should customize this template by:
1. Adding your specific installation requirements [[1]](https://dev.to/kfir-g/how-to-write-an-effective-readme-file-a-guide-for-software-engineers-207b)
2. Including your preferred license
3. Adding any specific configuration instructions
4. Updating the repository URL
5. Adding any specific usage scenarios relevant to your implementation
6. Including any additional limitations or requirements specific to your environment

Remember to keep the README updated as you make changes to the project.
