from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse
from database import cursor, conn

app = FastAPI()

connections = {}
clients = []


@app.get("/")
def get_chat():
    return FileResponse("chat.html")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):

    await websocket.accept()

    username = await websocket.receive_text()

    # проверяем пользователя в базе
    cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()

    if user is None:
        cursor.execute("INSERT INTO users (username) VALUES (?)", (username,))
        conn.commit()
        user_id = cursor.lastrowid
    else:
        user_id = user[0]

    connections[websocket] = username
    clients.append(websocket)

    try:
        while True:

            message = await websocket.receive_text()

            # сохраняем сообщение
            cursor.execute(
                "INSERT INTO messages (user_id, message) VALUES (?, ?)",
                (user_id, message)
            )
            conn.commit()

            # отправляем другим пользователям
            for client in clients:
                if client != websocket:
                    await client.send_text(f"{username}: {message}")

    except:
        clients.remove(websocket)
        del connections[websocket]