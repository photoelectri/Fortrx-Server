from fastapi import WebSocket
from app.services.pubsub import publish_message

class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[int,list[WebSocket]] = {}
    async def connect(self,user_id:int,websocket:WebSocket):
        await websocket.accept()
        self.active_connections.setdefault(user_id, []).append(websocket)
    def disconnect(self,user_id:int,websocket:WebSocket):
        connections = self.active_connections.get(user_id, [])
        remaining = [conn for conn in connections if conn is not websocket]
        if remaining:
            self.active_connections[user_id] = remaining
            return
        self.active_connections.pop(user_id,None)
    async def send_to_user(self,user_id:int,data:dict):
        await publish_message(user_id,data) 
    def is_online(self,user_id:int):
        return bool(self.active_connections.get(user_id))

manager = ConnectionManager()
