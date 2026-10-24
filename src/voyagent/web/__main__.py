"""Run the web app:  python -m voyagent.web  [--host 0.0.0.0] [--port 7860]"""

import argparse
import os

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Voyagent web app.")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    uvicorn.run("voyagent.web.app:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
