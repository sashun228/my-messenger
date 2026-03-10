from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from database import cursor, conn
from email.mime.text import MIMEText
from dotenv import load_dotenv
import os
import random
import string
import smtplib

load_dotenv(".env")

app = FastAPI()

connections = {}

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")


def generate_code():
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=8))


def send_email(receiver, code):
    try:
        if not EMAIL or not PASSWORD:
            print("EMAIL ERROR: EMAIL or PASSWORD not set in .env")
            return False

        msg = MIMEText(f"Ваш код для входа: {code}")
        msg["Subject"] = "Messenger Code"
        msg["From"] = EMAIL
        msg["To"] = receiver

        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(EMAIL, PASSWORD)
        server.sendmail(EMAIL, receiver, msg.as_string())
        server.quit()

        return True

    except Exception as e:
        print("EMAIL ERROR:", e)
        return False


@app.get("/")
def get_chat():
    return FileResponse("chat.html")


@app.get("/manifest.json")
def get_manifest():
    return FileResponse("manifest.json", media_type="application/manifest+json")


@app.get("/sw.js")
def get_sw():
    return FileResponse("sw.js", media_type="application/javascript")


@app.get("/icon-192.png")
def get_icon_192():
    return FileResponse("icon-192.png", media_type="image/png")


@app.get("/icon-512.png")
def get_icon_512():
    return FileResponse("icon-512.png", media_type="image/png")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    user = None
    user_id = None

    try:
        data = await websocket.receive_text()

        if data.startswith("register:"):
            parts = data.split(":", 2)

            if len(parts) < 3:
                await websocket.send_text("REGISTER_ERROR")
                await websocket.close()
                return

            username = parts[1].strip()
            email = parts[2].strip()

            if not username or not email:
                await websocket.send_text("REGISTER_ERROR")
                await websocket.close()
                return

            cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
            existing = cursor.fetchone()

            if existing is not None:
                await websocket.send_text("USERNAME_EXISTS")
                await websocket.close()
                return

            code = generate_code()

            cursor.execute(
                "INSERT INTO users (username, user_code, email) VALUES (?, ?, ?)",
                (username, code, email)
            )
            conn.commit()

            success = send_email(email, code)

            if not success:
                await websocket.send_text("EMAIL_ERROR")
                await websocket.close()
                return

            cursor.execute(
                "SELECT id FROM users WHERE username = ?",
                (username,)
            )
            row = cursor.fetchone()
            user_id = row[0]
            user = username

            await websocket.send_text("EMAIL_SENT")
            await websocket.send_text(f"AUTH_OK:{user}")

        elif data.startswith("login:"):
            code = data.split(":", 1)[1].strip()

            cursor.execute(
                "SELECT id, username FROM users WHERE user_code = ?",
                (code,)
            )
            row = cursor.fetchone()

            if row is None:
                await websocket.send_text("LOGIN_ERROR")
                await websocket.close()
                return

            user_id = row[0]
            user = row[1]

            await websocket.send_text(f"AUTH_OK:{user}")

        else:
            await websocket.close()
            return

        connections[websocket] = user

        while True:
            data = await websocket.receive_text()

            if data == "GET_USERS":
                cursor.execute("SELECT username FROM users ORDER BY username")
                users = cursor.fetchall()

                for (name,) in users:
                    status = "online" if name in connections.values() else "offline"
                    await websocket.send_text(f"USER:{name}:{status}")

                continue

            if data.startswith("LOAD_CHAT:"):
                friend = data.split(":", 1)[1].strip()

                cursor.execute(
                    "SELECT id FROM users WHERE username = ?",
                    (friend,)
                )
                friend_row = cursor.fetchone()

                if friend_row is None:
                    continue

                friend_id = friend_row[0]

                await websocket.send_text(f"CHAT_START:{friend}")

                cursor.execute("""
                    SELECT u.username, m.message
                    FROM messages m
                    JOIN users u ON u.id = m.sender_id
                    WHERE (m.sender_id = ? AND m.receiver_id = ?)
                       OR (m.sender_id = ? AND m.receiver_id = ?)
                    ORDER BY m.id
                """, (user_id, friend_id, friend_id, user_id))

                history = cursor.fetchall()

                for sender_name, message_text in history:
                    await websocket.send_text(f"MSG:{sender_name}:{message_text}")

                await websocket.send_text(f"CHAT_END:{friend}")
                continue

            if data.startswith("TYPING:"):
                receiver = data.split(":", 1)[1].strip()

                for client, name in connections.items():
                    if name == receiver:
                        await client.send_text(f"TYPING:{user}")

                continue

            if ":" not in data:
                continue

            receiver_name, message = data.split(":", 1)
            receiver_name = receiver_name.strip()
            message = message.strip()

            if not receiver_name or not message:
                continue

            cursor.execute(
                "SELECT id FROM users WHERE username = ?",
                (receiver_name,)
            )
            receiver_row = cursor.fetchone()

            if receiver_row is None:
                continue

            receiver_id = receiver_row[0]

            cursor.execute(
                "INSERT INTO messages (sender_id, receiver_id, message) VALUES (?, ?, ?)",
                (user_id, receiver_id, message)
            )
            conn.commit()

            for client, name in connections.items():
                if name == receiver_name or name == user:
                    await client.send_text(f"MSG:{user}:{message}")

    except WebSocketDisconnect:
        print(f"{user} disconnected")

    finally:
        if websocket in connections:
            del connections[websocket]