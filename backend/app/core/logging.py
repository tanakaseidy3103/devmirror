"""
DevMirror - 構造化ロギング設定
"""
import logging
import sys

import structlog


def setup_logging() -> None:
    """structlogの設定"""
    # NOTE: 任意ロガークラスで使える汎用プロセッサのみを使用する。
    # stdlib 専用プロセッサ（add_logger_name 等）は logging.Logger を前提と
    # するため、PrintLogger では `AttributeError` になる。
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )

    # stdlib logging との統合
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
    )
