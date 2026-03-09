from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse
from typing import List

app = FastAPI()

clients: List[WebSocket] = []

@app.get("/")
def get_chat():
    return FileResponse("chat.html")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    clients.append(websocket)

    try:
        while True:
            message = await websocket.receive_text()

            for client in clients:
                if client != websocket:
                    await client.send_text(message)

    except:
        clients.remove(websocket)