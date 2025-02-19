import os
import time

from fastapi import FastAPI, HTTPException, Depends, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional, Dict, Any
from crawl4ai import (
    AsyncWebCrawler, BrowserConfig, CrawlerRunConfig,
    PruningContentFilter, DefaultMarkdownGenerator,
    CacheMode
)

app = FastAPI(title="Primer Webscraper API")

# API token security
security = HTTPBearer()
PRIMER_API_TOKEN=os.getenv("PRIMER_API_TOKEN")

def verify_auth(credentials: HTTPAuthorizationCredentials = Security(security)):
    # Verify if the token is valid
    if credentials.scheme.lower() != "bearer" or credentials.credentials != PRIMER_API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid or missing token")
    return True


class CrawlRequest(BaseModel):
    url: str
    browser_config: Optional[Dict[str, Any]] = None
    crawler_config: Optional[Dict[str, Any]] = None

@app.get("/health")
async def health_check():
    return { "status": "Service is running!" }

@app.post("/crawl", dependencies=[Depends(verify_auth)])
async def crawl(request: CrawlRequest):
    browser_config = BrowserConfig(
        verbose=request.browser_config.get("verbose", True),
        headless=request.browser_config.get("headless", False),
        text_mode=request.browser_config.get("text_mode", True),
    )

    crawler_config = request.crawler_config

    # Content filter
    content_filter = crawler_config.get("content_filter")
    prune_filter = PruningContentFilter(
        threshold=content_filter.get("threshold", 0.9),
        threshold_type=content_filter.get("threshold_type", "dynamic"),
        min_word_threshold=content_filter.get("min_word_threshold", 50),
    )

    # Markdown generator
    markdown_generator = crawler_config.get("markdown_generator")
    md_generator = DefaultMarkdownGenerator(
        options={
            "ignore_links": markdown_generator.get("ignore_links", True),
            "ignore_images": markdown_generator.get("ignore_images", True),
            "escape_html": markdown_generator.get("escape_html", True),
        }
    )

    # Default crawler configuration
    crawler_config = CrawlerRunConfig(
        cache_mode=CacheMode(crawler_config.get("cache_mode")) or CacheMode.BYPASS,
        verbose=crawler_config.get("verbose", True),
        wait_until=crawler_config.get("wait_until", "load"),
        only_text=crawler_config.get("only_text", True),
        excluded_tags=crawler_config.get("excluded_tags", ["form", "nav", "footer", "header", "aside", "script", "style", "iframe"]),
        exclude_external_links=crawler_config.get("exclude_external_links", True),
        exclude_social_media_links=crawler_config.get("exclude_social_media_links", True),
        exclude_external_images=crawler_config.get("exclude_external_images", True),
        remove_overlay_elements=crawler_config.get("remove_overlay_elements", True),
        page_timeout=crawler_config.get("page_timeout", 180000),
        content_filter=prune_filter,
        markdown_generator=md_generator,
    )

    max_retries = 5
    for i in range(max_retries):
        try:
            async with AsyncWebCrawler(config=browser_config) as crawler:
                result = await crawler.arun(
                    url=request.url,
                    config=crawler_config,
                )

                if not result.success:
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "error": result.error_message,
                            "status_code": result.status_code
                        }
                    )
                return {
                    "success": True,
                    "title": result.metadata.get("og:title"),
                    "description": result.metadata.get("og:description"),
                    "type": result.metadata.get("og:type"),
                    "image": result.metadata.get("og:image"),
                    "url": result.metadata.get("og:url"),
                    "site_name": result.metadata.get("og:site_name"),
                    "author": result.metadata.get("author"),
                    "keywords": result.metadata.get("keywords"),
                    "raw_markdown": result.markdown_v2.raw_markdown,
                }

        except Exception as ex:
            print(f"Exception while scraping: {ex}")
            if i == max_retries - 1:
                print(f"Failed to scrape {request.url} after {max_retries} attempts")
                return {
                    "success": False,
                    "message": ex,
                    "content": None
                }
            print(f"Waiting for service to start (attempt {i + 1}/{max_retries})...")
            time.sleep(5)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=11235)