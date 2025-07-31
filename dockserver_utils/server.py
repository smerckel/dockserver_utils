import asyncio
import json
import logging
import signal
import zmq
import zmq.asyncio


class AsyncZeroMQServer:
    def __init__(self, port: int =11000):
        self.context = zmq.asyncio.Context()
        self.socket = self.context.socket(zmq.REP)
        self.bind_address = f"tcp://*:{port}"
        self.socket.bind(self.bind_address)
        # a callback function to do somee processing
        self.callback: dict = {}
        self.task :asyncio.Task|None = None
        logger.info(f"Async Server listening on {self.bind_address}")
        
    def register_callback(self, device, callback):
        logger.debug(f"Registered callback for device {device}.")
        self.callback[device] = callback

    def deregister_callback(self, device):
        logger.debug(f"Deregistered callback for device {device}.")
        self.callback.pop(device)
        
    async def handle_request(self):
        try:
            while True:
                message = await self.socket.recv_string()
                d = json.loads(message)
                device = d["device"]
                action = d["action"]
                logger.debug(f"Received {message}")
                if device not in self.callback:
                    response = f"Unknown device ({device})."
                else:
                    response = await self.callback[device](action)
                await self.socket.send_string(response)
        except Exception as e:
            logger.debug(f"Error in request handling: {e}")
    

    async def run(self):
        logger.debug("ZMQ server started.")
        try:
            await self.handle_request()
        except asyncio.CancelledError:
            self.close()
        finally:
            logger.debug("ZMQ server DONE.")
        
    def close(self):
        """Clean up resources"""
        self.socket.close()
        self.context.term()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.ERROR)
logger.setLevel(logging.DEBUG)
