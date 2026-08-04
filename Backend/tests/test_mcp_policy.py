from __future__ import annotations

import unittest

from Backend.MCPManager import list_mcp_servers


class MCPPolicyTests(unittest.TestCase):
    def test_google_mcp_endpoints_are_removed(self) -> None:
        self.assertEqual(list_mcp_servers(), [])


if __name__ == "__main__":
    unittest.main()
