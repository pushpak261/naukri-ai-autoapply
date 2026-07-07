from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update as sql_update

from api.deps import state
from src.naukri_agent.models.db_schema import NaukriAccount

router = APIRouter(tags=["accounts"])


class AccountCreate(BaseModel):
    email: str
    password: str
    name: str = ""
    is_primary: bool = False


class AccountUpdate(BaseModel):
    email: str | None = None
    password: str | None = None
    name: str | None = None
    is_active: bool | None = None
    is_primary: bool | None = None


@router.get("/api/accounts")
async def list_accounts():
    session_factory = await state.db_manager.get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(NaukriAccount).order_by(NaukriAccount.created_at.desc())
        )
        accounts = result.scalars().all()
        return {
            "items": [
                {
                    "id": a.id,
                    "email": a.email[:3] + "..." if len(a.email) > 3 else a.email,
                    "name": a.name,
                    "is_active": a.is_active,
                    "is_primary": a.is_primary,
                    "has_password": bool(a.password),
                    "created_at": a.created_at.isoformat() if a.created_at else "",
                    "last_used_at": a.last_used_at.isoformat() if a.last_used_at else None,
                }
                for a in accounts
            ]
        }


@router.post("/api/accounts")
async def create_account(body: AccountCreate):
    session_factory = await state.db_manager.get_session_factory()
    async with session_factory() as session:
        existing = await session.execute(
            select(NaukriAccount).where(NaukriAccount.email == body.email.strip())
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Account with this email already exists")

        # Deactivate all other accounts so only this new one is active
        await session.execute(sql_update(NaukriAccount).values(is_active=False))

        if body.is_primary:
            current_primary = (
                await session.execute(select(NaukriAccount).where(NaukriAccount.is_primary == True))
            ).scalar_one_or_none()
            if current_primary:
                current_primary.is_primary = False

        account = NaukriAccount(
            email=body.email.strip(),
            password=body.password,
            name=body.name.strip() or body.email.strip(),
            is_active=True,
            is_primary=body.is_primary or False,
        )
        session.add(account)
        await session.commit()
        await session.refresh(account)

        # Sync in-memory state
        state.active_account_email = account.email

        return {
            "status": "created",
            "account": {
                "id": account.id,
                "email": account.email,
                "name": account.name,
                "is_active": account.is_active,
                "is_primary": account.is_primary,
            },
        }


@router.put("/api/accounts/{account_id}")
async def update_account(account_id: int, body: AccountUpdate):
    session_factory = await state.db_manager.get_session_factory()
    async with session_factory() as session:
        result = await session.execute(select(NaukriAccount).where(NaukriAccount.id == account_id))
        account = result.scalar_one_or_none()
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")

        if body.email is not None:
            account.email = body.email.strip()
        if body.password is not None:
            account.password = body.password
        if body.name is not None:
            account.name = body.name.strip()
        if body.is_active is not None:
            account.is_active = body.is_active
            if body.is_active:
                # Deactivate all other accounts
                await session.execute(
                    sql_update(NaukriAccount).where(NaukriAccount.id != account_id).values(is_active=False)
                )
                state.active_account_email = account.email
            else:
                if state.active_account_email == account.email:
                    state.active_account_email = None
        if body.is_primary:
            current_primary = (
                await session.execute(
                    select(NaukriAccount).where(
                        NaukriAccount.is_primary == True, NaukriAccount.id != account_id
                    )
                )
            ).scalar_one_or_none()
            if current_primary:
                current_primary.is_primary = False
                current_primary.is_active = False
            account.is_primary = True
            account.is_active = True

        await session.commit()

        return {
            "status": "updated",
            "account": {
                "id": account.id,
                "email": account.email,
                "name": account.name,
                "is_active": account.is_active,
                "is_primary": account.is_primary,
            },
        }


@router.delete("/api/accounts/{account_id}")
async def delete_account(account_id: int):
    session_factory = await state.db_manager.get_session_factory()
    async with session_factory() as session:
        result = await session.execute(select(NaukriAccount).where(NaukriAccount.id == account_id))
        account = result.scalar_one_or_none()
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")

        if account.is_primary:
            raise HTTPException(status_code=400, detail="Cannot delete the primary account")

        await session.delete(account)
        await session.commit()

        # Clean up the account's session file
        safe_name = account.email.replace("@", "_at_").replace(".", "_dot_")
        session_path = state.settings.sessions_dir / f"naukri_session_{safe_name}.json"
        if session_path.exists():
            session_path.unlink()

        # Clear active account reference if this was the active account
        if state.active_account_email == account.email:
            state.active_account_email = None

        return {"status": "deleted", "message": f"Account {account.email} deleted"}


@router.post("/api/accounts/{account_id}/activate")
async def activate_account(account_id: int):
    session_factory = await state.db_manager.get_session_factory()
    async with session_factory() as session:
        result = await session.execute(select(NaukriAccount).where(NaukriAccount.id == account_id))
        account = result.scalar_one_or_none()
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")

        await session.execute(sql_update(NaukriAccount).values(is_active=False))
        account.is_active = True
        account.last_used_at = datetime.now(UTC)

        await session.commit()

        # Track active account so the API layer and agent subprocess know which session to use
        state.active_account_email = account.email

        return {
            "status": "activated",
            "message": f"Switched to account {account.email}",
            "account": {
                "id": account.id,
                "email": account.email[:3] + "..." if len(account.email) > 3 else account.email,
                "name": account.name,
                "is_active": account.is_active,
                "is_primary": account.is_primary,
            },
        }
