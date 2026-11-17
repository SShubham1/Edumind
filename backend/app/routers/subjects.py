from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Subject, Topic
from ..schemas import SubjectOut

router = APIRouter(prefix="/api/subjects", tags=["subjects"])


@router.get("", response_model=list[SubjectOut])
def list_subjects(db: Session = Depends(get_db)):
    """List curriculum subjects with their topic counts.

    The count lets the UI hide empty subjects and show how much content each
    one currently has.
    """
    counts = dict(
        db.execute(
            select(Topic.subject_id, func.count(Topic.id)).group_by(Topic.subject_id)
        ).all()
    )
    subjects = db.scalars(select(Subject).order_by(Subject.name)).all()
    return [
        SubjectOut(
            id=subject.id,
            key=subject.key,
            name=subject.name,
            description=subject.description,
            topic_count=int(counts.get(subject.id, 0)),
        )
        for subject in subjects
    ]
