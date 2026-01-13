"""Database connection and session management"""

import os
from contextlib import contextmanager
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool
import logging

from .models import Base

logger = logging.getLogger(__name__)


class DatabaseConnection:
    """Manage database connections and sessions"""
    
    def __init__(self, database_url: str = None):
        """
        Initialize database connection.
        
        Args:
            database_url: SQLAlchemy database URL
        """
        if database_url is None:
            # Prefer env override; default to local SQLite for ease of dev
            database_url = os.getenv(
                "DATABASE_URL",
                "sqlite:///./swebench.db"
            )
        
        self.database_url = database_url
        
        engine_kwargs = {
            "poolclass": NullPool,
            "echo": False,
        }
        if database_url.startswith("sqlite"):
            engine_kwargs["connect_args"] = {"check_same_thread": False}
        # Create engine
        self.engine = create_engine(
            database_url,
            **engine_kwargs,
        )
        
        # Create session factory
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )
        
        logger.info(f"Database connection initialized: {self._safe_url()}")
    
    def _safe_url(self) -> str:
        """Return database URL with password masked"""
        if "@" in self.database_url:
            parts = self.database_url.split("@")
            creds = parts[0].split("://")[1]
            if ":" in creds:
                user = creds.split(":")[0]
                return f"{self.database_url.split('://')[0]}://{user}:****@{parts[1]}"
        return self.database_url
    
    def create_tables(self):
        """Create all database tables"""
        try:
            Base.metadata.create_all(bind=self.engine)
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(f"Error creating database tables: {e}")
            raise
    
    def drop_tables(self):
        """Drop all database tables (use with caution!)"""
        try:
            Base.metadata.drop_all(bind=self.engine)
            logger.info("Database tables dropped")
        except Exception as e:
            logger.error(f"Error dropping database tables: {e}")
            raise
    
    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """
        Get a database session with automatic cleanup.
        
        Usage:
            with db.get_session() as session:
                # Use session here
                session.add(obj)
                session.commit()
        """
        session = self.SessionLocal()
        try:
            yield session
        except Exception as e:
            session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            session.close()
    
    def close(self):
        """Close database connection"""
        self.engine.dispose()
        logger.info("Database connection closed")


# Global database connection instance
_db_connection = None


def init_database(database_url: str = None) -> DatabaseConnection:
    """
    Initialize the global database connection.
    
    Args:
        database_url: SQLAlchemy database URL
        
    Returns:
        DatabaseConnection instance
    """
    global _db_connection
    if _db_connection is None:
        _db_connection = DatabaseConnection(database_url)
        _db_connection.create_tables()
    return _db_connection


def get_database() -> DatabaseConnection:
    """
    Get the global database connection.
    
    Returns:
        DatabaseConnection instance
    """
    global _db_connection
    if _db_connection is None:
        _db_connection = init_database()
    return _db_connection


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """
    Get a database session from the global connection.
    
    Usage:
        with get_session() as session:
            # Use session here
    """
    db = get_database()
    with db.get_session() as session:
        yield session