"""Entry point for the Vigil hosted service."""

import uvicorn
from hosted.app import create_hosted_app


def main():
    app = create_hosted_app()
    uvicorn.run(app, host="0.0.0.0", port=8400)


if __name__ == "__main__":
    main()
