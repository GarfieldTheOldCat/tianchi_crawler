import argparse
from .service import mcp
from .service import ensure_playwright_browsers


def main():
    ensure_playwright_browsers()
    parser = argparse.ArgumentParser(description="Tianchi Web Crawler MCP Server")
    parser.parse_args()
    mcp.run()


if __name__ == "__main__":
    main()
