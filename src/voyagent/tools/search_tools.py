"""Web search tool backed by the Serper.dev Google Search API."""

from crewai.tools import tool

from voyagent.serper import SearchError, search

TOP_RESULTS_TO_RETURN = 2
#: Cap snippet length so search results don't balloon the LLM context (which
#: matters on token-per-minute-limited free tiers like Groq's).
MAX_SNIPPET_CHARS = 150


class SearchTools:
    @tool("Search the internet")
    def search_internet(query: str) -> str:
        """Useful to search the internet about a given topic and return relevant results."""
        try:
            results = search(query)
        except SearchError as exc:
            return str(exc)

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
