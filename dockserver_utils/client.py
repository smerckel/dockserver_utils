import zmq
import time
import json

class ZeroMQClient:
    def __init__(self, host="localhost", port=11000):
        # Create ZeroMQ context
        self.context = zmq.Context()
        
        # Create socket of type REQ (Request)
        self.socket = self.context.socket(zmq.REQ)
        
        # Connect to server
        self.connect_address = f"tcp://{host}:{port}"
        self.socket.connect(self.connect_address)
    
    def send_request(self, message):
        # Send request
        self.socket.send_string(message)
        
        # Wait for response
        response = self.socket.recv_string()
        return response
    
    def close(self):
        # Clean up
        self.socket.close()
        self.context.term()

class UI(object):
    COMMANDS = "quit device status connect disconnect".split()
    
    def __init__(self, host="localhost", port=11000):
        self.client = ZeroMQClient(host, port)
        self.device = "/dev/ttyUSB0"
        
    def get_command(self, input_str):
        s, *_ = input_str.split()
        errorno=0
        index = -1
        for i, c in enumerate(UI.COMMANDS):
            if c.startswith(s):
                if index == -1:
                    index = i
                else:
                    errorno=1
        if errorno==0 and index>=0:
            return UI.COMMANDS[index]
        else:
            return ""

    def send(self, d):
        if self.device:
            d["device"] = self.device
            message = json.dumps(d)
            response = self.client.send_request(message)
            print(response)
        else:
            logger.error("Device not set. Message not sent.")
        
    def set_device(self, s):
        try:
            _, device = s.split()
        except Exception:
            print("Could not parse command")
        else:
            self.device = device
    
    # def set_glider(self, s):
    #     try:
    #         _, glider = s.split()
    #     except Exception:
    #         print("Could not parse command")
    #     else:
    #         m=dict(glider=glider)
    #         self.send(m)
        

    def send_action(self, action):
        m=dict(action=action)
        self.send(m)
        
    def run(self):
        print("Ready to receive input.")
        try:
            while True:
                device_str = self.device or "No Device"
               
                input_str = input(f"[{device_str}]> ")
                cmd = self.get_command(input_str)
                if not cmd:
                    print(f"Command {cmd} not understood.")
                    continue
                match cmd:
                    case "quit":
                        break
                    case "device":
                        self.set_device(input_str)
                    # case "glider":
                    #     self.set_glider(input_str)
                    case "connect":
                        self.send_action("connect")
                    case "disconnect":
                        self.send_action("disconnect")
                    case "status":
                        self.send_action("status")
 
        finally:
            self.client.close()
            print("Closing down")

        
def main():
    ui = UI("localhost", 11000)
    ui.run()
    
if __name__ == "__main__":
    main()
