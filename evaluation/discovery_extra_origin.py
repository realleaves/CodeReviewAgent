"""Evaluator-only local WebSocket behavior checks; not Agent-generated proof."""

import json
from pathlib import Path

from evaluation.bugsinpy_review import reviewer_files
from src.repository import snapshot_digest
from src.reproduction import DockerExecutor
from src.schemas import Finding


TEST = '''from tornado.web import Application
from tornado.websocket import WebSocketHandler, websocket_connect
from tornado.httpclient import HTTPRequest
from tornado.testing import AsyncHTTPTestCase, gen_test

class EchoHandler(WebSocketHandler):
    def open(self):
        self.write_message("opened")
    def on_message(self, message):
        pass

class ReproductionTest(AsyncHTTPTestCase):
    def get_app(self):
        return Application([(r"/ws", EchoHandler)])
    @gen_test
    def test_lowercase_control(self):
        port = self.get_http_port()
        request = HTTPRequest(self.get_url("/ws").replace("http", "ws", 1),
            headers={"Host": "localhost:%s" % port,
                     "Origin": "http://localhost:%s" % port})
        connection = yield websocket_connect(request)
        self.assertEqual((yield connection.read_message()), "opened")
        connection.close()
    @gen_test
    def test_reproduction(self):
        port = self.get_http_port()
        request = HTTPRequest(self.get_url("/ws").replace("http", "ws", 1),
            headers={"Host": "LOCALHOST:%s" % port,
                     "Origin": "http://localhost:%s" % port})
        connection = yield websocket_connect(request)
        self.assertEqual((yield connection.read_message()), "opened")
        connection.close()
'''


def main():
    root = Path(__file__).resolve().parents[1]
    experiment = root / "outputs/discovery-goal-20261015"
    out = experiment / "r1-origin-audit"
    out.mkdir(exist_ok=False)
    selection = json.loads(
        (root / "outputs/evidence-original20-20261014/selection.json").read_text()
    )
    case = next(c for c in selection if c["id"] == "tornado-1")
    records = json.loads((experiment / "r1-thinking/results.json").read_text())["records"]
    image = "sha256:a255ffcb469f2ec40f2958a76beb0c2bbebfe92ce9af67a9b48d84b4cb695ac8"
    checks = []
    for side, patched in [("buggy", False), ("fixed", False), ("fixed", True)]:
        files, _ = reviewer_files(
            root / "outputs/bugsinpy-work" / case["snapshot_paths"][side]
        )
        original_digest = snapshot_digest(files)
        if patched:
            old = 'host = self.request.headers.get("Host")'
            new = 'host = self.request.headers.get("Host", "").lower()'
            assert files["tornado/websocket.py"].count(old) == 1
            files["tornado/websocket.py"] = files["tornado/websocket.py"].replace(old, new)
        finding = next(
            f for r in records if r["case"] == case["id"] and r["side"] == side
            for f in r["findings"] if f["id"] in {"ef0c6ef53521", "e0b517c5291b"}
        )
        destination = out / (side + ("-counterfactual-lower-host" if patched else ""))
        destination.mkdir()
        (destination / "test.py").write_text(TEST)
        (destination / "finding.json").write_text(json.dumps(finding, ensure_ascii=False, indent=2) + "\n")
        attempt = DockerExecutor(image).execute(files, Finding.model_validate(finding), TEST)
        (destination / "execution.json").write_text(json.dumps(attempt, ensure_ascii=False, indent=2) + "\n")
        (destination / "execution.log").write_text(attempt["log"])
        checks.append({
            "side": side, "evaluator_patched_copy": patched,
            "original_snapshot_sha256": original_digest,
            "executed_snapshot_sha256": snapshot_digest(files),
            "execution": attempt["execution"],
            "stop_reason": attempt["stop_reason"],
        })
        print(side, patched, attempt["execution"], flush=True)
    (out / "summary.json").write_text(json.dumps({
        "api_calls": 0, "containers": 3,
        "provenance": "Evaluator-written test and counterfactual copy; never replaces Agent outputs or reference tests. All original snapshots preserved.",
        "checks": checks,
    }, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
