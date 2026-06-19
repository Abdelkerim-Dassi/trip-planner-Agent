"""Web search tool backed by the Serper.dev Google Search API."""

import json
import os

import requests
from crewai.tools import tool

SEARCH_URL = "https://google.serper.dev/search"
TOP_RESULTS_TO_RETURN = 2
REQUEST_TIMEOUT_SECONDS = 15
#: Cap snippet length so search results don't balloon the LLM context (which
#: matters on token-per-minute-limited free tiers like Groq's).
MAX_SNIPPET_CHARS = 150


class SearchTools:
    @tool("Search the internet")
    def search_internet(query: str) -> str:
        """Useful to search the internet about a given topic and return relevant results."""
        api_key = os.environ.get("SERPER_API_KEY")
        if not api_key:
            return "Search unavailable: SERPER_API_KEY is not set in the environment."

        payload = json.dumps({"q": query})
        headers = {"X-API-KEY": api_key, "content-type": "application/json"}

        try:
            response = requests.post(
                SEARCH_URL,
                headers=headers,
                data=payload,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as exc:
            return f"Search request failed: {exc}"

        results = data.get("organic")
        if not results:
            return (
                "Sorry, I couldn't find anything about that. "
                "There could be an error with your Serper API key."
            )

        formatted = []
        for result in results[:TOP_RESULTS_TO_RETURN]:
            try:
                snippet = result["snippet"][:MAX_SNIPPET_CHARS]
                formatted.append(
                    "\n".join(
                        [
                            f"Title: {result['title']}",
                            f"Link: {result['link']}",
                            f"Snippet: {snippet}",
                            "\n-----------------",
                        ]
                    )
                )
            except KeyError:
                continue

        return "\n".join(formatted)
