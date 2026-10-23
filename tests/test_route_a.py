"""Static repo and deployment invariants; no live YaCy network required."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RENDER = ROOT / "scripts" / "render-config.sh"
FIXTURE = ROOT / "tests" / "fixtures" / "yacy.init"
IPS = ["192.168.1.101", "192.168.1.102", "192.168.1.103"]


def properties(text):
    result = {}
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key, value = stripped.split("=", 1)
            result[key.strip()] = value.strip()
    return result


class RouteAConfigTest(unittest.TestCase):
    def render(self, node, ips=None):
        with tempfile.TemporaryDirectory() as dest:
            cp = subprocess.run(
                ["bash", str(RENDER), node, *(ips or IPS), str(FIXTURE), dest],
                capture_output=True, text=True,
            )
            init = Path(dest, "yacy.init")
            unit = Path(dest, "yacy.network.route-A.unit")
            return cp, init.read_text() if init.exists() else "", unit.read_text() if unit.exists() else ""

    def test_same_private_network_all_nodes(self):
        units = []
        for node, ip in zip(("ubuntu-a", "ubuntu-b", "macos-c"), IPS):
            cp, init, unit = self.render(node)
            self.assertEqual(cp.returncode, 0, cp.stderr)
            p = properties(init)
            n = properties(unit)
            self.assertEqual(p["network.unit.definition"], "defaults/yacy.network.route-A.unit")
            self.assertEqual(p["staticIP"], ip)
            self.assertEqual(n["network.unit.name"], "homeweb")
            self.assertEqual(n["network.unit.dht"], "true")
            self.assertNotIn("freeworld", unit)
            self.assertNotIn("yacy.net/yacy/seed", unit)
            self.assertNotIn("network.unit.bootstrap.seedlist2", unit)
            units.append(unit)
        self.assertEqual(units[0], units[1])
        self.assertEqual(units[1], units[2])

    def test_two_principals_one_worker(self):
        for node, want in (("ubuntu-a", "File"), ("ubuntu-b", "File"), ("macos-c", "none")):
            cp, init, _ = self.render(node)
            self.assertEqual(cp.returncode, 0, cp.stderr)
            p = properties(init)
            self.assertEqual(p["seedUploadMethod"], want)
            self.assertEqual(p["seedFilePath"], "DATA/HTDOCS/seed.txt")
            self.assertTrue(p["seedURL"].endswith("/seed.txt"))

    def test_rejects_bad_addresses_and_nodes(self):
        bad_cases = [
            ("ubuntu-a", ["999.168.1.1", *IPS[1:]]),
            ("ubuntu-a", ["a.b.c.d", *IPS[1:]]),
            ("ubuntu-x", IPS),
        ]
        for node, ips in bad_cases:
            cp, _, _ = self.render(node, ips)
            self.assertNotEqual(cp.returncode, 0, f"Expected rejection: {node} {ips}")

    def test_matches_own_seed_urls(self):
        cp, _, unit = self.render("ubuntu-a")
        self.assertEqual(cp.returncode, 0, cp.stderr)
        p = properties(unit)
        self.assertEqual(p["network.unit.bootstrap.seedlist0"], "http://192.168.1.101:8090/seed.txt")
        self.assertEqual(p["network.unit.bootstrap.seedlist1"], "http://192.168.1.102:8090/seed.txt")


if __name__ == "__main__":
    unittest.main()
