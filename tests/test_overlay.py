import unittest
from unittest.mock import patch, MagicMock
from src.assistant.overlay import OverlayApp
from src.assistant.actions import execute_action
import time

class TestOverlayApp(unittest.TestCase):

    def setUp(self):
        # Initialize the OverlayApp instance before each test
        self.overlay_app = OverlayApp()

    def test_overlay_initialization(self):
        # Test if the overlay app initializes correctly
        self.assertIsNotNone(self.overlay_app)

    def test_overlay_ui_elements(self):
        # Test if the overlay app has the expected UI elements
        self.assertIsNotNone(self.overlay_app.entry)
        self.assertIsNotNone(self.overlay_app.btn_send)
        self.assertIsNotNone(self.overlay_app.btn_observe)
        self.assertIsNotNone(self.overlay_app.btn_quit)

    @patch("src.assistant.overlay.execute_action")
    def test_overlay_command_execution(self, mock_execute_action):
        # Mock the execute_action function
        mock_execute_action.return_value = {"say": "Action executed successfully"}

        # Simulate entering a command
        self.overlay_app.entry_var.set("test_command")
        self.overlay_app._on_enter()

        # Simulate the worker loop processing the command
        self.overlay_app._q.put(("cmd", "test_command"))
        time.sleep(0.1)  # Allow the worker thread to process the queue

        # Verify that execute_action was called with the correct command
        mock_execute_action.assert_called_with("test_command")

if __name__ == "__main__":
    unittest.main()