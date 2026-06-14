import pytest
import asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select

from backend.database.models import Base, User
from backend.core.security.rbac import hash_password, verify_password

pytestmark = pytest.mark.asyncio(loop_scope="session")

TEST_DB_URL = "sqlite+aiosqlite:///./test_register.db"

test_engine = create_async_engine(TEST_DB_URL, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
async def setup_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def override_get_db_session():
    async with TestSessionLocal() as session:
        yield session


from backend.api.main import app
from backend.database.connection import get_db_session

app.dependency_overrides[get_db_session] = override_get_db_session


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestRegisterNormalFlow:
    async def test_register_with_email(self, client):
        response = await client.post("/api/v1/auth/register", json={
            "username": "testuser1",
            "password": "secure123",
            "email": "test1@example.com"
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert data["user_info"]["username"] == "testuser1"
        assert data["user_info"]["role"] == "viewer"
        assert "permissions" in data["user_info"]

    async def test_register_without_email(self, client):
        response = await client.post("/api/v1/auth/register", json={
            "username": "testuser2",
            "password": "secure123"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["user_info"]["username"] == "testuser2"

    async def test_register_with_null_email(self, client):
        response = await client.post("/api/v1/auth/register", json={
            "username": "testuser3",
            "password": "secure123",
            "email": None
        })
        assert response.status_code == 200
        data = response.json()
        assert data["user_info"]["username"] == "testuser3"

    async def test_register_then_login(self, client):
        reg_response = await client.post("/api/v1/auth/register", json={
            "username": "logintest",
            "password": "secure123",
            "email": "login@example.com"
        })
        assert reg_response.status_code == 200

        login_response = await client.post("/api/v1/auth/login", json={
            "username": "logintest",
            "password": "secure123"
        })
        assert login_response.status_code == 200
        data = login_response.json()
        assert "access_token" in data
        assert data["user_info"]["username"] == "logintest"

    async def test_password_is_hashed(self, client):
        await client.post("/api/v1/auth/register", json={
            "username": "hashtest",
            "password": "secure123",
            "email": "hash@example.com"
        })
        async with TestSessionLocal() as db:
            result = await db.execute(select(User).where(User.username == "hashtest"))
            user = result.scalars().first()
            assert user is not None
            assert user.password_hash != "secure123"
            assert verify_password("secure123", user.password_hash)


class TestRegisterBoundaryConditions:
    async def test_username_min_length_3(self, client):
        response = await client.post("/api/v1/auth/register", json={
            "username": "ab",
            "password": "secure123"
        })
        assert response.status_code == 422

    async def test_username_exactly_3_chars(self, client):
        response = await client.post("/api/v1/auth/register", json={
            "username": "abc",
            "password": "secure123"
        })
        assert response.status_code == 200

    async def test_password_min_length_6(self, client):
        response = await client.post("/api/v1/auth/register", json={
            "username": "shortpwd",
            "password": "12345"
        })
        assert response.status_code == 422

    async def test_password_exactly_6_chars(self, client):
        response = await client.post("/api/v1/auth/register", json={
            "username": "exactpwd",
            "password": "123456"
        })
        assert response.status_code == 200

    async def test_username_max_length_50(self, client):
        long_name = "a" * 50
        response = await client.post("/api/v1/auth/register", json={
            "username": long_name,
            "password": "secure123"
        })
        assert response.status_code == 200

    async def test_username_exceeds_max_length(self, client):
        long_name = "a" * 51
        response = await client.post("/api/v1/auth/register", json={
            "username": long_name,
            "password": "secure123"
        })
        assert response.status_code == 422


class TestRegisterValidationErrors:
    async def test_username_with_spaces(self, client):
        response = await client.post("/api/v1/auth/register", json={
            "username": "user name",
            "password": "secure123"
        })
        assert response.status_code == 422

    async def test_username_with_special_chars(self, client):
        response = await client.post("/api/v1/auth/register", json={
            "username": "user@name!",
            "password": "secure123"
        })
        assert response.status_code == 422

    async def test_invalid_email_format(self, client):
        response = await client.post("/api/v1/auth/register", json={
            "username": "bademail",
            "password": "secure123",
            "email": "not-an-email"
        })
        assert response.status_code == 422

    async def test_invalid_email_no_domain(self, client):
        response = await client.post("/api/v1/auth/register", json={
            "username": "bademail2",
            "password": "secure123",
            "email": "user@"
        })
        assert response.status_code == 422

    async def test_missing_username(self, client):
        response = await client.post("/api/v1/auth/register", json={
            "password": "secure123"
        })
        assert response.status_code == 422

    async def test_missing_password(self, client):
        response = await client.post("/api/v1/auth/register", json={
            "username": "nopwd"
        })
        assert response.status_code == 422


class TestRegisterDuplicateChecks:
    async def test_duplicate_username(self, client):
        await client.post("/api/v1/auth/register", json={
            "username": "duplicate_user",
            "password": "secure123",
            "email": "dup1@example.com"
        })
        response = await client.post("/api/v1/auth/register", json={
            "username": "duplicate_user",
            "password": "secure123",
            "email": "dup2@example.com"
        })
        assert response.status_code == 409
        assert "已存在" in response.json()["detail"]

    async def test_duplicate_email(self, client):
        await client.post("/api/v1/auth/register", json={
            "username": "dup_email_user1",
            "password": "secure123",
            "email": "same@example.com"
        })
        response = await client.post("/api/v1/auth/register", json={
            "username": "dup_email_user2",
            "password": "secure123",
            "email": "same@example.com"
        })
        assert response.status_code == 409
        assert "邮箱" in response.json()["detail"]

    async def test_multiple_users_without_email(self, client):
        r1 = await client.post("/api/v1/auth/register", json={
            "username": "noemail1",
            "password": "secure123"
        })
        assert r1.status_code == 200

        r2 = await client.post("/api/v1/auth/register", json={
            "username": "noemail2",
            "password": "secure123"
        })
        assert r2.status_code == 200


class TestRegisterNoAuthRequired:
    async def test_register_without_authentication(self, client):
        response = await client.post("/api/v1/auth/register", json={
            "username": "publicuser",
            "password": "secure123",
            "email": "public@example.com"
        })
        assert response.status_code == 200
        assert "access_token" in response.json()

    async def test_register_not_requires_admin(self, client):
        response = await client.post("/api/v1/auth/register", json={
            "username": "normaluser",
            "password": "secure123"
        })
        assert response.status_code != 401
        assert response.status_code != 403


class TestRegisterDefaultRole:
    async def test_new_user_gets_viewer_role(self, client):
        response = await client.post("/api/v1/auth/register", json={
            "username": "rolecheck",
            "password": "secure123",
            "email": "role@example.com"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["user_info"]["role"] == "viewer"
        assert "intents:read" in data["user_info"]["permissions"]
        assert "users:manage" not in data["user_info"]["permissions"]
