from datetime import datetime, timedelta, timezone
from jose import jwt
from core.config import SECRET_KEY, ALGO

data = {
    "user_id": "b7d5e8c5-cea1-4f32-b9ff-9fe9e5ab2dc0",
    "tenant_id": "b5b72eab-8da9-46c6-a041-da3bcddc5d50",
    "role": "admin",
}
data["exp"] = datetime.now(timezone.utc) + timedelta(days=365)

token = jwt.encode(data, SECRET_KEY, algorithm=ALGO)
print(token)
