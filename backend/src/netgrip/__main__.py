import logging
import sys

from netgrip.config import Config


def main() -> None:
    config = Config.from_env()
    if not config.is_loopback:
        print(
            f"netgrip: refusing to bind to {config.host!r}; only the loopback interface "
            "(127.0.0.1) is supported",
            file=sys.stderr,
        )
        sys.exit(2)

    import uvicorn

    from netgrip.app import create_app

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    uvicorn.run(create_app(config), host=config.host, port=config.port, log_level="info")


if __name__ == "__main__":
    main()
