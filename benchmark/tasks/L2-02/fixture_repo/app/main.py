from contextlib import asynccontextmanager

from fastapi import FastAPI, Form, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import ValidationError

from .db import create_task as persist_task
from .db import get_task, initialize_database, list_tasks
from .schemas import TaskCreate, TaskRead


FORM_PAGE = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Task Board</title>
  </head>
  <body>
    <main>
      <h1>Create a task</h1>
      <form method="post" action="/tasks">
        <label>Title <input name="title" required maxlength="200"></label>
        <label>Description <textarea name="description" maxlength="2000"></textarea></label>
        <label>Due date <input type="date" name="due_date"></label>
        <button type="submit">Create</button>
      </form>
    </main>
  </body>
</html>
"""


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


def create_app() -> FastAPI:
    application = FastAPI(title="Task Board", lifespan=lifespan)

    @application.get("/", response_class=HTMLResponse)
    def task_form() -> str:
        return FORM_PAGE

    @application.post(
        "/tasks",
        response_model=TaskRead,
        status_code=201,
    )
    def submit_task(
        title: str = Form(...),
        description: str = Form(""),
        due_date: str = Form(""),
    ) -> TaskRead | JSONResponse:
        try:
            task = TaskCreate(
                title=title,
                description=description,
                due_date=due_date,
            )
        except ValidationError as error:
            return JSONResponse(
                status_code=422,
                content={"detail": jsonable_encoder(error.errors())},
            )
        return TaskRead.model_validate(persist_task(task))

    @application.get("/tasks", response_model=list[TaskRead])
    def task_list() -> list[TaskRead]:
        return [TaskRead.model_validate(row) for row in list_tasks()]

    @application.get("/tasks/{task_id}", response_model=TaskRead)
    def task_detail(task_id: int) -> TaskRead:
        row = get_task(task_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Task not found")
        return TaskRead.model_validate(row)

    return application


app = create_app()
