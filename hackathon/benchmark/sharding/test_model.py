import unittest
from model import Order, ShardUnavailable, ServiceUnavailable, compare_shards, route, validate_mapping

class ShardingContractTests(unittest.TestCase):
    def setUp(self):
        self.mapping = {1: "a", 2: "a", 3: "b", 4: "b"}
        self.rows = [Order(1, 1, "2026-10-31", "10:00", 7, 2, "paid", 2, 350),
                     Order(1, 2, "2026-10-31", "10:01", 7, 2, "paid", 1, 350),
                     Order(2, 3, "2026-11-01", "00:00", None, None, "cancelled", 1, 999),
                     Order(3, 4, "2026-10-31", "23:59", 9, 4, "shipped", 3, 100)]
    def test_mapping_requires_exact_tenants_and_known_shard(self):
        validate_mapping(self.mapping, ["a", "b"], [1, 2, 3, 4])
        with self.assertRaises(AssertionError): validate_mapping({1:"a",2:"a",3:"b"},["a","b"],[1,2,3,4])
        with self.assertRaises(AssertionError): validate_mapping({1:"x",2:"a",3:"b",4:"b"},["a","b"],[1,2,3,4])
    def test_per_shard_oracle_nullable_keys_and_time_edges(self):
        mapping = {1:"a",2:"a",3:"b"}
        actual = compare_shards(mapping, {"a":self.rows[:3],"b":self.rows[3:]}, [1,2,3], ["a","b"])
        self.assertEqual(actual["a"][(1,"2026-10-31",7,2,"paid")], (2,3,1050))
        self.assertEqual(actual["a"][(2,"2026-11-01",None,None,"cancelled")], (1,1,999))
        self.assertEqual(actual["b"][(3,"2026-10-31",9,4,"shipped")], (1,3,300))
    def test_duplicate_or_misplaced_tenant_fails(self):
        with self.assertRaises(AssertionError): compare_shards({1:"a",2:"a",3:"b"},{"a":self.rows[:3],"b":self.rows[2:]},[1,2,3],["a","b"])
        with self.assertRaises(AssertionError): compare_shards({1:"a",2:"a",3:"b"},{"a":self.rows[:2],"b":self.rows[2:]},[1,2,3],["a","b"])
    def test_unavailable_returns_503_and_other_shard_works(self):
        def down(_): raise ShardUnavailable()
        clients={"a":down,"b":lambda tenant:{"tenant":tenant}}
        with self.assertRaises(ServiceUnavailable) as err: route(1,self.mapping,clients)
        self.assertEqual(err.exception.status_code,503)
        self.assertEqual(route(3,self.mapping,clients),{"tenant":3})
    def test_unmapped_tenant_fails_closed(self):
        with self.assertRaises(ServiceUnavailable): route(99,self.mapping,{"a":lambda t:t,"b":lambda t:t})

if __name__ == "__main__": unittest.main()
