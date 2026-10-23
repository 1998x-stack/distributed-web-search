import unittest
from scripts.render_os_config import create_config, private_ip


class OpenSearchConfigTests(unittest.TestCase):
    IPS = ("192.168.1.101", "192.168.1.102", "192.168.1.103")

    def test_two_data_and_third_manager(self):
        for name, ip in zip(("os-a", "os-b", "os-c"), self.IPS):
            cfg = create_config(name, self.IPS)
            self.assertEqual(cfg["transport.publish_host"], ip)
            self.assertEqual(cfg["node.name"], name)
            self.assertIn("cluster_manager", cfg["node.roles"])
            self.assertEqual(cfg["cluster.initial_cluster_manager_nodes"],
                             ["os-a", "os-b", "os-c"])
            self.assertEqual("data" in cfg["node.roles"], name != "os-c")
            self.assertEqual(len(cfg["discovery.seed_hosts"]), 3)

    def test_post_bootstrap_removes_init_setting(self):
        cfg = create_config("os-a", self.IPS, bootstrap=False)
        self.assertNotIn("cluster.initial_cluster_manager_nodes", cfg)

    def test_reject_unsafe_addresses(self):
        for address in ("127.0.0.1", "169.254.1.5", "8.8.8.8", "::1"):
            with self.assertRaises(ValueError):
                private_ip(address)


if __name__ == "__main__":
    unittest.main()
