import unittest
from fl_security.mtd.client_selection import select_clients
from fl_security.mtd.controller import MTDController

class TestMTD(unittest.TestCase):
    def test_client_selection_reproducibility(self):
        """Client selection returns the same cohort when the seed is unchanged."""
        num_clients = 10
        fraction = 0.5
        selected_1 = select_clients(num_clients, fraction, strategy='random', seed=42)
        selected_2 = select_clients(num_clients, fraction, strategy='random', seed=42)
        self.assertEqual(selected_1, selected_2)

    def test_controller_generation(self):
        """The MTD controller produces valid client-selection rounds."""
        config = {
            "experiment": {"seed": 42},
            "mtd": {"enabled": True, "selection_strategy": "random"}
        }
        controller = MTDController(config)
        round_cfg = controller.generate_round_config(1, num_clients=10, fraction=0.4)
        
        self.assertIn("selected_clients", round_cfg)
        self.assertNotIn("committees", round_cfg)
        self.assertEqual(len(round_cfg["selected_clients"]), 4)
        self.assertEqual(round_cfg["round"], 1)

if __name__ == '__main__':
    unittest.main()
