import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ["PULSE_HOME"] = tempfile.mkdtemp(prefix="pulse-api-")
os.environ["PULSE_DRY_RUN"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from fastapi.testclient import TestClient

    AVAILABLE = True
except Exception:
    AVAILABLE = False


@unittest.skipUnless(AVAILABLE, "fastapi и httpx не установлены: pip install -r requirements.txt httpx")
class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from api.app import ApiFactory
        from service.container import Services
        from service.settings import Settings

        cls.settings = Settings.load()
        cls.services = Services(cls.settings, "main.py")
        cls.services.monitor.ping = lambda host: False
        cls.services.monitor.probe = lambda host: False
        cls.services.wake.wake = lambda mac, broadcast=None, port=None: 3
        cls.client = TestClient(ApiFactory(cls.services).build())
        cls.auth = {"X-Pulse-Token": cls.settings.token}

    def device(self, **extra):
        data = {"name": "Gaming PC", "mac": "aa-bb-cc-dd-ee-ff", "host": "192.168.1.77"}
        data.update(extra)
        return data

    def test_health_is_open(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["app"], "pulse")

    def test_auth_required(self):
        self.assertEqual(self.client.get("/api/info").status_code, 401)
        self.assertEqual(self.client.get("/api/devices", headers={"X-Pulse-Token": "wrong"}).status_code, 401)
        self.assertEqual(self.client.get("/api/info", headers=self.auth).status_code, 200)
        self.assertEqual(self.client.get("/api/info", params={"token": self.settings.token}).status_code, 200)

    def test_device_lifecycle(self):
        created = self.client.post("/api/devices", json=self.device(), headers=self.auth)
        self.assertEqual(created.status_code, 201)
        body = created.json()
        self.assertEqual(body["mac"], "AA:BB:CC:DD:EE:FF")
        self.assertNotIn("token", body)
        duplicate = self.client.post("/api/devices", json=self.device(), headers=self.auth)
        self.assertEqual(duplicate.status_code, 409)
        listing = self.client.get("/api/devices", headers=self.auth).json()
        self.assertIn(body["id"], [item["id"] for item in listing])
        woken = self.client.post(f"/api/devices/{body['id']}/wake", headers=self.auth)
        self.assertEqual(woken.status_code, 200)
        self.assertEqual(woken.json()["sent"], 3)
        rejected = self.client.post(f"/api/devices/{body['id']}/shutdown", json={"delay": 5}, headers=self.auth)
        self.assertEqual(rejected.status_code, 409)
        shortcut = self.client.get(f"/api/shortcuts/wake/{body['id']}", params={"token": self.settings.token})
        self.assertEqual(shortcut.status_code, 200)
        updated = self.client.put(
            f"/api/devices/{body['id']}", json=self.device(name="Office"), headers=self.auth
        )
        self.assertEqual(updated.json()["name"], "Office")
        self.assertEqual(self.client.delete(f"/api/devices/{body['id']}", headers=self.auth).status_code, 200)
        self.assertEqual(self.client.delete(f"/api/devices/{body['id']}", headers=self.auth).status_code, 404)

    def test_validation_errors(self):
        bad_mac = self.client.post("/api/devices", json=self.device(mac="zz"), headers=self.auth)
        self.assertEqual(bad_mac.status_code, 422)
        bad_broadcast = self.client.post(
            "/api/devices", json=self.device(mac="11:22:33:44:55:66", broadcast="nope"), headers=self.auth
        )
        self.assertEqual(bad_broadcast.status_code, 422)

    def test_local_shutdown_and_cancel(self):
        done = self.client.post("/api/shutdown", json={"delay": 5}, headers=self.auth)
        self.assertEqual(done.status_code, 200)
        self.assertEqual(self.client.post("/api/shutdown/cancel", headers=self.auth).status_code, 200)

    def test_adhoc_wake(self):
        response = self.client.post(
            "/api/wake", json={"mac": "AA:BB:CC:DD:EE:FF", "broadcast": "192.168.1.255", "port": 9},
            headers=self.auth,
        )
        self.assertEqual(response.status_code, 200)

    def test_ui_is_served(self):
        index = self.client.get("/")
        self.assertEqual(index.status_code, 200)
        self.assertIn("Pulse", index.text)
        self.assertEqual(self.client.get("/static/js/app.js").status_code, 200)
        self.assertEqual(self.client.get("/static/css/app.css").status_code, 200)

    def test_cors_preflight(self):
        response = self.client.options(
            "/api/devices",
            headers={"Origin": "null", "Access-Control-Request-Method": "GET",
                     "Access-Control-Request-Headers": "x-pulse-token"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("access-control-allow-origin", response.headers)


if __name__ == "__main__":
    unittest.main()
