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

    if login_data.startswith("register:"):

        username = login_data.split(":")[1]

        code = generate_code()

        cursor.execute(
            "INSERT INTO users (username, user_code) VALUES (?, ?)",
            (username, code)
        )
        conn.commit()

        user_id = cursor.lastrowid

        await websocket.send_text("CODE:" + code)

    elif login_data.startswith("login:"):

        code = login_data.split(":")[1]

        cursor.execute(
            "SELECT id, username FROM users WHERE user_code=?", (code,)
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

            if data == "GET_USERS":

                cursor.execute("SELECT username FROM users")

                users = cursor.fetchall()

                for u in users:

                    name = u[0]

                    status = "online" if name in connections.values() else "offline"

                    await websocket.send_text(f"USER:{name}:{status}")

                continue


            if data.startswith("LOAD_CHAT:"):

                friend = data.split(":")[1]

                cursor.execute("SELECT id FROM users WHERE username=?", (friend,))
                receiver = cursor.fetchone()

                if receiver is None:
                    continue

                friend_id = receiver[0]

                cursor.execute("""
                SELECT users.username, messages.message
                FROM messages
                JOIN users ON users.id = messages.sender_id
                WHERE (sender_id=? AND receiver_id=?)
                OR (sender_id=? AND receiver_id=?)
                """, (user_id, friend_id, friend_id, user_id))

                messages = cursor.fetchall()

                for m in messages:
                    await websocket.send_text(f"MSG:{m[0]}:{m[1]}")

                continue


            if data.startswith("TYPING:"):

                receiver = data.split(":")[1]

                for client, name in connections.items():
                    if name == receiver:
                        await client.send_text(f"TYPING:{username}")

                continue


            receiver_name, message = data.split(":", 1)

            cursor.execute(
                "SELECT id FROM users WHERE username=?", (receiver_name,)
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

                if name == receiver_name or name == username:

                    await client.send_text(f"MSG:{username}:{message}")

    except:

        del connections[websocket]