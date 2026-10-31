import unittest
from network_safety import attachment_restore_options, validate_isolated_target

class NetworkSafetyTests(unittest.TestCase):
    def test_refuses_shared_a_b_fault_network(self):
        with self.assertRaises(ValueError): validate_isolated_target('api-a',['api-a','api-b'],['api-a'],['api-a','api-b'])
    def test_requires_independent_api_path_to_b(self):
        with self.assertRaises(ValueError): validate_isolated_target('api-a',['api-a'],['api-a'],['api-b'])
    def test_accepts_dedicated_a_network_and_independent_b_route(self):
        validate_isolated_target('api-a',['api-a','api-b'],['api-a'],['api-b'])
    def test_preserves_aliases_and_static_addresses(self):
        self.assertEqual(attachment_restore_options({'Aliases':['shard-a','db-a'],'IPv4Address':'10.0.0.8/24','IPv6Address':'fd00::8/64'}),
                         ['--alias','shard-a','--alias','db-a','--ip','10.0.0.8','--ip6','fd00::8'])

if __name__=='__main__': unittest.main()
