import threading
import time

import uvicorn


class ServerRunner:
    def __init__(self, app, host, port):
        config = uvicorn.Config(app, host=host, port=port, log_config=None, access_log=False)
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def start(self, timeout=10.0):
        self.thread.start()
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.server.started:
                return True
            if not self.thread.is_alive():
                return False
            time.sleep(0.05)
        return self.server.started

    def wait(self):
        while self.thread.is_alive():
            self.thread.join(timeout=0.5)

    def stop(self):
        self.server.should_exit = True
        self.thread.join(timeout=5)
