import json
from datetime import datetime, timezone

from sqlalchemy import create_engine, Column, Integer, String, Float, Text, DateTime
from sqlalchemy.orm import sessionmaker, DeclarativeBase

DATABASE_URL = "sqlite:///estimates.db"

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


class Estimate(Base):
    __tablename__ = "estimates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    image_filename = Column(String(255), nullable=False)
    scene_description = Column(Text, nullable=True)
    limitations = Column(Text, nullable=True)
    materials_json = Column(Text, nullable=False)  # JSON array of material line items
    total_cost = Column(Float, default=0.0)
    material_count = Column(Integer, default=0)
    priced_count = Column(Integer, default=0)

    def set_materials(self, materials: list[dict]):
        self.materials_json = json.dumps(materials)
        self.material_count = len(materials)
        self.priced_count = sum(1 for m in materials if "unit_cost" in m)
        self.total_cost = sum(m.get("line_total", 0) for m in materials)

    def get_materials(self) -> list[dict]:
        return json.loads(self.materials_json) if self.materials_json else []

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "image_filename": self.image_filename,
            "scene_description": self.scene_description,
            "limitations": self.limitations,
            "materials": self.get_materials(),
            "total_cost": self.total_cost,
            "material_count": self.material_count,
            "priced_count": self.priced_count,
        }


def init_db():
    """Create all tables."""
    Base.metadata.create_all(engine)


def save_estimate(
    image_filename: str,
    scene_description: str,
    limitations: str,
    materials: list[dict],
) -> Estimate:
    """Save a completed estimate to the database."""
    session = SessionLocal()
    try:
        estimate = Estimate(
            image_filename=image_filename,
            scene_description=scene_description,
            limitations=limitations,
        )
        estimate.set_materials(materials)
        session.add(estimate)
        session.commit()
        session.refresh(estimate)
        return estimate
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_estimates(limit: int = 50, offset: int = 0) -> list[dict]:
    """Retrieve past estimates, newest first."""
    session = SessionLocal()
    try:
        estimates = (
            session.query(Estimate)
            .order_by(Estimate.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [e.to_dict() for e in estimates]
    finally:
        session.close()


def get_estimate_by_id(estimate_id: int) -> dict | None:
    """Retrieve a single estimate by ID."""
    session = SessionLocal()
    try:
        estimate = session.query(Estimate).filter_by(id=estimate_id).first()
        return estimate.to_dict() if estimate else None
    finally:
        session.close()
