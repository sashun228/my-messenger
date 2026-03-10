from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse
from database import cursor, conn
import random
import string

app = FastAPI()

connections = {}


def generate_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))


@app.get("/")
def get_chat():
    return FileResponse("chat.html")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):

    await websocket.accept()

    login_data = await websocket.receive_text()

    # регистрация
    if login_data.startswith("register:"):

        username = login_data.split(":")[1]

        code = generate_code()

        cursor.execute(
            "INSERT INTO users (username, user_code) VALUES (?, ?)",
            (username, code)
        )
        conn.commit()

        user_id = cursor.lastrowid

        await websocket.send_text(f"YOUR_CODE:{code}")

    # вход
    elif login_data.startswith("login:"):

        code = login_data.split(":")[1]

        cursor.execute(
            "SELECT id, username FROM users WHERE user_code = ?", (code,)
        )

        user = cursor.fetchone()

        if user is None:
            await websocket.close()
            return

        user_id = user[0]
        username = user[1]

    else:
        await websocket.close()
        return

    connections[websocket] = username

    try:
        while True:

            data = await websocket.receive_text()

            receiver_name, message = data.split(":", 1)

            cursor.execute(
                "SELECT id FROM users WHERE username = ?", (receiver_name,)
            )

            receiver = cursor.fetchone()

            if receiver is None:
                continue

            receiver_id = receiver[0]

            cursor.execute(
                "INSERT INTO messages (sender_id, receiver_id, message) VALUES (?, ?, ?)",
                (user_id, receiver_id, message)
            )

            conn.commit()

            for client, name in connections.items():
                if name == receiver_name:
                    await client.send_text(f"{username}: {message}")

    except:
        del connections[websocket]