from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from .database import init_db
from .health import start_health_scheduler
from .routers import admin, auth, internal, invites, stream


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_health_scheduler()
    yield


app = FastAPI(title="Access Window", lifespan=lifespan)

app.include_router(auth.router)
app.include_router(invites.router)
app.include_router(stream.router)
app.include_router(internal.router)
app.include_router(admin.router)


@app.get("/admin", include_in_schema=False)
def admin_redirect():
    return RedirectResponse(url="/admin/")


app.mount("/", StaticFiles(directory="app/static", html=True), name="static")
