from fastapi import FastAPI
from pydantic import BaseModel

app_notify = FastAPI(title="Notification Service")


class Notification(BaseModel):
    user_id: int
    email: str
    message: str


@app_notify.post("/notify/")
async def send_notification(notification: Notification):
    print(f"! Sending notification to {notification.email}: {notification.message}")
    return {"status": "sent", "notification": notification.model_dump()}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app_notify, host="0.0.0.0", port=8001)
