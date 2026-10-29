# SPDX-FileCopyrightText: The Docling-pipeline Contributors
# SPDX-License-Identifier: MIT

"""PostgreSQL connection helpers shared by every PostgreSQL-backed component.

Builds the connection string from the ``postgres`` config section and the
``DOCPIPE_POSTGRES_*`` environment variables, and creates SQLAlchemy engines.

Configuration precedence:
1. Config dict passed to functions (from YAML)
2. Environment variables (fallback)
3. Built-in defaults
"""

import os
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from docpipe.core.constants import DocpipeConfigKeys, EnvironmentVariables
from docpipe.utils.infrastructure.logging import get_logger

logger = get_logger("DOCPIPE_POSTGRES_DATABASE")


def get_postgres_connection_string(*, config: dict[str, Any] | None = None) -> str | None:
    """
    Build PostgreSQL connection string from config or environment variables.

    Configuration precedence:
    1. Config dict (from YAML): config['postgres']['host'], etc.
    2. Environment variables: DOCPIPE_POSTGRES_HOST, etc.
    3. Built-in defaults

    Args:
        config: Optional configuration dict from YAML

    Environment Variables (fallback):
        DOCPIPE_POSTGRES_HOST: Database host (default: localhost)
        DOCPIPE_POSTGRES_PORT: Database port (default: 5432)
        DOCPIPE_POSTGRES_DB: Database name (default: docpipe)
        DOCPIPE_POSTGRES_USER: Database user (default: docpipe_user)
        DOCPIPE_POSTGRES_PASSWORD: Database password (required)

    Returns:
        Connection string if password is available, None otherwise
    """
    config = config or {}
    postgres_config = config.get(DocpipeConfigKeys.POSTGRES, {})

    # Get password (required) - check config first, then env
    password = postgres_config.get(DocpipeConfigKeys.PASSWORD) or os.getenv(
        EnvironmentVariables.DOCPIPE_POSTGRES_PASSWORD
    )
    if not password:
        logger.warning(
            "PostgreSQL password not configured (YAML or %s)", EnvironmentVariables.DOCPIPE_POSTGRES_PASSWORD
        )
        return None

    # Get other connection parameters with fallback chain: config -> env -> default
    host = postgres_config.get(DocpipeConfigKeys.HOST) or os.getenv(
        EnvironmentVariables.DOCPIPE_POSTGRES_HOST, "localhost"
    )
    port = postgres_config.get(DocpipeConfigKeys.PORT) or os.getenv(EnvironmentVariables.DOCPIPE_POSTGRES_PORT, "5432")
    database = postgres_config.get(DocpipeConfigKeys.DATABASE) or os.getenv(
        EnvironmentVariables.DOCPIPE_POSTGRES_DB, "docpipe"
    )
    user = postgres_config.get(DocpipeConfigKeys.USER) or os.getenv(
        EnvironmentVariables.DOCPIPE_POSTGRES_USER, "docpipe_user"
    )

    connection_string = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}"
    logger.info("PostgreSQL connection string built: %s@%s:%s/%s", user, host, port, database)

    return connection_string


def create_postgres_engine(*, connection_string: str, config: dict[str, Any] | None = None) -> Engine:
    """
    Create SQLAlchemy engine for PostgreSQL.

    Args:
        connection_string: PostgreSQL connection string
        config: Optional configuration dict for pool settings

    Returns:
        SQLAlchemy Engine instance

    Raises:
        PostgresConnectionException: If engine creation fails
    """
    from docpipe.exceptions.docpipe_exceptions import PostgresConnectionException

    config = config or {}
    postgres_config = config.get(DocpipeConfigKeys.POSTGRES, {})

    # Get pool settings from config or use defaults
    pool_size = postgres_config.get(DocpipeConfigKeys.POOL_SIZE, 5)
    max_overflow = postgres_config.get(DocpipeConfigKeys.MAX_OVERFLOW, 10)
    pool_timeout = postgres_config.get(DocpipeConfigKeys.POOL_TIMEOUT, 30)

    try:
        engine = create_engine(
            connection_string,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_timeout=pool_timeout,
            pool_pre_ping=True,  # Verify connections before using
            echo=False,  # Set to True for SQL debugging
        )

        # Test connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        logger.info(
            "PostgreSQL engine created: pool_size=%s, max_overflow=%s, pool_timeout=%s",
            pool_size,
            max_overflow,
            pool_timeout,
        )
        return engine
    except Exception as e:
        logger.error("Failed to create PostgreSQL engine: %s", e)
        raise PostgresConnectionException(
            message=f"PostgreSQL engine creation failed: {e}",
            host=postgres_config.get(DocpipeConfigKeys.HOST, "unknown"),
            database=postgres_config.get(DocpipeConfigKeys.DATABASE, "unknown"),
        ) from e
