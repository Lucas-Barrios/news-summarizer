from typing import Any

import requests


class NewsApiClient:
    BASE_URL = "https://newsapi.org/v2/everything"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def fetch_articles(
        self,
        query: str,
        language: str = "en",
        page_size: int = 5,
    ) -> list[dict[str, Any]]:
        if not self.api_key:
            raise ValueError("NEWS_API_KEY is required to fetch articles.")

        response = requests.get(
            self.BASE_URL,
            params={
                "q": query,
                "language": language,
                "pageSize": page_size,
                "apiKey": self.api_key,
            },
            timeout=10,
        )
        response.raise_for_status()
        return response.json().get("articles", [])
