"""Validated, atomic import of dashboard exports into an existing database."""

from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import DateTime, select
from sqlalchemy.exc import IntegrityError, StatementError

from src.naukri_agent.models.db_schema import Application, Job, ResumeProfile


def model_values(model, record):
    if not isinstance(record, dict):
        raise ValueError("Each exported record must be an object")
    columns = {column.name: column for column in model.__table__.columns}
    unknown = record.keys() - columns.keys()
    if unknown:
        raise ValueError(f"Unknown {model.__name__} fields: {', '.join(sorted(unknown))}")
    values = {key: value for key, value in record.items() if key != "id"}
    for key, value in values.items():
        if value is not None and isinstance(columns[key].type, DateTime):
            values[key] = datetime.fromisoformat(value) if isinstance(value, str) else value
    return values


async def import_records(session_factory, payload):
    counts = {"jobs": 0, "applications": 0, "resume_profiles": 0}
    data = payload.get("data")
    if not isinstance(data, dict) or not all(isinstance(data.get(key, []), list) for key in counts):
        raise HTTPException(422, "Expected an export containing data.jobs, data.applications and data.resume_profiles arrays")
    try:
        async with session_factory() as session, session.begin():
            job_ids = {}
            for record in data.get("jobs", []):
                values = model_values(Job, record)
                if not all(values.get(key) for key in ("naukri_job_id", "title", "company", "url")):
                    raise ValueError("Jobs require naukri_job_id, title, company and url")
                job = (await session.execute(select(Job).where(Job.naukri_job_id == values["naukri_job_id"]))).scalar_one_or_none()
                if job is None:
                    job = Job(**values)
                    session.add(job)
                    await session.flush()
                    counts["jobs"] += 1
                if record.get("id") is not None:
                    job_ids[record["id"]] = job.id

            for record in data.get("applications", []):
                values = model_values(Application, record)
                old_id = values.get("job_id")
                if old_id not in job_ids:
                    raise ValueError("Every application must reference a job included in the export")
                values["job_id"] = job_ids[old_id]
                if not values.get("status") or not values.get("applied_at"):
                    raise ValueError("Applications require status and applied_at")
                existing = (await session.execute(select(Application.id).where(
                    Application.job_id == values["job_id"],
                    Application.applied_at == values["applied_at"],
                    Application.status == values["status"],
                ))).first()
                if existing is None:
                    session.add(Application(**values))
                    await session.flush()
                    counts["applications"] += 1

            for record in data.get("resume_profiles", []):
                values = model_values(ResumeProfile, record)
                if not values.get("file_hash"):
                    raise ValueError("Resume profiles require file_hash")
                existing = (await session.execute(select(ResumeProfile.id).where(ResumeProfile.file_hash == values["file_hash"]))).first()
                if existing is None:
                    session.add(ResumeProfile(**values))
                    await session.flush()
                    counts["resume_profiles"] += 1
    except (IntegrityError, StatementError) as error:
        raise HTTPException(422, "Export contains invalid or incomplete database records") from error
    except (ValueError, TypeError, KeyError) as error:
        raise HTTPException(422, str(error)) from error
    return counts
