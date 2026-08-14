"""Catalog persistence layer — PostgreSQL via SQLAlchemy with local fallback."""

import os
from dotenv import load_dotenv
from sqlalchemy import Column, Float, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv("test_bed/.env")


def _get_engine():
    db_url = os.getenv("DATABASE_URL", "")
    if db_url and "postgresql" in db_url:
        try:
            eng = create_engine(db_url, pool_pre_ping=True)
            with eng.connect():
                pass
            return eng
        except Exception:
            pass
    # Fallback to local SQLite when container is offline
    sqlite_url = "sqlite:///test_bed/shopflow.db"
    return create_engine(sqlite_url, connect_args={"check_same_thread": False})


engine = _get_engine()
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"

    id       = Column(Integer, primary_key=True)
    name     = Column(String, nullable=False)
    sku      = Column(String, unique=True, nullable=False)
    price    = Column(Float, nullable=False)
    category = Column(String, nullable=False)
    stock    = Column(Integer, nullable=False)
    emoji    = Column(String, default="📦")


_SEED = [
    Product(id=1, name="Asus Zephyrus G14 Gaming Laptop",    sku="ASUS-G14-6700S", price=120000.0, category="Electronics", stock=15,  emoji="💻"),
    Product(id=2, name="Keychron Q1 Pro Mechanical Keyboard", sku="KEY-Q1-PRO",     price=14500.0,  category="Peripherals", stock=40,  emoji="⌨️"),
    Product(id=3, name="Dell UltraSharp 27-inch 4K Monitor",  sku="DELL-U2723QE",   price=48000.0,  category="Monitors",    stock=22,  emoji="🖥️"),
    Product(id=4, name="Sony WH-1000XM5 Headphones",          sku="SONY-WH-XM5",    price=29900.0,  category="Audio",       stock=35,  emoji="🎧"),
    Product(id=5, name="Cloud GPU Compute Voucher (100hr)",    sku="GPU-CR-100H",    price=8500.0,   category="Cloud",       stock=100, emoji="☁️"),
    Product(id=6, name="Logitech MX Master 3S Mouse",         sku="LOG-MX3S",       price=9500.0,   category="Peripherals", stock=60,  emoji="🖱️"),
]


def init_db() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if db.query(Product).count() == 0:
            db.add_all(_SEED)
            db.commit()


def list_products() -> list[Product]:
    with SessionLocal() as db:
        return db.query(Product).all()


def get_product(product_id: int) -> Product | None:
    with SessionLocal() as db:
        return db.get(Product, product_id)
