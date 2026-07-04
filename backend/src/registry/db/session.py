from collections.abc import Generator

from sqlmodel import Session, SQLModel, create_engine

from registry.config import settings

engine = create_engine(settings.database_url, echo=False)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
